"""Custom exceptions for SciGlob library."""

from typing import Optional


class SciGlobError(Exception):
    """Base exception for all SciGlob errors."""

    pass


class ConnectionError(SciGlobError):
    """Raised when a connection to a device fails."""

    pass


class CommunicationError(SciGlobError):
    """Raised when communication with a device fails."""

    def __init__(self, message: str, error_code: Optional[int] = None):
        super().__init__(message)
        self.error_code = error_code


class DeviceError(SciGlobError):
    """Raised when a device operation fails."""

    def __init__(self, message: str, error_code: Optional[int] = None):
        super().__init__(message)
        self.error_code = error_code


class TimeoutError(SciGlobError):
    """Raised when an operation times out."""

    pass


class ConfigurationError(SciGlobError):
    """Raised when there's a configuration error."""

    pass


class TrackerError(DeviceError):
    """Raised when a tracker operation fails."""

    pass


class MotorError(DeviceError):
    """Raised when a motor operation fails."""

    pass


class FilterWheelError(DeviceError):
    """Raised when a filter wheel operation fails."""

    pass


class PositionError(MotorError):
    """Raised when a position is out of valid range."""

    def __init__(
        self,
        position: float,
        min_pos: float,
        max_pos: float,
        axis: str = "position",
    ):
        self.position = position
        self.min_pos = min_pos
        self.max_pos = max_pos
        self.axis = axis
        super().__init__(f"{axis} {position} is out of range [{min_pos}, {max_pos}]")


class HomingError(MotorError):
    """Raised when homing operation fails."""

    pass


class MotorAlarmError(MotorError):
    """Raised when motor reports an alarm condition."""

    def __init__(self, message: str, alarm_code: int, axis: str = "motor"):
        super().__init__(message, alarm_code)
        self.alarm_code = alarm_code
        self.axis = axis


class SensorError(DeviceError):
    """Raised when a sensor reading fails."""

    pass


class RecoveryError(SciGlobError):
    """Raised when recovery attempts are exhausted."""

    def __init__(self, message: str, recovery_level: int):
        super().__init__(message)
        self.recovery_level = recovery_level


class SpectrometerError(DeviceError):
    """Raised when a spectrometer operation fails."""

    pass


class CameraError(DeviceError):
    """Raised when a camera operation fails."""

    pass
