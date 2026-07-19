"""Samirob 4-channel USB relay board (binary wire protocol).

Field-proven protocol mined from the Blick suite
(``C:/Blick/src/devices/relay_lib_samirob.py`` / ``relay_controller.py``).
See ``specs/relay-board.md`` for the full derivation and citations.

Wire protocol summary (spec sections 2-3):

* 9600 baud, 8N1, no flow control (pyserial defaults).
* Every host->board command is exactly 4 bytes::

      [0xA0, channel(1-based), opcode, checksum=(b0+b1+b2) & 0xFF]

* Opcodes (spec section 2.1)::

      0x00 off    (silent, no response)
      0x01 on     (silent, no response)
      0x02 off    (4-byte echo response)
      0x03 on     (4-byte echo response)
      0x04 toggle (4-byte echo: state after toggle)
      0x05 status (4-byte echo: current state)

* Response echo is 4 bytes ``[0xA0, channel, state, checksum]`` with
  ``state`` 0x00=OFF / 0x01=ON (spec section 3).

Wiring doctrine (spec section 7.2): devices are wired to the relay's
**normally-closed** (NC) contact, so energizing a relay (``on``) *cuts*
power to the attached device -- used only as an exceptional hard reset.
Electrical note (spec section 1): all 4 relays energized draw ~270 mA, so
the board must sit on a USB 2.0 (or better) port.

The battle-tested source is Python-2 code whose checksum/comparison
arithmetic breaks under Python 3 (spec section 3.3); the checksum algorithm
here (``sum(frame) & 0xFF``) is the Py3-correct rewrite of that logic.
"""

import logging
import threading
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Optional

from sciglob.core.connection import SerialConnection
from sciglob.core.exceptions import (
    ConnectionError,
    DeviceIdentityError,
    RelayBoardError,
    TimeoutError,
)
from sciglob.core.help_mixin import HelpMixin
from sciglob.core.protocols import SerialConfig

if TYPE_CHECKING:
    from sciglob.core.simulation import SimulatedTransport

# Start byte for every frame in both directions (spec section 2, byte 1;
# relay_lib_samirob.py:24 ``self.start_byte = b'\xA0'``).
START_BYTE = 0xA0

# Wire values: state byte in a response echo (spec section 3, byte 3).
STATE_OFF = 0x00
STATE_ON = 0x01

# Frame length, both directions (spec sections 2 and 3).
FRAME_SIZE = 4

# Default serial read timeout in seconds (spec section 5: the only timeout
# constant is the 1 s serial read timeout; relay_lib_samirob.py:9).
DEFAULT_READ_TIMEOUT = 1.0


class Op(IntEnum):
    """Command opcodes (spec section 2.1; relay_lib_samirob.py:60-67)."""

    OFF = 0x00  # turn relay OFF, silent (no response)
    ON = 0x01  # turn relay ON, silent (no response)
    OFF_ACK = 0x02  # turn relay OFF, 4-byte echo response
    ON_ACK = 0x03  # turn relay ON, 4-byte echo response
    TOGGLE = 0x04  # toggle relay, echo with state after toggle
    STATUS = 0x05  # query relay state, 4-byte echo response


#: Opcodes that produce a 4-byte echo response (all except the silent set/clear).
_ACK_OPCODES = frozenset({Op.OFF_ACK, Op.ON_ACK, Op.TOGGLE, Op.STATUS})


def _checksum(frame3: bytes) -> int:
    """Compute the frame checksum ``(b0 + b1 + b2) & 0xFF`` (spec section 2, byte 4).

    Py3-correct rewrite of the Py2 ``sum(ord(i) for i in cmd) % 256`` from
    relay_lib_samirob.py:90 (spec section 3.3).
    """
    return sum(frame3) & 0xFF


def build_frame(channel: int, opcode: int) -> bytes:
    """Build a 4-byte command frame with checksum (spec section 2).

    Args:
        channel: 1-based relay channel (written to the wire verbatim, no offset).
        opcode: One of the :class:`Op` values.

    Returns:
        The 4-byte frame ``[0xA0, channel, opcode, checksum]``.
    """
    body = bytes([START_BYTE, channel, int(opcode)])
    return body + bytes([_checksum(body)])


