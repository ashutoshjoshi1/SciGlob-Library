"""Configuration module for SciGlob Library.

This module provides configuration classes for all hardware devices.

Usage:
    from sciglob.config import (
        SerialConfig,
        HeadSensorConfig,
        TemperatureControllerConfig,
        HumiditySensorConfig,
        GPSConfig,
        HardwareConfig,
    )
    
    # Create serial config
    serial = SerialConfig(port='COM3', baudrate=9600)
    
    # Create head sensor config
    hs_config = HeadSensorConfig(
        serial=serial,
        tracker_type='LuftBlickTR1',
    )
    
    # Load from YAML
    config = HardwareConfig.from_yaml('config.yaml')
"""

from sciglob.config.hardware import (
    SerialConfig,
    HeadSensorConfig,
    TemperatureControllerConfig,
    HumiditySensorConfig,
    GPSConfig,
    HardwareConfig,
    DEFAULT_SERIAL_CONFIG,
    DEFAULT_HEAD_SENSOR_CONFIG,
    DEFAULT_TETECH1_CONFIG,
    DEFAULT_TETECH2_CONFIG,
    print_help,
)

__all__ = [
    'SerialConfig',
    'HeadSensorConfig',
    'TemperatureControllerConfig',
    'HumiditySensorConfig',
    'GPSConfig',
    'HardwareConfig',
    'DEFAULT_SERIAL_CONFIG',
    'DEFAULT_HEAD_SENSOR_CONFIG',
    'DEFAULT_TETECH1_CONFIG',
    'DEFAULT_TETECH2_CONFIG',
    'print_help',
]
