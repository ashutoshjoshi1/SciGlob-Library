"""SciGlobSRB1 Sensors-Reading-Board interface (RS232).

The SRB is a SciGlob-designed superset of the SBHS: it reports humidity,
temperature *and* pressure over an ASCII request/response protocol
(spec §1). Wire protocol (spec §3, §4):

- ``"?"``  -> a line containing ``"ready"`` (identify / initialize)
- ``"H1"`` -> ``"Humidity(%):<value>"``
- ``"T1"`` -> ``"Temperature(degC):<value>"``
- ``"P1"`` -> ``"Pressure(hPa):<value>"``

Every command is terminated with a single carriage return ``"\\r"`` and every
answer is *also* terminated with ``"\\r"`` (NOT ``"\\r\\n"``) -- spec §2
"Answer terminator". Values are the substring after the first ``":"``
(spec §4.2). On a failed read the field code stores a sentinel value rather
than wedging the bus (spec §5.1): humidity/pressure ``-9``, temperature
``999``.
"""

import threading
from typing import TYPE_CHECKING, Any, Optional

from sciglob.core.base import BaseDevice
from sciglob.core.connection import SerialConnection
from sciglob.core.exceptions import (
    CommunicationError,
    ConnectionError,
    DeviceError,
    SensorError,
    TimeoutError,
)
from sciglob.core.help_mixin import HelpMixin
from sciglob.core.protocols import ESP32_SENSOR_ERROR_MESSAGES, TIMING_CONFIG, SerialConfig

if TYPE_CHECKING:
    from sciglob.core.simulation import SimulatedTransport

# Wire terminators (spec §2: question and answer both end with "\r").
_END_CHAR = "\r"
_ANSWER_END = "\r"

# Command wire strings (spec §3; the modern port and legacy *code* agree that
# the wire truth is ?, H1, T1, P1 -- the legacy docstring is stale).
_CMD_IDENTIFY = "?"
_CMD_HUMIDITY = "H1"
_CMD_TEMPERATURE = "T1"
_CMD_PRESSURE = "P1"

# Answer prefixes -- the accepted answer must start with these (spec §4.2,
# legacy 'start' match mode).
_PREFIX_HUMIDITY = "Humidity(%):"
_PREFIX_TEMPERATURE = "Temperature(degC):"
_PREFIX_PRESSURE = "Pressure(hPa):"


