"""Humidity Sensor interface for HDC2080EVM."""

from typing import TYPE_CHECKING, Any, Optional

from sciglob.core.base import BaseDevice

if TYPE_CHECKING:
    from sciglob.config import HumiditySensorConfig
from sciglob.core.connection import SerialConnection
from sciglob.core.exceptions import ConnectionError, DeviceError, SensorError
from sciglob.core.help_mixin import HelpMixin
from sciglob.core.protocols import HDC2080_PROTOCOL, TIMING_CONFIG, SerialConfig
from sciglob.core.utils import parse_hdc2080_humidity, parse_hdc2080_temperature


class HumiditySensor(BaseDevice, HelpMixin):
    """
    Humidity Sensor interface for HDC2080EVM.

    Protocol:
    - ID query: "?" -> "S,HDC2080EVM,..."
    - Initialize: "4" -> "stream stop"
    - Temperature: "1" -> 4-char hex (little-endian)
    - Humidity: "2" -> 4-char hex (little-endian)

    Example:
        >>> hs = HumiditySensor(port="/dev/ttyUSB0")
        >>> hs.connect()
        >>> print(f"Temperature: {hs.get_temperature()}°C")
        >>> print(f"Humidity: {hs.get_humidity()}%")
        >>> hs.disconnect()

    Help:
        >>> hs.help()              # Show full help
    """

    # HelpMixin properties
    _device_name = "HumiditySensor"
    _device_description = "HDC2080EVM humidity and temperature sensor"
    _supported_types = ["HDC2080EVM"]
    _default_config = {
        "baudrate": 9600,
        "data_format": "4-char little-endian hex",
    }
    _command_reference = {
        "?": "Get device ID",
        "4": "Initialize (stop streaming)",
        "1": "Read temperature",
        "2": "Read humidity",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 1.0,
        name: str = "HumiditySensor",
        config: Optional["HumiditySensorConfig"] = None,
        serial_config: Optional[SerialConfig] = None,
    ):
        """
        Initialize the Humidity Sensor.

        Args:
            port: Serial port path
            baudrate: Communication speed (default 9600)
            timeout: Command timeout
            name: Device name for logging
            config: HumiditySensorConfig object
            serial_config: SerialConfig object for port settings
        """
        # If config object provided, use its values
        if config is not None:
            port = config.serial.port or port
            baudrate = config.serial.baudrate
            timeout = config.serial.timeout or timeout

        # If serial_config provided, use its values
        if serial_config is not None:
            port = serial_config.port or port
            baudrate = serial_config.baudrate
            timeout = serial_config.timeout or timeout

        super().__init__(port=port, baudrate=baudrate, timeout=timeout, name=name)
        self._protocol = HDC2080_PROTOCOL
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if the sensor has been initialized."""
        return self._initialized

    def connect(self) -> None:
        """Connect to the humidity sensor."""
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
                raise DeviceError("Failed to verify HDC2080EVM connection")

            # Initialize sensor
            self.initialize()

            self._connected = True
            self.logger.info(f"Connected to HDC2080EVM on {self.port}")

        except Exception as e:
            self.disconnect()
            raise ConnectionError(f"Failed to connect: {e}") from e

    def _verify_connection(self) -> bool:
        """Verify connection by sending ID query."""
        try:
            response = self._query(self._protocol["id_command"])
            return self._protocol["expected_id"] in response
        except Exception:
            return False

    def disconnect(self) -> None:
        """Disconnect from the humidity sensor."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
            finally:
                self._connection = None
                self._connected = False
                self._initialized = False

    def _query(self, command: str) -> str:
        """Send command and get response."""
        if self._connection is None:
            raise DeviceError("Not connected")

        end_char = self._protocol["end_char"]
        response_end = self._protocol["response_end_char"]

        self._connection.send_command(command, end_char=end_char)

        response = self._connection.read_until(
            terminator=response_end.encode(),
            timeout=TIMING_CONFIG["sensor_reading_timeout"],
        )

        return response.decode().strip()

    def send_command(self, command: str) -> Optional[str]:
        """Send raw command."""
        return self._query(command)

    def initialize(self) -> bool:
        """
        Initialize the sensor (stop any streaming).

        Returns:
            True if successful
        """
        try:
            response = self._query(self._protocol["initialize_command"])
            self._initialized = "stream stop" in response.lower()
            return self._initialized
        except Exception as e:
            self.logger.error(f"Failed to initialize: {e}")
            return False

    def get_temperature(self) -> float:
        """
        Get temperature reading.

        Returns:
            Temperature in °C

        Raises:
            SensorError: If reading fails
        """
        if not self._connected:
            raise DeviceError("Not connected")

        try:
            response = self._query(self._protocol["temperature_command"])

            # Response should be 4-char hex
            if len(response) >= 4:
                # Extract just the hex part
                hex_value = response[:4]
                return parse_hdc2080_temperature(hex_value)
            else:
                raise SensorError(f"Invalid temperature response: {response}")

        except SensorError:
            raise
        except Exception as e:
            raise SensorError(f"Temperature reading failed: {e}") from e

    def get_humidity(self) -> float:
        """
        Get humidity reading.

        Returns:
            Relative humidity in %

        Raises:
            SensorError: If reading fails
        """
        if not self._connected:
            raise DeviceError("Not connected")

        try:
            response = self._query(self._protocol["humidity_command"])

            # Response should be 4-char hex
            if len(response) >= 4:
                hex_value = response[:4]
                return parse_hdc2080_humidity(hex_value)
            else:
                raise SensorError(f"Invalid humidity response: {response}")

        except SensorError:
            raise
        except Exception as e:
            raise SensorError(f"Humidity reading failed: {e}") from e

    def get_readings(self) -> dict[str, float]:
        """
        Get both temperature and humidity readings.

        Returns:
            Dictionary with 'temperature' and 'humidity' keys
        """
        return {
            "temperature": self.get_temperature(),
            "humidity": self.get_humidity(),
        }

    def get_status(self) -> dict[str, Any]:
        """Get humidity sensor status."""
        status = {
            "connected": self._connected,
            "initialized": self._initialized,
            "port": self.port,
        }

        if self._connected:
            try:
                status["readings"] = self.get_readings()
            except Exception as e:
                status["error"] = str(e)

        return status