class RelayBoard(HelpMixin):
    """Samirob 4-channel USB relay board.

    A binary command-response device. Public operations acquire a per-device
    :class:`threading.RLock` around the write+read pair so concurrent callers
    cannot interleave frames and mis-attribute responses (spec section 8).

    Example:
        >>> rb = RelayBoard(port="COM10")
        >>> rb.connect()
        >>> rb.on(1)                 # energize relay 1 (cuts NC-wired device)
        >>> rb.state(1)
        True
        >>> rb.get_status()
        {1: True, 2: False, 3: False, 4: False}
        >>> rb.disconnect()

    Hardware-free:
        >>> rb = SimulatedRelayBoard()
        >>> rb.toggle(2)
        True
    """

    _device_name = "RelayBoard"
    _device_description = "Samirob 4-channel USB relay board (binary protocol)"
    _supported_types = ["Samirob"]
    _default_config = {
        "baudrate": 9600,
        "framing": "8N1",
        "nrelays": 4,
        "frame": "[0xA0, channel, opcode, checksum]",
    }
    _command_reference = {
        "on(ch)": "Energize relay (opcode 0x03, verified echo)",
        "off(ch)": "De-energize relay (opcode 0x02, verified echo)",
        "toggle(ch)": "Toggle relay (opcode 0x04), returns new state",
        "state(ch)": "Query relay state (opcode 0x05)",
        "get_status()": "Query all relays -> {channel: bool}",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        nrelays: int = 4,
        timeout: float = DEFAULT_READ_TIMEOUT,
        name: str = "RelayBoard",
        connection: Optional[SerialConnection] = None,
    ):
        """Initialize the relay board.

        Args:
            port: Serial port path (e.g. ``"COM10"``).
            baudrate: Communication speed (spec section 1: field default 9600).
            nrelays: Number of relays (spec section 1: default/hardcoded 4).
            timeout: Serial read timeout in seconds (spec section 5: 1 s default).
            name: Device name for logging.
            connection: Inject a SerialConnection-compatible transport (e.g.
                :class:`~sciglob.core.simulation.SimulatedTransport`) for
                hardware-free operation. When omitted, a real
                :class:`SerialConnection` is built on :meth:`connect`.
        """
        if nrelays < 1:
            raise RelayBoardError(f"nrelays must be >= 1, got {nrelays}")
        self.port = port
        self.baudrate = baudrate
        self.nrelays = nrelays
        self.timeout = timeout
        self.name = name
        self._injected_connection = connection
        self._connection: Optional[SerialConnection] = None
        self._connected = False
        self._lock = threading.RLock()
        self.logger = logging.getLogger(f"sciglob.{name}")

    # -- connection management ------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Whether the board transport is open."""
        return self._connected

    def connect(self, probe_on_connect: bool = True) -> None:
        """Open the serial transport and (by default) probe for the board.

        There is no identify/version command in the protocol (spec section 6);
        presence is confirmed by a valid status echo. After opening the port
        this queries channel 1 status (opcode 0x05) and requires a well-formed,
        checksum-correct 4-byte echo. A bad/short/absent echo means the device
        on the port is not a Samirob board (or nothing answered), so the port
        is closed and :class:`DeviceIdentityError` is raised.

        Args:
            probe_on_connect: When True (default), perform the status-echo
                presence probe. Pass False to skip it (open only).

        Raises:
            ConnectionError: If no port is available and no transport injected.
            DeviceIdentityError: If the presence probe gets no/short/malformed
                echo (spec section 6).
        """
        with self._lock:
            if self._connected:
                self.logger.warning("Already connected")
                return

            conn = self._injected_connection
            if conn is None:
                if self.port is None:
                    raise ConnectionError("No port specified")
                conn = SerialConnection(
                    port=self.port,
                    config=SerialConfig(baudrate=self.baudrate, timeout=self.timeout),
                    owner=self.name,
                )
            if not conn.is_open:
                conn.open()
            self._connection = conn
            self._connected = True

            if probe_on_connect:
                try:
                    self._probe()
                except DeviceIdentityError:
                    # Presence probe failed: close the port and reset state so
                    # the caller does not hold an open handle to a wrong device.
                    try:
                        conn.close()
                    except Exception:  # pragma: no cover - defensive
                        pass
                    self._connection = None
                    self._connected = False
                    raise

            self.logger.info(f"Connected to relay board on {self.port}")

    def _probe(self) -> None:
        """Confirm a Samirob board is present via a status echo (spec section 6).

        Queries channel 1 status (opcode 0x05) and requires a well-formed
        4-byte echo with a valid start byte and checksum. There is no identify
        command; a valid status echo is the de-facto identity check.

        Raises:
            DeviceIdentityError: On no/short/malformed echo.
        """
        assert self._connection is not None
        frame = build_frame(1, Op.STATUS)
        try:
            self._connection.write_frame(frame)
            response = self._connection.read_exact(FRAME_SIZE, timeout=self.timeout)
        except TimeoutError as e:
            raise DeviceIdentityError(
                "No response to relay-board presence probe "
                "(status echo not received).",
            ) from e
        if (
            len(response) < FRAME_SIZE
            or response[0] != START_BYTE
            or response[3] != _checksum(response[:3])
        ):
            raise DeviceIdentityError(
                "Malformed relay-board presence probe echo; "
                "device is not a Samirob relay board.",
                answer=response.hex(),
            )

    def disconnect(self) -> None:
        """Close the serial transport (safe to call when not connected)."""
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception as e:  # pragma: no cover - defensive
                    self.logger.error(f"Error during disconnect: {e}")
                finally:
                    self._connection = None
                    self._connected = False

    def __enter__(self) -> "RelayBoard":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"<RelayBoard(port={self.port}, nrelays={self.nrelays}, {status})>"

    # -- internals ------------------------------------------------------

    def _validate_channel(self, channel: int) -> None:
        """Validate a 1-based channel against ``nrelays`` (spec section 2.2)."""
        if not isinstance(channel, int) or isinstance(channel, bool):
            raise RelayBoardError("Channel must be an integer.")
        if channel < 1 or channel > self.nrelays:
            raise RelayBoardError(
                f"Invalid channel number. Must be between 1 and {self.nrelays}."
            )

    def _parse_echo(self, response: bytes, channel: int) -> bool:
        """Validate a 4-byte echo and return the reported state.

        Validation order follows spec section 3.2: length -> start byte ->
        checksum -> channel echo.

        Args:
            response: Raw bytes read from the board.
            channel: The channel that was commanded (for echo verification).

        Returns:
            True if the relay reports ON (energized), False if OFF.

        Raises:
            RelayBoardError: On short read, bad start byte, checksum mismatch,
                or channel mismatch.
        """
        if len(response) < FRAME_SIZE:
            raise RelayBoardError("Invalid response (too short)")
        if response[0] != START_BYTE:
            raise RelayBoardError("Invalid start byte in response.")
        if response[3] != _checksum(response[:3]):
            raise RelayBoardError("Checksum mismatch in response.")
        if response[1] != channel:
            raise RelayBoardError("Channel mismatch in response.")
        return response[2] == STATE_ON

    def _transact(self, channel: int, opcode: Op) -> Optional[bool]:
        """Send one command frame and, for ACK opcodes, read+validate the echo.

        Silent opcodes (0x00/0x01) write only and return None. The whole
        write+read pair is guarded by the device lock (spec section 8).

        Raises:
            RelayBoardError: On any wire/validation failure (including a short
                read/timeout, per spec section 4).
        """
        if self._connection is None:
            raise RelayBoardError("Not connected to any relay board.")
        frame = build_frame(channel, opcode)
        with self._lock:
            self._connection.write_frame(frame)
            if opcode not in _ACK_OPCODES:
                return None
            try:
                response = self._connection.read_exact(FRAME_SIZE, timeout=self.timeout)
            except TimeoutError as e:
                raise RelayBoardError(f"Invalid response (too short): {e}") from e
            return self._parse_echo(response, channel)

    # -- public operations ----------------------------------------------

    def on(self, channel: int, silent: bool = False) -> None:
        """Energize (turn ON) a relay.

        Uses the verified opcode 0x03 by default and confirms the echo reports
        ON (spec section 3.2 rule 5). Pass ``silent=True`` to use the no-response
        opcode 0x01 (fire-and-forget; no verification).

        Args:
            channel: 1-based relay channel.
            silent: Use silent opcode 0x01 instead of verified 0x03.

        Raises:
            RelayBoardError: On invalid channel or if the echo is not ON.
        """
        self._validate_channel(channel)
        if silent:
            self._transact(channel, Op.ON)
            return
        state = self._transact(channel, Op.ON_ACK)
        if state is not True:
            raise RelayBoardError("Relay is not ON as expected.")

    def off(self, channel: int, silent: bool = False) -> None:
        """De-energize (turn OFF) a relay.

        Uses the verified opcode 0x02 by default and confirms the echo reports
        OFF (spec section 3.2 rule 5). Pass ``silent=True`` to use the
        no-response opcode 0x00.

        Args:
            channel: 1-based relay channel.
            silent: Use silent opcode 0x00 instead of verified 0x02.

        Raises:
            RelayBoardError: On invalid channel or if the echo is not OFF.
        """
        self._validate_channel(channel)
        if silent:
            self._transact(channel, Op.OFF)
            return
        state = self._transact(channel, Op.OFF_ACK)
        if state is not False:
            raise RelayBoardError("Relay is not OFF as expected.")

    def toggle(self, channel: int) -> bool:
        """Toggle a relay (opcode 0x04) and return the new state.

        Args:
            channel: 1-based relay channel.

        Returns:
            True if the relay is now ON, False if now OFF.

        Raises:
            RelayBoardError: On invalid channel or a bad echo.
        """
        self._validate_channel(channel)
        state = self._transact(channel, Op.TOGGLE)
        assert state is not None  # TOGGLE is an ACK opcode
        return state

    def state(self, channel: int) -> bool:
        """Query a single relay's state (opcode 0x05).

        Args:
            channel: 1-based relay channel.

        Returns:
            True if the relay is ON (energized), False if OFF.

        Raises:
            RelayBoardError: On invalid channel or a bad echo.
        """
        self._validate_channel(channel)
        state = self._transact(channel, Op.STATUS)
        assert state is not None  # STATUS is an ACK opcode
        return state

    def get_status(self) -> dict[int, bool]:
        """Query every relay and return a ``{channel: bool}`` map.

        Returns:
            Dict mapping each 1-based channel to True (ON) / False (OFF).
        """
        with self._lock:
            return {ch: self.state(ch) for ch in range(1, self.nrelays + 1)}


