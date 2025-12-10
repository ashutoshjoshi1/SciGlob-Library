"""Temperature Controller interface for TETech devices."""

from typing import TYPE_CHECKING, Any, Optional

from sciglob.core.base import BaseDevice

if TYPE_CHECKING:
    from sciglob.config import TemperatureControllerConfig
from sciglob.core.connection import SerialConnection
from sciglob.core.exceptions import CommunicationError, ConnectionError, DeviceError
from sciglob.core.help_mixin import HelpMixin
from sciglob.core.protocols import TETECH_PROTOCOL, TIMING_CONFIG, SerialConfig
from sciglob.core.utils import dec2hex, get_checksum, hex2dec


class TemperatureController(BaseDevice, HelpMixin):
    """
    Temperature Controller interface for TETech devices.

    Supports TETech1 (16-bit) and TETech2 (32-bit) controllers.

    Protocol:
    - Commands: "*<cmd><hex_value><checksum>"
    - Response ends with "^"
    - Hex values are signed (two's complement)

    Example:
        >>> tc = TemperatureController(port="/dev/ttyUSB0", controller_type="TETech1")
        >>> tc.connect()
        >>> tc.set_temperature(25.0)
        >>> print(f"Current temp: {tc.get_temperature()}°C")
        >>> tc.disconnect()

    Help:
        >>> tc.help()              # Show full help
        >>> tc.list_methods()      # List all methods
    """

    # HelpMixin properties
    _device_name = "TemperatureController"
    _device_description = "TETech temperature controller interface"
    _supported_types = ["TETech1 (16-bit)", "TETech2 (32-bit)"]
    _default_config = {
        "baudrate": 9600,
        "conversion_factor": "10 (TETech1) or 100 (TETech2)",
        "protocol": "Hex with checksum, ends with ^",
    }
    _command_reference = {
        "1c": "Set temperature",
        "1d": "Set proportional bandwidth",
        "1e": "Set integral gain",
        "30/2d": "Enable output",
        "5065": "Read set temperature",
        "0161": "Read control sensor temp",
        "0261": "Read secondary sensor temp",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 1.0,
        name: str = "TempController",
        controller_type: str = "TETech1",
        config: Optional['TemperatureControllerConfig'] = None,
        serial_config: Optional[SerialConfig] = None,
    ):
        """
        Initialize the Temperature Controller.

        Args:
            port: Serial port path
            baudrate: Communication speed (default 9600)
            timeout: Command timeout
            name: Device name for logging
            controller_type: "TETech1" (16-bit) or "TETech2" (32-bit)
            config: TemperatureControllerConfig object
            serial_config: SerialConfig object for port settings
        """
        # If config object provided, use its values
        if config is not None:
            port = config.serial.port or port
            baudrate = config.serial.baudrate
            timeout = config.serial.timeout or timeout
            controller_type = config.controller_type

        # If serial_config provided, use its values
        if serial_config is not None:
            port = serial_config.port or port
            baudrate = serial_config.baudrate
            timeout = serial_config.timeout or timeout

        super().__init__(port=port, baudrate=baudrate, timeout=timeout, name=name)

        if controller_type not in ("TETech1", "TETech2"):
            raise ValueError("controller_type must be 'TETech1' or 'TETech2'")

        self._controller_type = controller_type
        self._protocol = TETECH_PROTOCOL[controller_type]
        self._nbits = self._protocol["nbits"]

    @property
    def controller_type(self) -> str:
        """Get the controller type."""
        return self._controller_type

    @property
    def nbits(self) -> int:
        """Get the bit width (16 or 32)."""
        return self._nbits

    def connect(self) -> None:
        """Connect to the temperature controller."""
        if self._connected:
            self.logger.warning("Already connected")
            return

        if self.port is None:
            raise ConnectionError("No port specified")

        try:
            config = SerialConfig(baudrate=self.baudrate)
            self._connection = SerialConnection(port=self.port, config=config)
            self._connection.open()

            # Verify connection
            if not self._verify_connection():
                raise DeviceError("Failed to verify temperature controller connection")

            self._connected = True
            self.logger.info(f"Connected to {self._controller_type} on {self.port}")

        except Exception as e:
            self.disconnect()
            raise ConnectionError(f"Failed to connect: {e}") from e

    def _verify_connection(self) -> bool:
        """Verify connection by sending ID query."""
        try:
            test_cmd = self._protocol["connection_test"]
            response = self._query(test_cmd)
            return len(response) > 0
        except Exception:
            return False

    def disconnect(self) -> None:
        """Disconnect from the temperature controller."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
            finally:
                self._connection = None
                self._connected = False

    def _build_command(self, cmd: str, value: Optional[int] = None) -> str:
        """
        Build a TETech command string.

        Args:
            cmd: Command code
            value: Optional value (will be converted to hex)

        Returns:
            Complete command string with checksum
        """
        if value is not None:
            hex_value = dec2hex(value, self._nbits)
            if self._controller_type == "TETech1":
                cmd_str = f"{cmd}{hex_value}"
            else:
                # TETech2 uses longer format
                cmd_str = f"00{cmd}{hex_value}"
        else:
            cmd_str = cmd

        checksum = get_checksum(cmd_str)
        return f"*{cmd_str}{checksum}"

    def _query(self, command: str) -> str:
        """
        Send command and get response.

        Args:
            command: Command string

        Returns:
            Response string (without end character)
        """
        if not self._connected or self._connection is None:
            raise DeviceError("Not connected")

        end_char = self._protocol["end_char"]

        # Send command
        self._connection.send_command(command, end_char="\r")

        # Read until end character
        response = self._connection.read_until(
            terminator=end_char.encode(),
            timeout=TIMING_CONFIG["standard_timeout"],
        )

        return response.decode().rstrip(end_char)

    def _parse_response(self, response: str, factor: float) -> float:
        """
        Parse hex response to float value.

        Args:
            response: Hex response string
            factor: Conversion factor

        Returns:
            Converted float value
        """
        # Check for error response
        if "XXXX" in response:
            raise CommunicationError("TETech error response")

        # Extract hex value (remove checksum - last 2 chars)
        if len(response) > 2:
            hex_value = response[:-2]
            dec_value = hex2dec(hex_value, self._nbits)
            return dec_value / factor

        return 0.0

    def send_command(self, command: str) -> Optional[str]:
        """Send raw command."""
        return self._query(command)

    def set_temperature(self, temperature: float) -> bool:
        """
        Set target temperature.

        Args:
            temperature: Target temperature in °C

        Returns:
            True if successful
        """
        write_cmds = self._protocol["write_commands"]
        cmd_info = write_cmds["ST"]

        value = int(temperature * cmd_info["factor"])
        command = self._build_command(cmd_info["cmd"], value)

        self.logger.info(f"Setting temperature to {temperature}°C")
        response = self._query(command)

        # Verify the response echoes the value
        return "XXXX" not in response

    def get_temperature(self) -> float:
        """
        Get control sensor temperature.

        Returns:
            Temperature in °C
        """
        read_cmds = self._protocol["read_commands"]
        cmd_info = read_cmds["T1"]

        command = f"*{cmd_info['cmd']}"
        response = self._query(command)

        return self._parse_response(response, cmd_info["factor"])

    def get_secondary_temperature(self) -> float:
        """
        Get secondary sensor temperature.

        Returns:
            Temperature in °C
        """
        read_cmds = self._protocol["read_commands"]
        cmd_info = read_cmds["T2"]

        command = f"*{cmd_info['cmd']}"
        response = self._query(command)

        return self._parse_response(response, cmd_info["factor"])

    def get_setpoint(self) -> float:
        """
        Get current temperature setpoint.

        Returns:
            Setpoint temperature in °C
        """
        read_cmds = self._protocol["read_commands"]
        cmd_info = read_cmds["ST"]

        command = f"*{cmd_info['cmd']}"
        response = self._query(command)

        return self._parse_response(response, cmd_info["factor"])

    def set_bandwidth(self, bandwidth: float) -> bool:
        """
        Set proportional bandwidth (PID parameter).

        Args:
            bandwidth: Bandwidth value

        Returns:
            True if successful
        """
        write_cmds = self._protocol["write_commands"]
        cmd_info = write_cmds["BW"]

        value = int(bandwidth * cmd_info["factor"])
        command = self._build_command(cmd_info["cmd"], value)

        response = self._query(command)
        return "XXXX" not in response

    def set_integral_gain(self, gain: float) -> bool:
        """
        Set integral gain (PID parameter).

        Args:
            gain: Integral gain value

        Returns:
            True if successful
        """
        write_cmds = self._protocol["write_commands"]
        cmd_info = write_cmds["IG"]

        value = int(gain * cmd_info["factor"])
        command = self._build_command(cmd_info["cmd"], value)

        response = self._query(command)
        return "XXXX" not in response

    def enable_output(self) -> bool:
        """
        Enable temperature control output.

        Returns:
            True if successful
        """
        write_cmds = self._protocol["write_commands"]
        cmd_info = write_cmds["EO"]

        command = self._build_command(cmd_info["cmd"], 1)
        response = self._query(command)
        return "XXXX" not in response

    def disable_output(self) -> bool:
        """
        Disable temperature control output.

        Returns:
            True if successful
        """
        write_cmds = self._protocol["write_commands"]
        cmd_info = write_cmds["EO"]

        command = self._build_command(cmd_info["cmd"], 0)
        response = self._query(command)
        return "XXXX" not in response

    def get_status(self) -> dict[str, Any]:
        """Get temperature controller status."""
        status = {
            "connected": self._connected,
            "controller_type": self._controller_type,
            "port": self.port,
        }

        if self._connected:
            try:
                status["temperature"] = self.get_temperature()
                status["setpoint"] = self.get_setpoint()
                status["secondary_temperature"] = self.get_secondary_temperature()
            except Exception as e:
                status["error"] = str(e)

        return status