class SRB(BaseDevice, HelpMixin):
    """SciGlobSRB1 sensors-reading board (RS232, 8N1, default 9600 baud).

    Reports humidity (%), temperature (degC) and pressure (hPa). One command
    is in flight per port at a time; a per-device reentrant lock serializes
    all transport access (spec §9).

    Example:
        >>> srb = SRB(port="COM7")
        >>> srb.connect()
        >>> srb.get_temperature()
        25.0
        >>> srb.get_all_sensors()
        {'humidity': 50.0, 'temperature': 25.0, 'pressure': 1013.25}
        >>> srb.disconnect()
    """

    # Verbatim error table (spec §5); includes code 5 = pressure parse failure.
    ERROR_MESSAGES = ESP32_SENSOR_ERROR_MESSAGES

    # Invalid-reading sentinels stored on a failed read (spec §5.1).
    INVALID_HUMIDITY = -9.0
    INVALID_TEMPERATURE = 999.0
    INVALID_PRESSURE = -9.0

    # Error codes attributed to a parse failure per quantity (spec §5).
    _ERR_HUMIDITY = 3
    _ERR_TEMPERATURE = 4
    _ERR_PRESSURE = 5

    # Third consecutive failure -> caller should disconnect (spec §6/§8.2).
    MAX_FAILURES_BEFORE_DISCONNECT = 3

    # HelpMixin metadata
    _device_name = "SRB"
    _device_description = "SciGlobSRB1 sensors-reading board (humidity, temperature, pressure)"
    _supported_types = ["SciGlobSRB1"]
    _default_config = {
        "baudrate": 9600,
        "framing": "8N1",
        "question_terminator": "\\r",
        "answer_terminator": "\\r",
        "action_timeout_s": 12.0,
    }
    _command_reference = {
        "?": "Identify / initialize (answer contains 'ready')",
        "H1": "Read humidity -> 'Humidity(%):<value>'",
        "T1": "Read temperature -> 'Temperature(degC):<value>'",
        "P1": "Read pressure -> 'Pressure(hPa):<value>'",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,  # spec §2: framework default 9600
        timeout: float = TIMING_CONFIG["device_action_timeout"],  # spec §6: 12 s
        name: str = "SRB",
        config: Optional[Any] = None,
        serial_config: Optional[SerialConfig] = None,
        connection: Optional[SerialConnection] = None,
    ):
        """Initialize the SRB.

        Args:
            port: Serial port path (e.g. 'COM7').
            baudrate: Communication speed (spec §2 default 9600).
            timeout: Per-action answer timeout in seconds (spec §6: 12 s).
            name: Device name for logging.
            config: Optional config object exposing ``.serial`` (duck-typed).
            serial_config: Optional SerialConfig overriding port/baud/timeout.
            connection: Inject a SerialConnection-compatible transport (e.g.
                SimulatedTransport) for hardware-free operation.
        """
        if config is not None and getattr(config, "serial", None) is not None:
            port = config.serial.port or port
            baudrate = config.serial.baudrate
        if serial_config is not None:
            port = serial_config.port or port
            baudrate = serial_config.baudrate

        super().__init__(port=port, baudrate=baudrate, timeout=timeout, name=name)
        self._injected_connection = connection
        # RLock guarding all transport / shared-state access (spec §9).
        self._lock = threading.RLock()
        self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        """Number of consecutive failed reads (reset on any success)."""
        return self._consecutive_failures

    # -- connection ------------------------------------------------------

    def connect(self) -> None:
        """Open the port and verify the board answers ``ready``.

        Raises:
            ConnectionError: If no port is available or the port cannot open.
            DeviceError: If the board does not identify as ``ready``.
        """
        with self._lock:
            if self._connected:
                self.logger.warning("Already connected")
                return

            conn = self._injected_connection
            if conn is None:
                if self.port is None:
                    raise ConnectionError("No port specified")
                # spec §2: 8N1, no flow control, non-blocking read, 20 s write
                # timeout -- all SerialConfig defaults; only baud varies.
                conn = SerialConnection(
                    port=self.port,
                    config=SerialConfig(baudrate=self.baudrate),
                    owner=self.name,
                )
            self._connection = conn

            try:
                if not conn.is_open:
                    conn.open()
                # spec §7 step 4: INI reuses the ID query; only 'ready' checked.
                # spec §6: max-unexpected forced to 1 during connect.
                if not self.identify(max_unexpected=1):
                    raise DeviceError("SRB did not respond 'ready' to identify")
            except Exception:
                self.disconnect()
                raise

            self._connected = True
            self._consecutive_failures = 0
            self.logger.info(f"Connected to SciGlobSRB1 on {self.port}")

    def disconnect(self) -> None:
        """Close the connection (safe to call when not connected)."""
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception as e:  # pragma: no cover - defensive
                    self.logger.error(f"Error during disconnect: {e}")
                finally:
                    if self._injected_connection is None:
                        self._connection = None
            self._connected = False

    def identify(
        self,
        probe_timeout: Optional[float] = None,
        max_unexpected: int = 3,
    ) -> bool:
        """Send ``"?"`` and report whether the answer contains ``"ready"``.

        Args:
            probe_timeout: Answer timeout in seconds; defaults to the action
                timeout (12 s). Use a short value (e.g. 0.4 s, spec §6
                maxwaits[9]) during port auto-search.
            max_unexpected: Re-ask budget for non-matching answers (1 during
                connect per spec §6).

        Returns:
            True iff the answer contains ``"ready"``.
        """
        timeout = self.timeout if probe_timeout is None else probe_timeout
        with self._lock:
            if self._connection is None:
                raise DeviceError("Not connected")
            try:
                answer = self._connection.ask(
                    _CMD_IDENTIFY,
                    timeout=timeout,
                    end_char=_END_CHAR,
                    answer_end=_ANSWER_END,
                    validator=lambda a: "ready" in a,
                    max_unexpected=max_unexpected,
                    # spec §6: an identification probe (esp. a 0.4 s port-scan
                    # probe, maxwaits[9]) must abort promptly at its own
                    # timeout -- it must NOT inherit ask()'s short-timeout
                    # grace-retry (up to 3 extra 1 s waits for timeout<=4 s),
                    # which would block a silent port for ~3.4 s instead of ~0.4 s.
                    grace_retries=0,
                )
            except (TimeoutError, CommunicationError, ConnectionError) as e:
                self.logger.warning(f"SRB identify failed: {e}")
                return False
            return "ready" in answer

    def initialize(self) -> bool:
        """Initialize the board (spec §7: reuses ``"?"``; no config exists)."""
        return self.identify()

    # -- readings --------------------------------------------------------

    def get_humidity(self) -> float:
        """Read relative humidity in %.

        Returns:
            Humidity, or ``INVALID_HUMIDITY`` (-9) on a failed read (spec §5.1).
        """
        return self._read(
            _CMD_HUMIDITY, _PREFIX_HUMIDITY, self.INVALID_HUMIDITY, self._ERR_HUMIDITY
        )

    def get_temperature(self) -> float:
        """Read air temperature in degC.

        Returns:
            Temperature, or ``INVALID_TEMPERATURE`` (999) on failure (spec §5.1).
        """
        return self._read(
            _CMD_TEMPERATURE,
            _PREFIX_TEMPERATURE,
            self.INVALID_TEMPERATURE,
            self._ERR_TEMPERATURE,
        )

    def get_pressure(self) -> float:
        """Read barometric pressure in hPa.

        Returns:
            Pressure, or ``INVALID_PRESSURE`` (-9) on a failed read (spec §5.1).
        """
        return self._read(
            _CMD_PRESSURE, _PREFIX_PRESSURE, self.INVALID_PRESSURE, self._ERR_PRESSURE
        )

    def get_all_sensors(self) -> dict[str, float]:
        """Read all three sensors.

        Returns:
            Dict with ``humidity``, ``temperature`` and ``pressure`` keys.
            Any individual reading that fails carries its sentinel value.
        """
        return {
            "humidity": self.get_humidity(),
            "temperature": self.get_temperature(),
            "pressure": self.get_pressure(),
        }

    def send_command(self, command: str) -> Optional[str]:
        """Send a raw command and return the terminator-stripped answer.

        Args:
            command: Wire command string (terminator appended automatically).

        Returns:
            The answer string.

        Raises:
            DeviceError: If not connected.
        """
        with self._lock:
            if self._connection is None:
                raise DeviceError("Not connected")
            answer: str = self._connection.ask(
                command,
                timeout=self.timeout,
                end_char=_END_CHAR,
                answer_end=_ANSWER_END,
            )
            return answer

    def get_status(self) -> dict[str, Any]:
        """Return a status snapshot (includes readings when connected)."""
        status: dict[str, Any] = {
            "connected": self._connected,
            "port": self.port,
            "consecutive_failures": self._consecutive_failures,
        }
        if self._connected:
            try:
                status["readings"] = self.get_all_sensors()
            except Exception as e:  # pragma: no cover - defensive
                status["error"] = str(e)
        return status

    # -- internals -------------------------------------------------------

    def _read(self, command: str, prefix: str, sentinel: float, error_code: int) -> float:
        """Run one sensor read; return the value or the sentinel on failure.

        Frees the bus and stores a sentinel on any failure rather than
        wedging the port (spec §8.2 "Set low level status to free, even if
        error occurred"); a success resets the failure counter (spec §4.2).
        """
        with self._lock:
            if not self._connected or self._connection is None:
                raise DeviceError("Not connected")
            try:
                answer = self._connection.ask(
                    command,
                    timeout=self.timeout,
                    end_char=_END_CHAR,
                    answer_end=_ANSWER_END,
                    validator=lambda a: a.startswith(prefix),
                )
                value = self._parse_value(answer)
                if value is None:
                    raise SensorError(
                        f"{ESP32_SENSOR_ERROR_MESSAGES[error_code]} "
                        f"(command={command!r}, answer={answer!r})",
                        error_code=error_code,
                    )
            except (TimeoutError, CommunicationError, ConnectionError, SensorError) as e:
                self._consecutive_failures += 1
                # spec §8.2: warn but keep going; ReadAuxiData/orchestrator
                # disconnects after MAX_FAILURES_BEFORE_DISCONNECT.
                self.logger.warning(
                    f"srb_control, low level communication error happened while "
                    f"processing command={command!r}: {e}"
                )
                return sentinel
            self._consecutive_failures = 0
            return value

    @staticmethod
    def _parse_value(answer: str) -> Optional[float]:
        """Extract the float after the first ``":"`` (spec §4.2, modern port).

        Returns None if there is no colon or the field is not a float.
        """
        text = answer.replace("\r", "").replace("\n", "")
        if ":" not in text:
            return None
        try:
            return float(text.split(":", 1)[1].strip())
        except ValueError:
            return None


