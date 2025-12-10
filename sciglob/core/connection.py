"""Serial connection utilities for device communication."""

import logging
import time
from typing import Optional

import serial
import serial.tools.list_ports

from sciglob.core.exceptions import ConnectionError
from sciglob.core.protocols import TIMING_CONFIG, SerialConfig


class SerialConnection:
    """
    Serial port communication handler.

    Implements the question-answer protocol used by SciGlob devices.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        config: Optional[SerialConfig] = None,
    ):
        """
        Initialize serial connection.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0' or 'COM3')
            config: Serial configuration parameters
        """
        self.port = port
        self.config = config or SerialConfig()
        self._serial: Optional[serial.Serial] = None
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
        """
        if self.is_open:
            self.logger.warning(f"Port {self.port} is already open")
            return

        if self.port is None:
            raise ConnectionError("No port specified")

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
                dsrdtr=self.config.dsrdtr,
            )
            self.logger.info(f"Opened serial port {self.port} at {self.config.baudrate} baud")
        except serial.SerialException as e:
            raise ConnectionError(f"Failed to open port {self.port}: {e}") from e

    def close(self) -> None:
        """Close the serial connection."""
        if self._serial is not None:
            try:
                self._serial.close()
                self.logger.info(f"Closed serial port {self.port}")
            except Exception as e:
                self.logger.error(f"Error closing port {self.port}: {e}")
            finally:
                self._serial = None

    def flush_buffers(self) -> None:
        """Flush both input and output buffers."""
        if self.is_open:
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

    def read_buffer(self) -> bytes:
        """Read all available data from input buffer."""
        if not self.is_open:
            raise ConnectionError("Serial port is not open")

        data = b""
        while self._serial.in_waiting > 0:
            data += self._serial.read(self._serial.in_waiting)
            time.sleep(0.01)
        return data

    def write(self, data: bytes) -> int:
        """
        Write data to the serial port.

        Args:
            data: Bytes to write

        Returns:
            Number of bytes written
        """
        if not self.is_open:
            raise ConnectionError("Serial port is not open")

        self.logger.debug(f"TX: {data!r}")
        return self._serial.write(data)

    def read(self, size: int = 1, timeout: Optional[float] = None) -> bytes:
        """
        Read data from the serial port.

        Args:
            size: Number of bytes to read
            timeout: Read timeout in seconds

        Returns:
            Bytes read from port
        """
        if not self.is_open:
            raise ConnectionError("Serial port is not open")

        if timeout is not None:
            original_timeout = self._serial.timeout
            self._serial.timeout = timeout

        try:
            data = self._serial.read(size)
            self.logger.debug(f"RX: {data!r}")
            return data
        finally:
            if timeout is not None:
                self._serial.timeout = original_timeout

    def read_until(
        self,
        terminator: bytes = b'\n',
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
        if not self.is_open:
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
        end_char: str = '\r',
        encoding: str = 'ascii',
    ) -> None:
        """
        Send a command string.

        Args:
            command: Command to send
            end_char: End character to append
            encoding: String encoding
        """
        data = (command + end_char).encode(encoding)
        self.flush_buffers()
        self.write(data)

    def query(
        self,
        command: str,
        end_char: str = '\r',
        response_end_char: str = '\n',
        timeout: float = 1.0,
        encoding: str = 'ascii',
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
        self.send_command(command, end_char, encoding)

        # Small delay for device to process
        time.sleep(TIMING_CONFIG["inter_command_delay"])

        response = self.read_until(
            terminator=response_end_char.encode(encoding),
            timeout=timeout,
        )

        return response.decode(encoding).strip()

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
    data = response[len(expected_prefix):]

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
