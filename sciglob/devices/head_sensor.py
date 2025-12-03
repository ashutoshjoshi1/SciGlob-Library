"""Head Sensor interface for SciGlob instruments."""

from typing import Optional, Dict, Any, List, Union
import logging
from sciglob.core.base import BaseDevice
from sciglob.core.connection import SerialConnection, parse_response, parse_sensor_value
from sciglob.core.protocols import (
    SerialConfig,
    DeviceType,
    HEAD_SENSOR_COMMANDS,
    SENSOR_CONVERSIONS,
    TIMING_CONFIG,
    get_error_message,
)
from sciglob.core.exceptions import (
    ConnectionError,
    DeviceError,
    SensorError,
    CommunicationError,
)
from sciglob.core.help_mixin import HelpMixin


class HeadSensor(BaseDevice, HelpMixin):
    """
    Head Sensor interface for SciGlob instruments.
    
    The Head Sensor is the main communication hub that connects to:
    - Tracker (motor controller for azimuth/zenith)
    - Filter Wheels (FW1, FW2)
    - Shadowband
    - Internal sensors (temperature, humidity, pressure)
    
    Supported types:
    - SciGlobHSN1: Basic head sensor
    - SciGlobHSN2: Extended sensors (temp, humidity, pressure)
    
    Example:
        >>> hs = HeadSensor(port="/dev/ttyUSB0")
        >>> hs.connect()
        >>> print(f"Device: {hs.device_id}")
        >>> if hs.sensor_type == "SciGlobHSN2":
        ...     print(f"Temperature: {hs.get_temperature()}°C")
        >>> hs.disconnect()
    
    Using context manager:
        >>> with HeadSensor(port="/dev/ttyUSB0") as hs:
        ...     print(hs.get_status())
        
    Help:
        >>> hs.help()              # Show full help
        >>> hs.help('move_to')     # Help for specific method
        >>> hs.list_methods()      # List all methods
    """
    
    # HelpMixin properties
    _device_name = "HeadSensor"
    _device_description = "Main communication hub for SciGlob instruments"
    _supported_types = ["SciGlobHSN1", "SciGlobHSN2"]
    _default_config = {
        "baudrate": 9600,
        "bytesize": 8,
        "parity": "N",
        "stopbits": 1,
        "timeout": 1.0,
        "tracker_type": "Directed Perceptions",
        "degrees_per_step": 0.01,
        "motion_limits": "[0, 90, 0, 360]",
        "home_position": "[0.0, 180.0]",
    }
    _command_reference = {
        "?": "Get device ID",
        "TRw": "Get tracker position",
        "TRb<az>,<zen>": "Move tracker (both axes)",
        "TRt<steps>": "Move zenith (tilt)",
        "TRp<steps>": "Move azimuth (pan)",
        "TRr": "Reset tracker",
        "TRY": "Power cycle tracker",
        "F1<1-9>": "Set filter wheel 1 position",
        "F2<1-9>": "Set filter wheel 2 position",
        "SB<pos>": "Set shadowband position",
        "HTt?": "Read temperature (HSN2)",
        "HTh?": "Read humidity (HSN2)",
        "HTp?": "Read pressure (HSN2)",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 1.0,
        name: str = "HeadSensor",
        sensor_type: Optional[str] = None,
        fw1_filters: Optional[List[str]] = None,
        fw2_filters: Optional[List[str]] = None,
        tracker_type: str = "Directed Perceptions",
        degrees_per_step: float = 0.01,
        motion_limits: Optional[List[float]] = None,
        home_position: Optional[List[float]] = None,
        config: Optional['HeadSensorConfig'] = None,
        serial_config: Optional[SerialConfig] = None,
    ):
        """
        Initialize the Head Sensor.
        
        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0' or 'COM3')
            baudrate: Communication speed (default 9600)
            timeout: Command timeout in seconds
            name: Device name for logging
            sensor_type: Expected sensor type ('SciGlobHSN1' or 'SciGlobHSN2')
            fw1_filters: List of 9 filter names for Filter Wheel 1
            fw2_filters: List of 9 filter names for Filter Wheel 2
            tracker_type: Tracker type ('Directed Perceptions' or 'LuftBlickTR1')
            degrees_per_step: Tracker resolution (typically 0.01°/step)
            motion_limits: [zenith_min, zenith_max, azimuth_min, azimuth_max]
            home_position: [zenith_home, azimuth_home] in degrees
            config: HeadSensorConfig object (overrides other parameters)
            serial_config: SerialConfig object for port settings
        """
        # If config object provided, use its values
        if config is not None:
            port = config.serial.port or port
            baudrate = config.serial.baudrate
            timeout = config.serial.timeout or timeout
            sensor_type = config.sensor_type or sensor_type
            fw1_filters = config.fw1_filters
            fw2_filters = config.fw2_filters
            tracker_type = config.tracker_type
            degrees_per_step = config.degrees_per_step
            motion_limits = config.motion_limits
            home_position = config.home_position
        
        # If serial_config provided, use its values
        if serial_config is not None:
            port = serial_config.port or port
            baudrate = serial_config.baudrate
            timeout = serial_config.timeout or timeout
        
        super().__init__(port=port, baudrate=baudrate, timeout=timeout, name=name)
        
        self._expected_sensor_type = sensor_type
        self._sensor_type: Optional[str] = None
        self._device_id: Optional[str] = None
        
        # Filter wheel configuration
        self._fw1_filters = fw1_filters or ["OPEN"] * 9
        self._fw2_filters = fw2_filters or ["OPEN"] * 9
        
        # Tracker configuration
        self._tracker_type = tracker_type
        self._degrees_per_step = degrees_per_step
        self._motion_limits = motion_limits or [0, 90, 0, 360]  # [zen_min, zen_max, azi_min, azi_max]
        self._home_position = home_position or [0.0, 180.0]  # [zenith_home, azimuth_home]
        
        # Child device references (lazy initialization)
        self._tracker = None
        self._filter_wheel_1 = None
        self._filter_wheel_2 = None
        self._shadowband = None

    @property
    def device_id(self) -> Optional[str]:
        """Get the device identification string."""
        return self._device_id

    @property
    def sensor_type(self) -> Optional[str]:
        """Get the detected sensor type."""
        return self._sensor_type

    @property
    def tracker_type(self) -> str:
        """Get the tracker type."""
        return self._tracker_type

    @property
    def degrees_per_step(self) -> float:
        """Get the tracker resolution."""
        return self._degrees_per_step

    @property
    def motion_limits(self) -> List[float]:
        """Get motion limits [zen_min, zen_max, azi_min, azi_max]."""
        return self._motion_limits.copy()

    @property
    def home_position(self) -> List[float]:
        """Get home position [zenith_home, azimuth_home]."""
        return self._home_position.copy()

    @property
    def fw1_filters(self) -> List[str]:
        """Get Filter Wheel 1 filter names."""
        return self._fw1_filters.copy()

    @property
    def fw2_filters(self) -> List[str]:
        """Get Filter Wheel 2 filter names."""
        return self._fw2_filters.copy()

    @property
    def tracker(self):
        """
        Get the Tracker interface.
        
        Lazy initialization - creates Tracker on first access.
        """
        if self._tracker is None:
            from sciglob.devices.tracker import Tracker
            self._tracker = Tracker(self)
        return self._tracker

    @property
    def filter_wheel_1(self):
        """Get Filter Wheel 1 interface."""
        if self._filter_wheel_1 is None:
            from sciglob.devices.filter_wheel import FilterWheel
            self._filter_wheel_1 = FilterWheel(self, wheel_id=1)
        return self._filter_wheel_1

    @property
    def filter_wheel_2(self):
        """Get Filter Wheel 2 interface."""
        if self._filter_wheel_2 is None:
            from sciglob.devices.filter_wheel import FilterWheel
            self._filter_wheel_2 = FilterWheel(self, wheel_id=2)
        return self._filter_wheel_2

    @property
    def shadowband(self):
        """Get Shadowband interface."""
        if self._shadowband is None:
            from sciglob.devices.shadowband import Shadowband
            self._shadowband = Shadowband(self)
        return self._shadowband

    def connect(self) -> None:
        """
        Connect to the Head Sensor.
        
        Establishes serial connection and queries device identification.
        
        Raises:
            ConnectionError: If connection fails
            DeviceError: If device identification fails
        """
        if self._connected:
            self.logger.warning("Already connected to head sensor")
            return
            
        if self.port is None:
            # Try to auto-detect port
            self.port = self._scan_for_head_sensor()
            if self.port is None:
                raise ConnectionError("No head sensor found on any port")
                
        try:
            config = SerialConfig(baudrate=self.baudrate)
            self._connection = SerialConnection(port=self.port, config=config)
            self._connection.open()
            
            # Query device identification
            self._query_device_id()
            
            self._connected = True
            self.logger.info(
                f"Connected to {self._sensor_type} on {self.port}"
            )
            
        except Exception as e:
            self.disconnect()
            raise ConnectionError(f"Failed to connect to head sensor: {e}") from e

    def _scan_for_head_sensor(self) -> Optional[str]:
        """Scan ports for a head sensor device."""
        self.logger.info("Scanning for head sensor...")
        return SerialConnection.scan_for_device(
            id_command="?",
            expected_response="SciGlob",
            baudrate=self.baudrate,
            timeout=TIMING_CONFIG["standard_timeout"],
        )

    def _query_device_id(self) -> None:
        """Query and parse device identification."""
        protocol = HEAD_SENSOR_COMMANDS["id"]
        
        response = self._connection.query(
            command=protocol.command,
            end_char=protocol.end_char,
            response_end_char=protocol.response_end_char,
            timeout=protocol.timeout,
        )
        
        if not response:
            raise DeviceError("No response to ID query")
            
        self._device_id = response.strip()
        
        # Determine sensor type
        if "SciGlobHSN2" in self._device_id:
            self._sensor_type = DeviceType.SCIGLOB_HSN2.value
        elif "SciGlobHSN1" in self._device_id or "SciGlob" in self._device_id:
            self._sensor_type = DeviceType.SCIGLOB_HSN1.value
        else:
            self._sensor_type = self._device_id
            
        # Validate against expected type if specified
        if self._expected_sensor_type:
            if self._expected_sensor_type not in self._sensor_type:
                raise DeviceError(
                    f"Expected {self._expected_sensor_type}, got {self._sensor_type}"
                )

    def disconnect(self) -> None:
        """Disconnect from the Head Sensor."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
            finally:
                self._connection = None
                self._connected = False
                self._tracker = None
                self._filter_wheel_1 = None
                self._filter_wheel_2 = None
                self._shadowband = None
                self.logger.info("Disconnected from head sensor")

    def send_command(self, command: str, timeout: Optional[float] = None) -> str:
        """
        Send a command to the Head Sensor.
        
        Args:
            command: Command string (without end character)
            timeout: Response timeout (uses default if None)
            
        Returns:
            Response string
            
        Raises:
            DeviceError: If not connected
            CommunicationError: If command fails
        """
        if not self._connected or self._connection is None:
            raise DeviceError("Not connected to head sensor")
            
        timeout = timeout or self.timeout
        
        try:
            response = self._connection.query(
                command=command,
                end_char="\r",
                response_end_char="\n",
                timeout=timeout,
            )
            return response
        except Exception as e:
            raise CommunicationError(f"Command '{command}' failed: {e}")

    def get_id(self) -> str:
        """
        Get device identification string.
        
        Returns:
            Device ID string
        """
        if not self._connected:
            raise DeviceError("Not connected")
            
        response = self.send_command("?")
        return response.strip()

    def get_temperature(self) -> float:
        """
        Read head sensor temperature (SciGlobHSN2 only).
        
        Returns:
            Temperature in °C
            
        Raises:
            SensorError: If sensor type doesn't support temperature
        """
        if self._sensor_type != DeviceType.SCIGLOB_HSN2.value:
            raise SensorError(
                f"Temperature reading not supported on {self._sensor_type}"
            )
            
        protocol = HEAD_SENSOR_COMMANDS["temperature"]
        response = self.send_command(protocol.command)
        
        value = parse_sensor_value(
            response,
            protocol.expected_prefix,
            SENSOR_CONVERSIONS["temperature"]["factor"],
        )
        
        if value is None:
            return SENSOR_CONVERSIONS["temperature"]["error_value"]
        return value

    def get_humidity(self) -> float:
        """
        Read head sensor humidity (SciGlobHSN2 only).
        
        Returns:
            Relative humidity in %
            
        Raises:
            SensorError: If sensor type doesn't support humidity
        """
        if self._sensor_type != DeviceType.SCIGLOB_HSN2.value:
            raise SensorError(
                f"Humidity reading not supported on {self._sensor_type}"
            )
            
        protocol = HEAD_SENSOR_COMMANDS["humidity"]
        response = self.send_command(protocol.command)
        
        value = parse_sensor_value(
            response,
            protocol.expected_prefix,
            SENSOR_CONVERSIONS["humidity"]["factor"],
        )
        
        if value is None:
            return SENSOR_CONVERSIONS["humidity"]["error_value"]
        return value

    def get_pressure(self) -> float:
        """
        Read head sensor pressure (SciGlobHSN2 only).
        
        Returns:
            Pressure in mbar
            
        Raises:
            SensorError: If sensor type doesn't support pressure
        """
        if self._sensor_type != DeviceType.SCIGLOB_HSN2.value:
            raise SensorError(
                f"Pressure reading not supported on {self._sensor_type}"
            )
            
        protocol = HEAD_SENSOR_COMMANDS["pressure"]
        response = self.send_command(protocol.command)
        
        value = parse_sensor_value(
            response,
            protocol.expected_prefix,
            SENSOR_CONVERSIONS["pressure"]["factor"],
        )
        
        if value is None:
            return SENSOR_CONVERSIONS["pressure"]["error_value"]
        return value

    def get_all_sensors(self) -> Dict[str, float]:
        """
        Read all available sensor values.
        
        Returns:
            Dictionary with sensor readings
        """
        readings = {}
        
        if self._sensor_type == DeviceType.SCIGLOB_HSN2.value:
            try:
                readings["temperature"] = self.get_temperature()
            except Exception as e:
                self.logger.error(f"Temperature read failed: {e}")
                readings["temperature"] = SENSOR_CONVERSIONS["temperature"]["error_value"]
                
            try:
                readings["humidity"] = self.get_humidity()
            except Exception as e:
                self.logger.error(f"Humidity read failed: {e}")
                readings["humidity"] = SENSOR_CONVERSIONS["humidity"]["error_value"]
                
            try:
                readings["pressure"] = self.get_pressure()
            except Exception as e:
                self.logger.error(f"Pressure read failed: {e}")
                readings["pressure"] = SENSOR_CONVERSIONS["pressure"]["error_value"]
                
        return readings

    def power_reset(self, device: str) -> bool:
        """
        Power reset a connected device.
        
        Args:
            device: Device identifier:
                - 'TR' or 'tracker': Tracker
                - 'S1': Spectrometer 1
                - 'S2': Spectrometer 2
                
        Returns:
            True if successful
        """
        # Map device names
        device_map = {
            "tracker": "TR",
            "TR": "TR",
            "spectrometer1": "S1",
            "S1": "S1",
            "spectrometer2": "S2",
            "S2": "S2",
        }
        
        device_id = device_map.get(device, device)
        
        # Send power reset command
        if device_id == "TR":
            response = self.send_command("TRs", timeout=TIMING_CONFIG["power_reset_timeout"])
            return "TR0" in response
        else:
            # Generic power reset command format
            response = self.send_command(f"{device_id}s")
            return f"{device_id}0" in response

    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status of the Head Sensor.
        
        Returns:
            Dictionary with status information
        """
        status = {
            "connected": self._connected,
            "port": self.port,
            "device_id": self._device_id,
            "sensor_type": self._sensor_type,
            "tracker_type": self._tracker_type,
        }
        
        if self._connected and self._sensor_type == DeviceType.SCIGLOB_HSN2.value:
            status["sensors"] = self.get_all_sensors()
            
        return status

