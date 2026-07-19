"""Serial connection utilities for device communication."""

import logging
import threading
import time
from typing import Callable, Optional

import serial
import serial.tools.list_ports

from sciglob.core.exceptions import (
    CommunicationError,
    ConnectionError,
    PortCollisionError,
    TimeoutError,
)
from sciglob.core.protocols import TIMING_CONFIG, SerialConfig

# Wire encoding used across the Blick suite for all serial text
# (blick_params.py: encmeth='latin-1', encerr='ignore').
WIRE_ENCODING = "latin-1"

# Poll cadence of the ask/answer read loop (Blick op.maxwaits[0] = 0.008 s).
POLL_INTERVAL = 0.008

# Spacing before re-asking a question after an unexpected answer
# (Blick: op.maxwaits[0] + 0.5 = 0.508 s).
UNEXPECTED_ANSWER_RETRY_DELAY = 0.508

# Buffer-drain limits before each question (Blick op.maxserchar / op.maxseriter).
DRAIN_CHUNK = 5000
DRAIN_MAX_ITER = 10


class PortRegistry:
    """Process-wide registry of serial ports owned by sciglob device objects.

    Field lesson (unit 071): two device objects silently sharing one COM port
    corrupt each other's answer streams. Neither reference codebase had an
    explicit registry (they used cooperative exclusion lists), so collisions
    were possible; this registry makes them impossible within one process.
    """

    _lock = threading.Lock()
    _owners: dict[str, str] = {}

    @staticmethod
    def normalize(port: str) -> str:
        """Normalize a port name for comparison (COM ports are case-insensitive)."""
        port = port.strip()
        if port.upper().startswith("COM") or port.startswith("\\\\.\\"):
            return port.upper().replace("\\\\.\\", "")
        return port

    @classmethod
    def claim(cls, port: str, owner: str) -> None:
        """Claim a port for a device.

        Args:
            port: Serial port name
            owner: Human-readable owner description (device name)

        Raises:
            PortCollisionError: If the port is owned by another device
        """
        key = cls.normalize(port)
        with cls._lock:
            existing = cls._owners.get(key)
            if existing is not None and existing != owner:
                raise PortCollisionError(port, owner, existing)
            cls._owners[key] = owner

    @classmethod
    def release(cls, port: str, owner: Optional[str] = None) -> None:
        """Release a port claim (no-op if not claimed or claimed by another owner)."""
        key = cls.normalize(port)
        with cls._lock:
            if key in cls._owners and (owner is None or cls._owners[key] == owner):
                del cls._owners[key]

    @classmethod
    def owner_of(cls, port: str) -> Optional[str]:
        """Return the owner of a port, or None if unclaimed."""
        with cls._lock:
            return cls._owners.get(cls.normalize(port))

    @classmethod
    def clear(cls) -> None:
        """Release all claims (test helper)."""
        with cls._lock:
            cls._owners.clear()


