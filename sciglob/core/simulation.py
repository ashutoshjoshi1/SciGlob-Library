"""Shared simulated-transport machinery for hardware-free operation.

Every sciglob device has a simulation twin. Rather than duplicating the
question/answer logic, :class:`SimulatedTransport` subclasses the real
:class:`~sciglob.core.connection.SerialConnection` and swaps the pyserial
object for an in-memory fake — so simulated devices exercise the *real*
drain/ask/validate/retry code paths, byte for byte.

Usage:
    >>> def responder(data: bytes):
    ...     if data == b"?\\r":
    ...         return b"SciGlobHSN2\\n"
    ...     return b"TR0\\n"
    >>> transport = SimulatedTransport(responder=responder, port="SIM1")
    >>> transport.open()
    >>> transport.ask("?", timeout=1.0)
    'SciGlobHSN2'
"""

import threading
import time
from typing import Callable, Optional, Union

from sciglob.core.connection import WIRE_ENCODING, SerialConnection
from sciglob.core.protocols import SerialConfig

# What a responder may return: raw bytes, text (latin-1 encoded), a list of
# either (queued as separate chunks), or None (no answer).
ResponderResult = Union[bytes, str, None, list]
Responder = Callable[[bytes], ResponderResult]


class LineEvent:
    """A recorded control-line transition (DTR/RTS) or hold, for tests."""

    def __init__(self, line: str, value: Union[bool, float], timestamp: float):
        self.line = line  # "dtr", "rts", or "sleep"
        self.value = value
        self.timestamp = timestamp

    def __repr__(self) -> str:
        return f"LineEvent({self.line}={self.value})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, tuple):
            return (self.line, self.value) == other
        if isinstance(other, LineEvent):
            return (self.line, self.value) == (other.line, other.value)
        return NotImplemented


class FakeSerial:
    """In-memory stand-in for ``serial.Serial``.

    Written bytes are handed to a responder callable whose result is queued
    into the receive buffer. Control-line writes are recorded as
    :class:`LineEvent` entries so regression tests can assert exact
    DTR/RTS sequences (e.g. that a normal open never pulses reset lines).
    """

    def __init__(self, responder: Optional[Responder] = None, name: str = "SIM"):
        self.responder = responder
        self.name = name
        self.is_open = True
        self.timeout: float = 0
        self.write_timeout: float = 20.0
        self._rx = bytearray()
        self._lock = threading.Lock()
        self.written: list[bytes] = []
        self.line_events: list[LineEvent] = []
        self._dtr = False
        self._rts = False

    # -- control lines --------------------------------------------------

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, value: bool) -> None:
        self._dtr = bool(value)
        self.line_events.append(LineEvent("dtr", bool(value), time.monotonic()))

    @property
    def rts(self) -> bool:
        return self._rts

    @rts.setter
    def rts(self, value: bool) -> None:
        self._rts = bool(value)
        self.line_events.append(LineEvent("rts", bool(value), time.monotonic()))

    # -- data ------------------------------------------------------------

    @property
    def in_waiting(self) -> int:
        with self._lock:
            return len(self._rx)

    def feed(self, data: Union[bytes, str]) -> None:
        """Queue unsolicited bytes (e.g. an NMEA stream) into the buffer."""
        if isinstance(data, str):
            data = data.encode(WIRE_ENCODING)
        with self._lock:
            self._rx.extend(data)

    def write(self, data: bytes) -> int:
        self.written.append(bytes(data))
        if self.responder is not None:
            result = self.responder(bytes(data))
            self._queue(result)
        return len(data)

    def _queue(self, result: ResponderResult) -> None:
        if result is None:
            return
        if isinstance(result, list):
            for item in result:
                self._queue(item)
            return
        if isinstance(result, str):
            result = result.encode(WIRE_ENCODING)
        with self._lock:
            self._rx.extend(result)

    def read(self, size: int = 1) -> bytes:
        with self._lock:
            data = bytes(self._rx[:size])
            del self._rx[:size]
            return data

    def reset_input_buffer(self) -> None:
        with self._lock:
            self._rx.clear()

    def reset_output_buffer(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False


class SimulatedTransport(SerialConnection):
    """Drop-in :class:`SerialConnection` replacement backed by a responder.

    Inherits the full QA doctrine (drain, poll loop, grace retries,
    unexpected-answer escalation) — only the byte source is faked. Long
    recovery holds (reset pulses, DTR cycles, reopen settles) are scaled by
    ``time_scale`` (default 0: recorded but instantaneous) and appear in
    :attr:`line_events` as ``("sleep", requested_seconds)`` entries so tests
    can assert both ordering and requested hold durations.
    """

    def __init__(
        self,
        responder: Optional[Responder] = None,
        port: str = "SIM",
        config: Optional[SerialConfig] = None,
        owner: Optional[str] = None,
        esp32_safe: bool = False,
        time_scale: float = 0.0,
    ):
        super().__init__(port=port, config=config, owner=owner, esp32_safe=esp32_safe)
        self.responder = responder
        self.time_scale = time_scale
        self._fake: Optional[FakeSerial] = None
        self._sleep = self._scaled_sleep

    def _scaled_sleep(self, seconds: float) -> None:
        if self._fake is not None:
            self._fake.line_events.append(LineEvent("sleep", seconds, time.monotonic()))
        if self.time_scale > 0:
            time.sleep(seconds * self.time_scale)

    def open(self) -> None:
        """Open the simulated port (claims the port registry like a real one)."""
        with self._lock:
            if self.is_open:
                return
            if self.port is None:
                raise ValueError("No port specified")

            from sciglob.core.connection import PortRegistry

            owner = self.owner or f"{self.__class__.__name__}({self.port})"
            PortRegistry.claim(self.port, owner)
            self._claimed = True

            self._fake = FakeSerial(responder=self.responder, name=self.port)
            self._serial = self._fake  # type: ignore[assignment]
            if self.esp32_safe:
                self._fake.dtr = True
                self._fake.rts = True
            self.logger.info(f"Opened simulated port {self.port}")

    @property
    def fake(self) -> FakeSerial:
        """The underlying fake serial object (open the transport first)."""
        if self._fake is None:
            raise RuntimeError("Simulated transport is not open")
        return self._fake

    @property
    def line_events(self) -> list[LineEvent]:
        """Recorded DTR/RTS transitions and holds (empty before open)."""
        return [] if self._fake is None else self._fake.line_events

    @property
    def written(self) -> list[bytes]:
        """Every byte string written to the port, in order."""
        return [] if self._fake is None else self._fake.written

    def feed(self, data: Union[bytes, str]) -> None:
        """Queue unsolicited bytes into the receive buffer."""
        self.fake.feed(data)


def make_responder(
    mapping: dict[str, ResponderResult],
    default: ResponderResult = None,
    end_char: str = "\r",
) -> Responder:
    """Build a responder from a command->answer mapping.

    Keys are command strings *without* the terminator; the written bytes
    are decoded and the terminator stripped before lookup. Values may be
    str/bytes/list/None or a callable returning one of those (for stateful
    answers).

    Args:
        mapping: Command -> canned answer
        default: Answer for unmapped commands (None = stay silent)
        end_char: Terminator to strip from incoming writes

    Returns:
        A responder callable for :class:`SimulatedTransport`
    """

    def responder(data: bytes) -> ResponderResult:
        text = data.decode(WIRE_ENCODING, errors="ignore")
        command = text[: -len(end_char)] if end_char and text.endswith(end_char) else text
        answer = mapping.get(command, default)
        if callable(answer):
            return answer()
        return answer

    return responder
