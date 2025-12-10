"""Hardware configuration classes for SciGlob devices.

This module provides configuration management for all hardware devices,
including default serial port settings based on Blick reference specifications.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import yaml


@dataclass
class SerialConfig:
    """Serial port configuration settings.

    Attributes:
        port: Serial port name (e.g., 'COM1', '/dev/ttyUSB0')
        baudrate: Communication speed in bits per second
        bytesize: Number of data bits (5, 6, 7, or 8)
        parity: Parity checking ('N', 'E', 'O', 'M', 'S')
        stopbits: Number of stop bits (1, 1.5, or 2)
        timeout: Read timeout in seconds (0 = non-blocking)
        write_timeout: Write timeout in seconds
        xonxoff: Enable software flow control
        rtscts: Enable hardware (RTS/CTS) flow control
        dsrdtr: Enable hardware (DSR/DTR) flow control

    Example:
        >>> config = SerialConfig(port='COM3', baudrate=9600)
        >>> print(config)
    """
    port: Optional[str] = None
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = 'N'
    stopbits: float = 1
    timeout: float = 0
    write_timeout: float = 20.0
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for pyserial."""
        return {
            'port': self.port,
            'baudrate': self.baudrate,
            'bytesize': self.bytesize,
            'parity': self.parity,
            'stopbits': self.stopbits,
            'timeout': self.timeout,
            'write_timeout': self.write_timeout,
            'xonxoff': self.xonxoff,
            'rtscts': self.rtscts,
            'dsrdtr': self.dsrdtr,
        }

    @classmethod
    def help(cls) -> str:
        """Return help text for SerialConfig."""
        return """
SerialConfig - Serial Port Configuration
=========================================

Configuration class for RS-232 serial communication settings.

Default Values (Blick Reference):
---------------------------------
  baudrate    : 9600      - Bits per second
  bytesize    : 8         - Data bits
  parity      : 'N'       - No parity
  stopbits    : 1         - Stop bits
  timeout     : 0         - Read timeout (0 = non-blocking)
  write_timeout: 20.0     - Write timeout in seconds

Usage:
------
  from sciglob.config import SerialConfig

  # Create with defaults
  config = SerialConfig(port='/dev/ttyUSB0')

  # Create with custom settings
  config = SerialConfig(
      port='COM3',
      baudrate=115200,
      timeout=1.0
  )

  # Apply to device
  from sciglob import HeadSensor
  hs = HeadSensor(serial_config=config)
"""


@dataclass
class HeadSensorConfig:
    """Configuration for Head Sensor devices.

    Attributes:
        serial: Serial port configuration
        sensor_type: Expected sensor type ('SciGlobHSN1' or 'SciGlobHSN2')
        tracker_type: Tracker type ('Directed Perceptions' or 'LuftBlickTR1')
        degrees_per_step: Motor resolution (default 0.01 = 100 steps/degree)
        motion_limits: [zenith_min, zenith_max, azimuth_min, azimuth_max]
        home_position: [zenith_home, azimuth_home] in degrees
        fw1_filters: Filter names for Filter Wheel 1 (9 positions)
        fw2_filters: Filter names for Filter Wheel 2 (9 positions)
        shadowband_resolution: Shadowband degrees per step
        shadowband_ratio: Shadowband offset/radius ratio
    """
    serial: SerialConfig = field(default_factory=SerialConfig)
    sensor_type: Optional[str] = None
    tracker_type: str = "Directed Perceptions"
    degrees_per_step: float = 0.01
    motion_limits: list[float] = field(default_factory=lambda: [0, 90, 0, 360])
    home_position: list[float] = field(default_factory=lambda: [0.0, 180.0])
    fw1_filters: list[str] = field(default_factory=lambda: ["OPEN"] * 9)
    fw2_filters: list[str] = field(default_factory=lambda: ["OPEN"] * 9)
    shadowband_resolution: float = 0.36
    shadowband_ratio: float = 0.5

    @classmethod
    def help(cls) -> str:
        """Return help text for HeadSensorConfig."""
        return """
HeadSensorConfig - Head Sensor Configuration
=============================================

Configuration class for SciGlob Head Sensor devices.

Supported Sensor Types:
-----------------------
  - SciGlobHSN1 : Original head sensor
  - SciGlobHSN2 : Enhanced with temperature, humidity, pressure sensors

Supported Tracker Types:
------------------------
  - Directed Perceptions : Standard PTU tracker
  - LuftBlickTR1        : Oriental Motors with magnetic encoders

Default Values:
---------------
  baudrate         : 9600
  degrees_per_step : 0.01 (100 steps per degree)
  motion_limits    : [0, 90, 0, 360] degrees
  home_position    : [0.0, 180.0] degrees (zenith, azimuth)

Usage:
------
  from sciglob.config import HeadSensorConfig, SerialConfig

  config = HeadSensorConfig(
      serial=SerialConfig(port='COM3', baudrate=9600),
      tracker_type='LuftBlickTR1',
      motion_limits=[0, 85, 0, 360],
      fw1_filters=['OPEN', 'U340', 'BP300', 'LPNIR', 'ND1', 'ND2', 'ND3', 'ND4', 'OPAQUE'],
  )

  from sciglob import HeadSensor
  hs = HeadSensor(config=config)
"""