class RelayResponder:
    """Stateful simulator responder for a Samirob relay board.

    Maintains per-channel state and answers exactly as the hardware does:
    silent opcodes (0x00/0x01) produce no response; ACK opcodes (0x02/0x03/
    0x04/0x05) return a checksum-correct 4-byte echo reflecting the resulting
    state. Suitable as the ``responder`` for
    :class:`~sciglob.core.simulation.SimulatedTransport`.
    """

    def __init__(self, nrelays: int = 4, initial: Optional[dict[int, bool]] = None):
        """Initialize the responder.

        Args:
            nrelays: Number of relays to model.
            initial: Optional starting states ``{channel: bool}``.
        """
        self.nrelays = nrelays
        self.state: dict[int, bool] = {ch: False for ch in range(1, nrelays + 1)}
        if initial:
            for ch, val in initial.items():
                self.state[ch] = bool(val)

    def __call__(self, data: bytes) -> Optional[bytes]:
        """Process one command frame and return the echo (or None if silent)."""
        if len(data) != FRAME_SIZE or data[0] != START_BYTE:
            return None
        channel = data[1]
        opcode = data[2]

        if opcode in (Op.OFF, Op.OFF_ACK):
            self.state[channel] = False
        elif opcode in (Op.ON, Op.ON_ACK):
            self.state[channel] = True
        elif opcode == Op.TOGGLE:
            self.state[channel] = not self.state.get(channel, False)
        elif opcode == Op.STATUS:
            pass
        else:
            return None

        if opcode in (Op.OFF, Op.ON):
            return None  # silent opcodes produce no response

        state_byte = STATE_ON if self.state.get(channel, False) else STATE_OFF
        body = bytes([START_BYTE, channel, state_byte])
        return body + bytes([_checksum(body)])


def SimulatedRelayBoard(
    port: str = "SIM_RELAY",
    nrelays: int = 4,
    initial: Optional[dict[int, bool]] = None,
    connect: bool = True,
) -> RelayBoard:
    """Build a :class:`RelayBoard` backed by a hardware-free simulated transport.

    Args:
        port: Simulated port name.
        nrelays: Number of relays to model.
        initial: Optional starting states ``{channel: bool}``.
        connect: Open the transport before returning.

    Returns:
        A ready-to-use :class:`RelayBoard` over a
        :class:`~sciglob.core.simulation.SimulatedTransport` driven by a
        stateful :class:`RelayResponder`.
    """
    from sciglob.core.simulation import SimulatedTransport

    responder = RelayResponder(nrelays=nrelays, initial=initial)
    transport: "SimulatedTransport" = SimulatedTransport(
        responder=responder, port=port, owner="RelayBoard"
    )
    board = RelayBoard(port=port, nrelays=nrelays, connection=transport)
    if connect:
        board.connect()
    return board
