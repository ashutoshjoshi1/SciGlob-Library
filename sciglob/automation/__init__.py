"""
SciGlob Automation Module - Routines and Schedules

This module provides automated measurement control through:
- Routines: Predefined measurement sequences (similar to Blick .rout files)
- Schedules: Time-based execution of routine sequences (similar to Blick .sked files)

The design follows the Blick software pattern where:
- Routines are defined with two-letter codes (e.g., "DS" for direct sun)
- Schedules define when and how to execute routine sequences
- Timing can be based on astronomical events (sunrise, sunset, solar noon, etc.)

Quick Start:
    >>> from sciglob.automation import Routine, Schedule, ScheduleExecutor
    >>>
    >>> # Create a simple routine
    >>> routine = Routine.from_file("routines/DS.rout")
    >>>
    >>> # Create a schedule
    >>> schedule = Schedule.from_file("schedules/daily.sked")
    >>>
    >>> # Execute schedule
    >>> executor = ScheduleExecutor(schedule, head_sensor=hs)
    >>> executor.run()
"""

from sciglob.automation.exceptions import (
    AutomationError,
    ExecutionError,
    RoutineError,
    RoutineNotFoundError,
    RoutineParseError,
    ScheduleError,
    ScheduleParseError,
    TimingError,
)
from sciglob.automation.executor import (
    ExecutionContext,
    ExecutionState,
    RoutineExecutor,
    ScheduleExecutor,
)
from sciglob.automation.routines import (
    Routine,
    RoutineCommand,
    RoutineKeyword,
    RoutineParameters,
    RoutineReader,
)
from sciglob.automation.schedules import (
    Schedule,
    ScheduleEntry,
    ScheduleParameters,
    ScheduleReader,
    TimeReference,
)
from sciglob.automation.timing import (
    AstronomicalEvents,
    TimeCalculator,
    calculate_lunar_position,
    calculate_solar_position,
)

__all__ = [
    # Routines
    "Routine",
    "RoutineCommand",
    "RoutineKeyword",
    "RoutineParameters",
    "RoutineReader",
    # Schedules
    "Schedule",
    "ScheduleEntry",
    "ScheduleParameters",
    "ScheduleReader",
    "TimeReference",
    # Execution
    "RoutineExecutor",
    "ScheduleExecutor",
    "ExecutionContext",
    "ExecutionState",
    # Timing
    "AstronomicalEvents",
    "TimeCalculator",
    "calculate_solar_position",
    "calculate_lunar_position",
    # Exceptions
    "AutomationError",
    "RoutineError",
    "ScheduleError",
    "ExecutionError",
    "TimingError",
    "RoutineNotFoundError",
    "ScheduleParseError",
    "RoutineParseError",
]