@dataclass
class TemperatureControllerConfig:
    """Configuration for Temperature Controller devices.

    Attributes:
        serial: Serial port configuration
        controller_type: 'TETech1' (16-bit) or 'TETech2' (32-bit)
        set_temperature: Initial target temperature
        proportional_bandwidth: PID P parameter
        integral_gain: PID I parameter
    """
    serial: SerialConfig = field(default_factory=SerialConfig)
    controller_type: str = "TETech1"
    set_temperature: float = 25.0
    proportional_bandwidth: float = 10.0
    integral_gain: float = 0.5

    @classmethod
    def help(cls) -> str:
        """Return help text for TemperatureControllerConfig."""
        return """
TemperatureControllerConfig - Temperature Controller Configuration
===================================================================

Configuration class for TETech temperature controllers.

Supported Controller Types:
---------------------------
  - TETech1 : 16-bit protocol, conversion factor = 10
  - TETech2 : 32-bit protocol, conversion factor = 100

Default Values:
---------------
  baudrate             : 9600
  controller_type      : TETech1
  set_temperature      : 25.0°C
  proportional_bandwidth: 10.0
  integral_gain        : 0.5

Protocol Notes:
---------------
  Commands use hex encoding with checksum:
  - Format: *[address][command][value][checksum]^
  - Checksum: Sum of hex character ASCII values mod 256

Usage:
------
  from sciglob.config import TemperatureControllerConfig, SerialConfig

  config = TemperatureControllerConfig(
      serial=SerialConfig(port='COM4'),
      controller_type='TETech2',
      set_temperature=20.0,
  )

  from sciglob import TemperatureController
  tc = TemperatureController(config=config)
"""


@dataclass
class HumiditySensorConfig:
    """Configuration for Humidity Sensor devices.

    Attributes:
        serial: Serial port configuration
    """
    serial: SerialConfig = field(default_factory=SerialConfig)

    @classmethod
    def help(cls) -> str:
        """Return help text for HumiditySensorConfig."""
        return """
HumiditySensorConfig - Humidity Sensor Configuration
=====================================================

Configuration class for HDC2080EVM humidity sensors.

Supported Sensors:
------------------
  - HDC2080EVM : Texas Instruments humidity/temperature sensor EVM

Default Values:
---------------
  baudrate : 9600

Data Format:
------------
  - Humidity: Little-endian hex, value / 65536 * 100 = %RH
  - Temperature: Little-endian hex, (value / 65536) * 165 - 40 = °C

Usage:
------
  from sciglob.config import HumiditySensorConfig, SerialConfig

  config = HumiditySensorConfig(
      serial=SerialConfig(port='COM5', baudrate=9600)
  )

  from sciglob import HumiditySensor
  hs = HumiditySensor(config=config)
"""


