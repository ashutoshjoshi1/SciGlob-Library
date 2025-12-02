"""Core utilities and base classes for SciGlob library."""

from sciglob.core.base import BaseDevice
from sciglob.core.connection import SerialConnection, parse_response, parse_position_response
from sciglob.core.exceptions import (
    SciGlobError,
    ConnectionError,
    CommunicationError,
    DeviceError,
    TimeoutError,
    ConfigurationError,
    TrackerError,
    MotorError,
    FilterWheelError,
    PositionError,
    HomingError,
    MotorAlarmError,
    SensorError,
    RecoveryError,
)
from sciglob.core.protocols import (
    DeviceType,
    ErrorCode,
    MotorAlarmCode,
    SerialConfig,
    CommandProtocol,
    ERROR_MESSAGES,
    MOTOR_ALARM_MESSAGES,
    TIMING_CONFIG,
    get_error_message,
    get_motor_alarm_message,
)
from sciglob.core.utils import (
    degrees_to_steps,
    steps_to_degrees,
    validate_angle,
    normalize_azimuth,
    calculate_angular_distance,
    shortest_rotation_path,
    dec2hex,
    hex2dec,
    get_checksum,
)

__all__ = [
    # Base
    "BaseDevice",
    # Connection
    "SerialConnection",
    "parse_response",
    "parse_position_response",
    # Exceptions
    "SciGlobError",
    "ConnectionError",
    "CommunicationError",
    "DeviceError",
    "TimeoutError",
    "ConfigurationError",
    "TrackerError",
    "MotorError",
    "FilterWheelError",
    "PositionError",
    "HomingError",
    "MotorAlarmError",
    "SensorError",
    "RecoveryError",
    # Protocols
    "DeviceType",
    "ErrorCode",
    "MotorAlarmCode",
    "SerialConfig",
    "CommandProtocol",
    "ERROR_MESSAGES",
    "MOTOR_ALARM_MESSAGES",
    "TIMING_CONFIG",
    "get_error_message",
    "get_motor_alarm_message",
    # Utils
    "degrees_to_steps",
    "steps_to_degrees",
    "validate_angle",
    "normalize_azimuth",
    "calculate_angular_distance",
    "shortest_rotation_path",
    "dec2hex",
    "hex2dec",
    "get_checksum",
]
