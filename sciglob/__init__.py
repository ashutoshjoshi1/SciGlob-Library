"""
SciGlob - Scientific Instrumentation Control Library

A Python library for controlling scientific instruments including:
- Head Sensors (SciGlobHSN1, SciGlobHSN2)
- Trackers (Directed Perceptions, LuftBlickTR1)
- Filter Wheels (FW1, FW2)
- Shadowband
- Temperature Controllers (TETech1, TETech2)
- Humidity Sensors (HDC2080EVM)
- GPS/Positioning Systems (Novatel, GlobalSat)
- Automated Routines and Schedules (Blick-compatible)

Installation:
    pip install sciglob

Quick Start:
    >>> from sciglob import HeadSensor
    >>> with HeadSensor(port="/dev/ttyUSB0") as hs:
    ...     # Access tracker
    ...     hs.tracker.move_to(zenith=45.0, azimuth=180.0)
    ...     # Access filter wheel
    ...     hs.filter_wheel_1.set_filter("OPEN")
    ...     # Get sensor readings
    ...     print(hs.get_all_sensors())

Automation (Routines & Schedules):
    >>> from sciglob.automation import Routine, Schedule, ScheduleExecutor
    >>>
    >>> # Load routines from files
    >>> routines = Routine.from_file("routines/DS.rout")
    >>>
    >>> # Load and execute a schedule
    >>> schedule = Schedule.from_file("schedules/daily.sked")
    >>> executor = ScheduleExecutor(schedule, routines, head_sensor=hs)
    >>> executor.start()

Help:
    >>> import sciglob
    >>> sciglob.help()                    # Library overview
    >>> sciglob.help_config()             # Configuration help
    >>>
    >>> hs = HeadSensor()
    >>> hs.help()                         # Device help
    >>> hs.help('method_name')            # Method help
    >>> hs.list_methods()                 # List methods
"""

__version__ = "0.1.4"
__author__ = "Ashutosh Joshi"

# Core components
# Automation
from sciglob.automation import (
    # Timing
    AstronomicalEvents,
    # Exceptions
    AutomationError,
    ExecutionContext,
    ExecutionError,
    ExecutionState,
    # Routines
    Routine,
    RoutineCommand,
    RoutineError,
    # Execution
    RoutineExecutor,
    RoutineKeyword,
    RoutineNotFoundError,
    RoutineParameters,
    RoutineParseError,
    RoutineReader,
    # Schedules
    Schedule,
    ScheduleEntry,
    ScheduleError,
    ScheduleExecutor,
    ScheduleParameters,
    ScheduleParseError,
    ScheduleReader,
    TimeCalculator,
    TimeReference,
    TimingError,
    calculate_lunar_position,
    calculate_solar_position,
)

# Configuration
from sciglob.config import (
    GPSConfig,
    HardwareConfig,
    HeadSensorConfig,
    HumiditySensorConfig,
    SerialConfig,
    TemperatureControllerConfig,
)

# Commands Reference
from sciglob.core.commands import (
    ALL_COMMANDS,
    CommandCategory,
    FirmwareCommand,
    get_command,
    list_commands,
    print_command_reference,
)
from sciglob.core.exceptions import (
    CommunicationError,
    ConfigurationError,
    ConnectionError,
    DeviceError,
    FilterWheelError,
    HomingError,
    MotorAlarmError,
    MotorError,
    PositionError,
    RecoveryError,
    SciGlobError,
    SensorError,
    TimeoutError,
    TrackerError,
)
from sciglob.core.help_mixin import show_config_help, show_library_help
from sciglob.core.protocols import (
    DeviceType,
    ErrorCode,
    MotorAlarmCode,
    get_error_message,
    get_motor_alarm_message,
)
from sciglob.core.utils import (
    degrees_to_steps,
    normalize_azimuth,
    steps_to_degrees,
)
from sciglob.devices.filter_wheel import FilterWheel

# Devices
from sciglob.devices.head_sensor import HeadSensor
from sciglob.devices.humidity_sensor import HumiditySensor
from sciglob.devices.positioning import GlobalSatGPS, NovatelGPS, PositioningSystem
from sciglob.devices.shadowband import Shadowband
from sciglob.devices.temperature_controller import TemperatureController
from sciglob.devices.tracker import Tracker


def help():
    """Display library help information."""
    show_library_help()


def help_config():
    """Display configuration help information."""
    show_config_help()


__all__ = [
    # Version
    "__version__",
    # Help
    "help",
    "help_config",
    # Commands Reference
    "FirmwareCommand",
    "CommandCategory",
    "ALL_COMMANDS",
    "get_command",
    "list_commands",
    "print_command_reference",
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
    "get_error_message",
    "get_motor_alarm_message",
    # Utilities
    "degrees_to_steps",
    "steps_to_degrees",
    "normalize_azimuth",
    # Configuration
    "SerialConfig",
    "HeadSensorConfig",
    "TemperatureControllerConfig",
    "HumiditySensorConfig",
    "GPSConfig",
    "HardwareConfig",
    # Devices
    "HeadSensor",
    "Tracker",
    "FilterWheel",
    "Shadowband",
    "TemperatureController",
    "HumiditySensor",
    "PositioningSystem",
    "GlobalSatGPS",
    "NovatelGPS",
    # Automation - Routines
    "Routine",
    "RoutineCommand",
    "RoutineKeyword",
    "RoutineParameters",
    "RoutineReader",
    # Automation - Schedules
    "Schedule",
    "ScheduleEntry",
    "ScheduleParameters",
    "ScheduleReader",
    "TimeReference",
    # Automation - Execution
    "RoutineExecutor",
    "ScheduleExecutor",
    "ExecutionContext",
    "ExecutionState",
    # Automation - Timing
    "AstronomicalEvents",
    "TimeCalculator",
    "calculate_solar_position",
    "calculate_lunar_position",
    # Automation - Exceptions
    "AutomationError",
    "RoutineError",
    "ScheduleError",
    "ExecutionError",
    "TimingError",
    "RoutineNotFoundError",
    "ScheduleParseError",
    "RoutineParseError",
]