class SerialConnection:
    """
    Serial port communication handler.

    Implements the question-answer protocol used by SciGlob devices.

    Thread safety: all public I/O methods hold a per-connection reentrant
    lock, so a connection object may be shared between timer, watchdog and
    recovery threads.

    ESP32 doctrine (SBHS/ASB boxes): pass ``esp32_safe=True``. The port is
    then opened with ``dsrdtr=False`` and DTR/RTS are explicitly asserted
    afterwards — on Windows, ``dsrdtr=True`` puts the driver in
    DTR_CONTROL_HANDSHAKE and silently ignores manual ``ser.dtr`` writes.
    Reset lines are never pulsed during a normal open (the ESP32 needs
    0.5–2 s after boot before its UART listens); use :meth:`reset_pulse`
    only as an explicit recovery action.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        config: Optional[SerialConfig] = None,
        owner: Optional[str] = None,
        esp32_safe: bool = False,
    ):
        """
        Initialize serial connection.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0' or 'COM3')
            config: Serial configuration parameters
            owner: Device name for the process-wide port registry; when set,
                opening refuses ports already owned by another device
            esp32_safe: Open with the ESP32-safe line discipline (see class doc)
        """
        self.port = port
        self.config = config or SerialConfig()
        self.owner = owner
        self.esp32_safe = esp32_safe
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.RLock()
        self._claimed = False
        # Long recovery holds go through this hook so simulated transports
        # can scale them down; poll loops use time.sleep directly.
        self._sleep: Callable[[float], None] = time.sleep
        self.logger = logging.getLogger(f"sciglob.serial.{port or 'unknown'}")

    @property
    def is_open(self) -> bool:
        """Check if the serial port is open."""
        return self._serial is not None and self._serial.is_open

    def open(self) -> None:
        """
        Open the serial connection.

        Raises:
            ConnectionError: If the port cannot be opened
            PortCollisionError: If the port is owned by another sciglob device
        """
        with self._lock:
            if self.is_open:
                self.logger.warning(f"Port {self.port} is already open")
                return

            if self.port is None:
                raise ConnectionError("No port specified")

            owner = self.owner or f"{self.__class__.__name__}({self.port})"
            PortRegistry.claim(self.port, owner)
            self._claimed = True

            dsrdtr = False if self.esp32_safe else self.config.dsrdtr
            try:
                self._serial = serial.Serial(
                    port=self.port,
                    baudrate=self.config.baudrate,
                    bytesize=self.config.bytesize,
                    parity=self.config.parity,
                    stopbits=self.config.stopbits,
                    timeout=self.config.timeout,
                    write_timeout=self.config.write_timeout,
                    xonxoff=self.config.xonxoff,
                    rtscts=self.config.rtscts,
                    dsrdtr=dsrdtr,
                )
                if self.esp32_safe:
                    # Hold both lines asserted so EN stays high and the
                    # module keeps running its application firmware.
                    # NEVER pulse reset lines here (boot-time UART race).
                    self._serial.dtr = True
                    self._serial.rts = True
                self.logger.info(f"Opened serial port {self.port} at {self.config.baudrate} baud")
            except serial.SerialException as e:
                PortRegistry.release(self.port, owner)
                self._claimed = False
                raise ConnectionError(f"Failed to open port {self.port}: {e}") from e

    def close(self) -> None:
        """Close the serial connection."""
        with self._lock:
            if self._serial is not None:
                try:
                    self._serial.close()
                    self.logger.info(f"Closed serial port {self.port}")
                except Exception as e:
                    self.logger.error(f"Error closing port {self.port}: {e}")
                finally:
                    self._serial = None
            if self._claimed and self.port is not None:
                owner = self.owner or f"{self.__class__.__name__}({self.port})"
                PortRegistry.release(self.port, owner)
                self._claimed = False

    def reopen(self, settle: float = 3.0) -> None:
        """Close and reopen the port (recovery step -2 of the Blick ladder).

        Args:
            settle: Seconds to wait between close and reopen
                (field-proven value: 3 s, Blick op.maxwaits[13])
        """
        with self._lock:
            self.close()
            self._sleep(settle)
            self.open()

    def dtr_cycle(self, hold: float = 3.0) -> None:
        """Pulse DTR low then high (recovery step -1 of the Blick ladder).

        Args:
            hold: Seconds to hold DTR low, and to settle after re-assert
                (field-proven value: 3 s each, Blick op.maxwaits[13])
        """
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise ConnectionError("Serial port is not open")
            self._serial.dtr = False
            self._sleep(hold)
            self._serial.dtr = True
            self._sleep(hold)

    def reset_pulse(self, hold: float = 0.5) -> None:
        """Pulse the ESP32 reset line: drop DTR (EN low, IO0 high), re-assert.

        Boots the module into its application firmware. Use only as an
        explicit recovery action — never during a normal open — and throttle
        automatic firings to >= 600 s apart (device-level policy).

        Args:
            hold: Seconds to hold the reset line low (field value: 0.5 s)
        """
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise ConnectionError("Serial port is not open")
            self.logger.info(f"ESP32 reset pulse on {self.port} (hold {hold}s)")
            self._serial.rts = True
            self._serial.dtr = False
            self._sleep(hold)
            self._serial.dtr = True

    def flush_buffers(self) -> None:
        """Flush both input and output buffers."""
        with self._lock:
            if self._serial is not None and self._serial.is_open:
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()

    def read_buffer(self) -> bytes:
        """Read all available data from input buffer."""
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise ConnectionError("Serial port is not open")

            data = b""
            while self._serial.in_waiting > 0:
                data += self._serial.read(self._serial.in_waiting)
                time.sleep(0.01)
            return data

    def drain(self) -> bytes:
        """Drain stale input before asking a question (Blick ser_question).

        Reads up to DRAIN_MAX_ITER chunks of DRAIN_CHUNK bytes; if the
        iteration cap is hit, the input buffer is flushed.

        Returns:
            Bytes that were sitting in the buffer (for diagnostics)
        """
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise ConnectionError("Serial port is not open")

            stale = b""
            iterations = 0
            while self._serial.in_waiting > 0 and iterations < DRAIN_MAX_ITER:
                stale += self._serial.read(min(self._serial.in_waiting, DRAIN_CHUNK))
                iterations += 1
            if iterations >= DRAIN_MAX_ITER:
                self._serial.reset_input_buffer()
            if stale:
                self.logger.debug(f"Drained stale buffer: {stale!r}")
            return stale

    def write(self, data: bytes) -> int:
        """
        Write data to the serial port.

        Args:
            data: Bytes to write

        Returns:
            Number of bytes written
        """
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise ConnectionError("Serial port is not open")

            self.logger.debug(f"TX: {data!r}")
            bytes_written: int = self._serial.write(data)
            return bytes_written

    def read(self, size: int = 1, timeout: Optional[float] = None) -> bytes:
        """
        Read data from the serial port.

        Args:
            size: Number of bytes to read
            timeout: Read timeout in seconds

        Returns:
            Bytes read from port
        """
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise ConnectionError("Serial port is not open")

            if timeout is not None:
                original_timeout = self._serial.timeout
                self._serial.timeout = timeout

            try:
                data: bytes = self._serial.read(size)
                self.logger.debug(f"RX: {data!r}")
                return data
            finally:
                if timeout is not None:
                    self._serial.timeout = original_timeout

    def read_exact(self, size: int, timeout: float = 1.0) -> bytes:
        """Read exactly ``size`` bytes or raise on timeout (binary frames).

        Args:
            size: Number of bytes required
            timeout: Maximum time to wait for the full frame

        Returns:
            Exactly ``size`` bytes

        Raises:
            TimeoutError: If the full frame does not arrive in time
        """
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise ConnectionError("Serial port is not open")

            deadline = time.monotonic() + timeout
            data = b""
            while len(data) < size:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Expected {size} bytes, got {len(data)} within {timeout}s: {data!r}"
                    )
                waiting = self._serial.in_waiting
                if waiting > 0:
                    data += self._serial.read(min(waiting, size - len(data)))
                else:
                    time.sleep(POLL_INTERVAL)
            self.logger.debug(f"RX: {data!r}")
            return data

    def write_frame(self, frame: bytes, drain_first: bool = True) -> None:
        """Write a raw binary frame (no terminator appended).

        Args:
            frame: Frame bytes to write
            drain_first: Drain stale input before writing
        """
        with self._lock:
            if drain_first:
                self.drain()
            self.write(frame)

    def read_until(
        self,
        terminator: bytes = b"\n",
        timeout: float = 1.0,
        max_bytes: int = 1024,
    ) -> bytes:
        """
        Read until terminator character or timeout.

        Args:
            terminator: End character(s) to look for
            timeout: Maximum time to wait
            max_bytes: Maximum bytes to read

        Returns:
            Data read including terminator (if found)
        """
        with self._lock:
            if self._serial is None or not self._serial.is_open:
                raise ConnectionError("Serial port is not open")

            start_time = time.time()
            data = b""

            while True:
                if time.time() - start_time > timeout:
                    self.logger.debug(f"Read timeout, got: {data!r}")
                    break

                if len(data) >= max_bytes:
                    self.logger.warning(f"Max bytes reached: {max_bytes}")
                    break

                if self._serial.in_waiting > 0:
                    chunk = self._serial.read(1)
                    data += chunk

                    if data.endswith(terminator):
                        break
                else:
                    time.sleep(0.01)

            self.logger.debug(f"RX: {data!r}")
            return data

    def send_command(
        self,
        command: str,
        end_char: str = "\r",
        encoding: str = "ascii",
    ) -> None:
        """
        Send a command string.

        Args:
            command: Command to send
            end_char: End character to append
            encoding: String encoding
        """
        with self._lock:
            data = (command + end_char).encode(encoding)
            self.flush_buffers()
            self.write(data)

    def query(
        self,
        command: str,
        end_char: str = "\r",
        response_end_char: str = "\n",
        timeout: float = 1.0,
        encoding: str = "ascii",
    ) -> str:
        """
        Send command and wait for response.

        This implements the standard question-answer protocol.

        Args:
            command: Command string
            end_char: Command end character
            response_end_char: Expected response terminator
            timeout: Response timeout
            encoding: String encoding

        Returns:
            Response string (stripped of terminator)
        """
        with self._lock:
            self.send_command(command, end_char, encoding)

            # Small delay for device to process
            time.sleep(TIMING_CONFIG["inter_command_delay"])

            response = self.read_until(
                terminator=response_end_char.encode(encoding),
                timeout=timeout,
            )

            return response.decode(encoding).strip()

    def ask(
        self,
        question: str,
        timeout: float,
        end_char: str = "\r",
        answer_end: str = "\n",
        validator: Optional[Callable[[str], bool]] = None,
        max_unexpected: int = 3,
        grace_retries: int = 3,
        encoding: str = WIRE_ENCODING,
    ) -> str:
        """Full QA cycle: drain -> ask -> poll-read -> validate -> retry.

        Implements the Blick ``qa``/``ser_answer``/``check_answer`` doctrine:

        * the input buffer is drained before every write;
        * the answer is polled every 8 ms until ``answer_end`` arrives;
        * short questions (timeout <= 4 s) that time out get up to
          ``grace_retries`` extra 1-second waits (field lesson: answers
          straggle);
        * an answer failing ``validator`` is re-asked after ~0.5 s, up to
          ``max_unexpected`` times, then raises.

        Args:
            question: Question string (terminator appended automatically)
            timeout: Per-question answer timeout in seconds (required;
                see the per-action timeout registry in the protocol docs)
            end_char: Question terminator
            answer_end: Answer terminator
            validator: Callable returning True for an expected answer;
                None accepts anything
            max_unexpected: Re-ask budget for unexpected answers
            grace_retries: Extra 1 s waits for short-timeout questions
            encoding: Wire encoding (latin-1 per the Blick suite)

        Returns:
            The answer string with the terminator stripped

        Raises:
            TimeoutError: No terminated answer within the (graced) timeout
            CommunicationError: Unexpected-answer budget exhausted
        """
        with self._lock:
            unexpected = 0
            while True:
                self.drain()
                self.write((question + end_char).encode(encoding, errors="ignore"))

                data = b""
                answer_end_b = answer_end.encode(encoding)
                deadline = time.monotonic() + timeout
                grace_used = 0
                while True:
                    if self._serial is not None and self._serial.in_waiting > 0:
                        data += self._serial.read(self._serial.in_waiting)
                        if answer_end_b in data:
                            break
                    if time.monotonic() > deadline:
                        # Long actions abort immediately; short actions get
                        # grace seconds (Blick qa: mwt > 4 s threshold).
                        if timeout <= 4 and grace_used < grace_retries:
                            grace_used += 1
                            self.logger.warning(
                                f"Answer to '{question}' is taking longer than expected, "
                                f"waiting 1 second more (try {grace_used} of {grace_retries})"
                            )
                            deadline = time.monotonic() + 1.0
                        else:
                            raise TimeoutError(
                                f"No answer from serial port {self.port} received "
                                f"within {timeout} seconds (question: '{question}')"
                            )
                    time.sleep(POLL_INTERVAL)

                # Keep everything up to the last terminator (stale fragments
                # from earlier timed-out reads may precede the real answer).
                raw: str = bytes(data).decode(encoding, errors="ignore")
                answer: str = raw[: raw.rindex(answer_end)].strip("\r\n")

                if validator is None or validator(answer):
                    return answer

                unexpected += 1
                if unexpected >= max_unexpected:
                    raise CommunicationError(
                        f"Maximum number of unexpected answers from serial port "
                        f"{self.port} reached (question: '{question}', "
                        f"last answer: '{answer}')"
                    )
                self.logger.warning(
                    f"Unexpected answer '{answer}' to '{question}'. "
                    f"Re-sending command (try {unexpected} of {max_unexpected})"
                )
                time.sleep(UNEXPECTED_ANSWER_RETRY_DELAY)

    def __enter__(self) -> "SerialConnection":
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    @staticmethod
    def list_ports() -> list[str]:
        """List available serial ports."""
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]

    @staticmethod
    def scan_for_device(
        id_command: str = "?",
        expected_response: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 2.0,
    ) -> Optional[str]:
        """
        Scan available ports for a specific device.

        Args:
            id_command: Command to send for identification
            expected_response: Expected substring in response
            baudrate: Baud rate to use
            timeout: Timeout for each port

        Returns:
            Port name if found, None otherwise
        """
        for port in SerialConnection.list_ports():
            try:
                config = SerialConfig(baudrate=baudrate)
                conn = SerialConnection(port=port, config=config)
                conn.open()

                try:
                    response = conn.query(id_command, timeout=timeout)
                    if expected_response is None or expected_response in response:
                        conn.close()
                        return port
                except Exception:
                    pass

                conn.close()
            except Exception:
                continue

        return None


def parse_response(
    response: str,
    expected_prefix: str,
) -> tuple[bool, str, Optional[int]]:
    """
    Parse a device response.

    Args:
        response: Raw response string
        expected_prefix: Expected device ID prefix

    Returns:
        Tuple of (success, data, error_code)
    """
    if not response:
        return False, "", None

    # Check for expected prefix
    if expected_prefix and not response.startswith(expected_prefix):
        return False, response, None

    # Extract code/data after prefix
    data = response[len(expected_prefix) :]

    # Check for success (code 0) or data marker (!)
    if data.startswith("0"):
        return True, data[1:], 0
    elif data.startswith("!"):
        return True, data[1:], None
    elif data.startswith("h"):
        # Position response: "h<azi>,<zen>"
        return True, data[1:], None
    elif data and data[0].isdigit():
        # Error code
        try:
            error_code = int(data[0])
            return False, data[1:], error_code
        except ValueError:
            pass

    return True, data, None


def parse_position_response(response: str) -> tuple[Optional[int], Optional[int]]:
    """
    Parse tracker position response.

    Response format: "TRh<azimuth>,<zenith>"

    Args:
        response: Response string

    Returns:
        Tuple of (azimuth_steps, zenith_steps) or (None, None) on error
    """
    if "TRh" not in response:
        return None, None

    try:
        # Extract position part
        pos_str = response.split("TRh")[1].strip()
        parts = pos_str.split(",")

        if len(parts) >= 2:
            azimuth = int(parts[0])
            zenith = int(parts[1])
            return azimuth, zenith
    except (ValueError, IndexError):
        pass

    return None, None


def parse_sensor_value(
    response: str,
    expected_prefix: str,
    conversion_factor: float,
) -> Optional[float]:
    """
    Parse sensor reading response.

    Response format: "<prefix>!<value>"

    Args:
        response: Response string
        expected_prefix: Expected prefix (e.g., "HT")
        conversion_factor: Factor to divide raw value by

    Returns:
        Converted value or None on error
    """
    success, data, error_code = parse_response(response, expected_prefix)

    if not success or error_code is not None:
        return None

    try:
        raw_value = float(data)
        return raw_value / conversion_factor
    except ValueError:
        return None