@dataclass
class GPSConfig:
    """Configuration for GPS/Positioning System devices.

    Attributes:
        serial: Serial port configuration
        system_type: 'GlobalSat' (GPS only) or 'Novatel' (GPS+Gyro)
    """
    serial: SerialConfig = field(default_factory=SerialConfig)
    system_type: str = "GlobalSat"

    @classmethod
    def help(cls) -> str:
        """Return help text for GPSConfig."""
        return """
GPSConfig - GPS/Positioning System Configuration
=================================================

Configuration class for GPS receivers and positioning systems.

Supported Systems:
------------------
  - GlobalSat : Simple GPS receiver, NMEA protocol (GPGGA)
  - Novatel   : GPS + Inertial Navigation, INSPVA output

Default Values:
---------------
  baudrate    : 9600
  system_type : GlobalSat

Output Formats:
---------------
  GlobalSat (GPGGA):
    $GPGGA,time,lat,N/S,lon,E/W,quality,satellites,hdop,alt,M,...

  Novatel (INSPVA):
    < week seconds lat lon alt vel_n vel_e vel_u roll pitch yaw status

Usage:
------
  from sciglob.config import GPSConfig, SerialConfig

  # GlobalSat GPS
  config = GPSConfig(
      serial=SerialConfig(port='COM6'),
      system_type='GlobalSat'
  )

  # Novatel GPS+Gyro
  config = GPSConfig(
      serial=SerialConfig(port='COM7', baudrate=115200),
      system_type='Novatel'
  )
"""


