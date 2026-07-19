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

__version__ = "0.2.0"
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
    CameraError,
    CommunicationError,
    ConfigurationError,
    ConnectionError,
    DeviceError,
    DeviceIdentityError,
    FilterWheelError,
    HomingError,
    ImuError,
    MotorAlarmError,
    MotorError,
    PortCollisionError,
    PositionError,
    RecoveryError,
    RecoveryFailed,
    RelayBoardError,
    SciGlobError,
    SensorError,
    SessionRestartRequired,
    SpectrometerError,
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
from sciglob.core.simulation import SimulatedTransport, make_responder

# Devices
from sciglob.devices.asb import ASB, SimulatedASB
from sciglob.devices.filter_wheel import FilterWheel
from sciglob.devices.head_sensor import HeadSensor, SimulatedHeadSensor
from sciglob.devices.humidity_sensor import HumiditySensor
from sciglob.devices.positioning import GlobalSatGPS, NovatelGPS, PositioningSystem
from sciglob.devices.relay_board import RelayBoard, SimulatedRelayBoard
from sciglob.devices.rs485_tracker import RS485Tracker, SimulatedRS485Tracker
from sciglob.devices.sbhs import SBHS, SensorRecord, SimulatedSBHS
from sciglob.devices.shadowband import Shadowband
from sciglob.devices.srb import SRB, SimulatedSRB
from sciglob.devices.temperature_controller import TemperatureController
from sciglob.devices.tracker import Tracker

# Top-level facade
from sciglob.instrument import Instrument

# Optional-extra subsystems (camera / imu / spectrometers) import their vendor
# dependencies lazily, so these modules themselves import fine without the
# extras installed; a clear error is raised only when a real backend is used.
from sciglob import camera, imu, spectrometers  # noqa: E402


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
    "RecoveryFailed",
    "PortCollisionError",
    "DeviceIdentityError",
    "SpectrometerError",
    "SessionRestartRequired",
    "RelayBoardError",
    "ImuError",
    "CameraError",
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
    "SimulatedHeadSensor",
    "Tracker",
    "FilterWheel",
    "Shadowband",
    "TemperatureController",
    "HumiditySensor",
    "PositioningSystem",
    "GlobalSatGPS",
    "NovatelGPS",
    # New devices (0.2.0)
    "SRB",
    "SimulatedSRB",
    "SBHS",
    "SimulatedSBHS",
    "SensorRecord",
    "ASB",
    "SimulatedASB",
    "RelayBoard",
    "SimulatedRelayBoard",
    "RS485Tracker",
    "SimulatedRS485Tracker",
    # Facade + simulation + optional subsystems
    "Instrument",
    "SimulatedTransport",
    "make_responder",
    "camera",
    "imu",
    "spectrometers",
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