def SimulatedSRB(
    port: str = "SIM_SRB",
    *,
    humidity: float = 50.0,
    temperature: float = 25.0,
    pressure: float = 1013.25,
    ready_line: str = "SciGlobSRB1 ready",
    timeout: float = TIMING_CONFIG["device_action_timeout"],
) -> SRB:
    """Build an :class:`SRB` over a scripted :class:`SimulatedTransport`.

    Canned answers use realistic values (modern StubSRB defaults, spec §4.3)
    and the exact wire shapes (spec §4.2), each terminated with ``"\\r"``.

    Args:
        port: Simulated port name.
        humidity: Canned humidity value (%).
        temperature: Canned temperature value (degC).
        pressure: Canned pressure value (hPa).
        ready_line: Identify answer (must contain 'ready').
        timeout: Per-action answer timeout.

    Returns:
        A connected-capable SRB whose transport answers H1/T1/P1/?.
    """
    from sciglob.core.simulation import SimulatedTransport, make_responder

    responder = make_responder(
        {
            _CMD_IDENTIFY: f"{ready_line}\r",
            _CMD_HUMIDITY: f"{_PREFIX_HUMIDITY}{humidity}\r",
            _CMD_TEMPERATURE: f"{_PREFIX_TEMPERATURE}{temperature}\r",
            _CMD_PRESSURE: f"{_PREFIX_PRESSURE}{pressure}\r",
        },
        end_char=_END_CHAR,
    )
    transport: "SimulatedTransport" = SimulatedTransport(
        responder=responder, port=port, owner="SRB"
    )
    return SRB(port=port, connection=transport, timeout=timeout)