@dataclass
class HardwareConfig:
    """Complete hardware configuration for all devices.

    This class holds configuration for the entire hardware setup.

    Attributes:
        head_sensor: Head Sensor configuration
        temperature_controller_1: First temperature controller config
        temperature_controller_2: Second temperature controller config
        humidity_sensor: Humidity sensor configuration
        gps: GPS/Positioning system configuration
    """
    head_sensor: HeadSensorConfig = field(default_factory=HeadSensorConfig)
    temperature_controller_1: TemperatureControllerConfig = field(
        default_factory=lambda: TemperatureControllerConfig(
            controller_type="TETech1"
        )
    )
    temperature_controller_2: TemperatureControllerConfig = field(
        default_factory=lambda: TemperatureControllerConfig(
            controller_type="TETech2"
        )
    )
    humidity_sensor: HumiditySensorConfig = field(default_factory=HumiditySensorConfig)
    gps: GPSConfig = field(default_factory=GPSConfig)

    @classmethod
    def from_yaml(cls, filepath: str) -> 'HardwareConfig':
        """Load configuration from YAML file.

        Args:
            filepath: Path to YAML configuration file

        Returns:
            HardwareConfig instance
        """
        with open(filepath) as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'HardwareConfig':
        """Create configuration from dictionary."""
        config = cls()

        if 'head_sensor' in data:
            hs = data['head_sensor']
            if 'serial' in hs:
                config.head_sensor.serial = SerialConfig(**hs['serial'])
            for key in ['sensor_type', 'tracker_type', 'degrees_per_step',
                       'motion_limits', 'home_position', 'fw1_filters', 'fw2_filters']:
                if key in hs:
                    setattr(config.head_sensor, key, hs[key])

        for tc_key in ['temperature_controller_1', 'temperature_controller_2']:
            if tc_key in data:
                tc = data[tc_key]
                tc_config = getattr(config, tc_key)
                if 'serial' in tc:
                    tc_config.serial = SerialConfig(**tc['serial'])
                for key in ['controller_type', 'set_temperature',
                           'proportional_bandwidth', 'integral_gain']:
                    if key in tc:
                        setattr(tc_config, key, tc[key])

        if 'humidity_sensor' in data:
            hs = data['humidity_sensor']
            if 'serial' in hs:
                config.humidity_sensor.serial = SerialConfig(**hs['serial'])

        if 'gps' in data:
            gps = data['gps']
            if 'serial' in gps:
                config.gps.serial = SerialConfig(**gps['serial'])
            if 'system_type' in gps:
                config.gps.system_type = gps['system_type']

        return config

    def to_yaml(self, filepath: str) -> None:
        """Save configuration to YAML file."""
        data = {
            'head_sensor': {
                'serial': self.head_sensor.serial.to_dict(),
                'sensor_type': self.head_sensor.sensor_type,
                'tracker_type': self.head_sensor.tracker_type,
                'degrees_per_step': self.head_sensor.degrees_per_step,
                'motion_limits': self.head_sensor.motion_limits,
                'home_position': self.head_sensor.home_position,
                'fw1_filters': self.head_sensor.fw1_filters,
                'fw2_filters': self.head_sensor.fw2_filters,
            },
            'temperature_controller_1': {
                'serial': self.temperature_controller_1.serial.to_dict(),
                'controller_type': self.temperature_controller_1.controller_type,
            },
            'temperature_controller_2': {
                'serial': self.temperature_controller_2.serial.to_dict(),
                'controller_type': self.temperature_controller_2.controller_type,
            },
            'humidity_sensor': {
                'serial': self.humidity_sensor.serial.to_dict(),
            },
            'gps': {
                'serial': self.gps.serial.to_dict(),
                'system_type': self.gps.system_type,
            },
        }
        with open(filepath, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def help(cls) -> str:
        """Return help text for HardwareConfig."""
        return """
HardwareConfig - Complete Hardware Configuration
================================================

Master configuration class for all SciGlob hardware devices.

Components:
-----------
  - head_sensor            : Head Sensor with Tracker, Filter Wheels, Shadowband
  - temperature_controller_1: TETech1 temperature controller
  - temperature_controller_2: TETech2 temperature controller
  - humidity_sensor        : HDC2080EVM humidity sensor
  - gps                    : GPS/Positioning system

Loading from YAML:
------------------
  from sciglob.config import HardwareConfig

  config = HardwareConfig.from_yaml('my_config.yaml')

Example YAML File:
------------------
  head_sensor:
    serial:
      port: COM3
      baudrate: 9600
    tracker_type: LuftBlickTR1
    motion_limits: [0, 90, 0, 360]
    fw1_filters: [OPEN, U340, BP300, LPNIR, ND1, ND2, ND3, ND4, OPAQUE]

  temperature_controller_1:
    serial:
      port: COM4
    controller_type: TETech1

  gps:
    serial:
      port: COM6
    system_type: GlobalSat

Saving Configuration:
---------------------
  config = HardwareConfig()
  config.head_sensor.serial.port = 'COM3'
  config.to_yaml('my_config.yaml')
"""


def print_help(cls_or_instance) -> None:
    """Print help for a configuration class or instance.

    Args:
        cls_or_instance: A config class or instance with help() method
    """
    if hasattr(cls_or_instance, 'help'):
        print(cls_or_instance.help())
    else:
        print(f"No help available for {type(cls_or_instance)}")


# Default configurations based on Blick reference
DEFAULT_SERIAL_CONFIG = SerialConfig(
    baudrate=9600,
    bytesize=8,
    parity='N',
    stopbits=1,
    timeout=0,
    write_timeout=20.0,
)

DEFAULT_HEAD_SENSOR_CONFIG = HeadSensorConfig(
    serial=SerialConfig(baudrate=9600),
    tracker_type="Directed Perceptions",
    degrees_per_step=0.01,
    motion_limits=[0, 90, 0, 360],
    home_position=[0.0, 180.0],
)

DEFAULT_TETECH1_CONFIG = TemperatureControllerConfig(
    serial=SerialConfig(baudrate=9600),
    controller_type="TETech1",
)

DEFAULT_TETECH2_CONFIG = TemperatureControllerConfig(
    serial=SerialConfig(baudrate=9600),
    controller_type="TETech2",
)

