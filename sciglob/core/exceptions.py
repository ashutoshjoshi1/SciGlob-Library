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


class RecoveryFailed(RecoveryError):
    """Raised when a device recovery ladder is exhausted without success.

    Subclass of :class:`RecoveryError` kept as a distinct name so callers
    can catch ladder exhaustion separately from single-step recovery errors.
    """

    def __init__(self, message: str, recovery_level: int = -1, device: Optional[str] = None):
        super().__init__(message, recovery_level)
        self.device = device


class PortCollisionError(ConnectionError):
    """Raised when a port is already owned by another device in this process.

    Field lesson (unit 071): two device objects silently sharing one COM port
    corrupt each other's answer streams. The library refuses to open a port
    that is already claimed and names both devices in the message.
    """

    def __init__(self, port: str, requesting_device: str, owning_device: str):
        self.port = port
        self.requesting_device = requesting_device
        self.owning_device = owning_device
        super().__init__(
            f"Port {port} requested by '{requesting_device}' is already owned by "
            f"'{owning_device}' in this process. Close the owning device first or "
            f"assign a different port."
        )


class DeviceIdentityError(ConnectionError):
    """Raised when a device on a port fails identification.

    Carries the raw answer so callers can diagnose what actually answered
    (e.g. an ASB found where an SBHS was expected — error code 98).
    """

    def __init__(self, message: str, answer: Optional[str] = None, error_code: Optional[int] = None):
        super().__init__(message)
        self.answer = answer
        self.error_code = error_code


class SpectrometerError(DeviceError):
    """Raised when a spectrometer operation fails."""

    pass


class SessionRestartRequired(SpectrometerError):
    """Sentinel escalation: Tier A recovery exhausted with a wedged AVS session.

    The coordinator must quiesce *all* spectrometer channels, then restart the
    process-wide AVS session (AVS_Done -> AVS_Init) and reactivate every
    channel. Never handled per-device.
    """

    pass


class RelayBoardError(DeviceError):
    """Raised when a relay board operation fails."""

    pass


class ImuError(DeviceError):
    """Raised when an IMU operation fails."""

    pass


class CameraError(DeviceError):
    """Raised when a camera operation fails."""

    pass
