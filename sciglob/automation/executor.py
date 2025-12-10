"""
Execution engine for SciGlob routines and schedules.

This module provides executors that run routines and schedules
by sending commands to connected hardware devices.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING, Any, Callable, Optional, Union

from sciglob.automation.exceptions import (
    ExecutionError,
    RoutineError,
)
from sciglob.automation.routines import (
    ROUTINE_PARAMS,
    Routine,
    RoutineCommand,
    RoutineKeyword,
    RoutineParameters,
)
from sciglob.automation.schedules import (
    Schedule,
    ScheduleEntry,
    TimeReference,
)
from sciglob.automation.timing import (
    AstronomicalEvents,
    LunarPosition,
    SolarPosition,
    TimeCalculator,
)

# Avoid circular imports
if TYPE_CHECKING:
    from sciglob.devices.head_sensor import HeadSensor
    from sciglob.devices.tracker import Tracker

logger = logging.getLogger(__name__)


class ExecutionState(Enum):
    """Current state of execution."""

    IDLE = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()
    COMPLETED = auto()


@dataclass
class ExecutionContext:
    """
    Context for routine execution containing state and device references.

    Attributes:
        state: Current execution state
        current_routine: Currently executing routine
        current_command: Currently executing command
        loop_stack: Stack of loop indices for nested loops
        variables: Dictionary of routine variables
        hardware: Dictionary of connected hardware devices
        location: Location information for astronomical calculations
        events: Astronomical events for current day
    """

    state: ExecutionState = ExecutionState.IDLE
    current_routine: Optional[str] = None
    current_command: Optional[RoutineCommand] = None
    loop_stack: list[dict[str, Any]] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)

    # Hardware references
    hardware: dict[str, Any] = field(default_factory=dict)

    # Location and timing
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    events: Optional[AstronomicalEvents] = None

    # Spectrometer settings
    integration_time: dict[int, float] = field(default_factory=dict)
    n_cycles: dict[int, int] = field(default_factory=dict)
    n_repetitions: dict[int, int] = field(default_factory=dict)

    # Filter wheel state
    filter_wheel_1_position: int = 1
    filter_wheel_2_position: int = 1

    # Tracker state
    pointing_zenith: float = 0.0
    pointing_azimuth: float = 0.0
    shadowband_zenith: float = 999.0  # 999 = not used

    # Measurement data
    last_measurement: Optional[dict[str, Any]] = None
    measurement_count: int = 0

    # Error tracking
    error_count: int = 0
    warning_count: int = 0
    last_error: Optional[str] = None

    def reset(self) -> None:
        """Reset execution context to initial state."""
        self.state = ExecutionState.IDLE
        self.current_routine = None
        self.current_command = None
        self.loop_stack.clear()
        self.variables.clear()
        self.measurement_count = 0
        self.error_count = 0
        self.warning_count = 0
        self.last_error = None

    def push_loop(
        self,
        values: list[Any],
        current_index: int = 0,
    ) -> None:
        """Push a new loop onto the stack."""
        self.loop_stack.append(
            {
                "values": values,
                "index": current_index,
                "iteration": 0,
            }
        )

    def pop_loop(self) -> Optional[dict[str, Any]]:
        """Pop loop from stack, returns None if empty."""
        if self.loop_stack:
            return self.loop_stack.pop()
        return None

    def get_xij_value(self, index: int = 0) -> Any:
        """Get XIJ variable value from current loop."""
        if not self.loop_stack:
            raise RoutineError("No loop active for XIJ variable")

        current_loop = self.loop_stack[-1]
        values = current_loop["values"]
        loop_index = current_loop["index"]

        if loop_index >= len(values):
            return None

        value = values[loop_index]

        # Handle nested values
        if isinstance(value, (list, tuple)) and index < len(value):
            return value[index]
        elif index == 0:
            return value

        raise RoutineError(f"XIJ index {index} out of range")


class RoutineExecutor:
    """
    Executor for running individual routines.

    Handles command execution, loop processing, and hardware interaction.

    Example:
        >>> executor = RoutineExecutor(head_sensor=hs)
        >>> executor.execute(routine)
    """

    def __init__(
        self,
        head_sensor: Optional["HeadSensor"] = None,
        tracker: Optional["Tracker"] = None,
        params: Optional[RoutineParameters] = None,
        latitude: float = 0.0,
        longitude: float = 0.0,
    ):
        """
        Initialize routine executor.

        Args:
            head_sensor: HeadSensor device for filter wheels and sensors
            tracker: Tracker device for pointing
            params: Routine parameters
            latitude: Location latitude for astronomical calculations
            longitude: Location longitude for astronomical calculations
        """
        self.params = params or ROUTINE_PARAMS

        # Create execution context
        self.context = ExecutionContext(
            latitude=latitude,
            longitude=longitude,
        )

        # Store hardware references
        if head_sensor:
            self.context.hardware["head_sensor"] = head_sensor
        if tracker:
            self.context.hardware["tracker"] = tracker

        # Time calculator for astronomical positions
        self._time_calculator = TimeCalculator(latitude, longitude)

        # Callbacks for custom handling
        self._callbacks: dict[str, list[Callable]] = {
            "on_command_start": [],
            "on_command_complete": [],
            "on_measurement": [],
            "on_error": [],
            "on_routine_start": [],
            "on_routine_complete": [],
        }

        # Control events
        self._stop_event = Event()
        self._pause_event = Event()
        self._lock = Lock()

    def register_callback(
        self,
        event: str,
        callback: Callable,
    ) -> None:
        """
        Register a callback for execution events.

        Args:
            event: Event name (on_command_start, on_measurement, etc.)
            callback: Callback function
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _emit_event(self, event: str, **kwargs) -> None:
        """Emit an event to registered callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(self.context, **kwargs)
            except Exception as e:
                logger.warning(f"Callback error for {event}: {e}")

    def execute(
        self,
        routine: Routine,
        timeout: Optional[float] = None,
    ) -> ExecutionContext:
        """
        Execute a routine.

        Args:
            routine: Routine to execute
            timeout: Maximum execution time in seconds

        Returns:
            ExecutionContext with results

        Raises:
            ExecutionError: If execution fails
        """
        self._stop_event.clear()
        self._pause_event.clear()
        self.context.reset()

        self.context.state = ExecutionState.RUNNING
        self.context.current_routine = routine.code

        logger.info(f"Starting routine {routine.code}: {routine.description}")
        self._emit_event("on_routine_start", routine=routine)

        start_time = time.time()

        try:
            # Execute commands
            command_index = 0
            while command_index < len(routine.commands):
                # Check for stop
                if self._stop_event.is_set():
                    self.context.state = ExecutionState.STOPPED
                    break

                # Check for pause
                while self._pause_event.is_set():
                    self.context.state = ExecutionState.PAUSED
                    time.sleep(0.1)
                    if self._stop_event.is_set():
                        break

                self.context.state = ExecutionState.RUNNING

                # Check timeout
                if timeout and (time.time() - start_time) > timeout:
                    raise ExecutionError(f"Routine timeout after {timeout}s")

                # Get command
                command = routine.commands[command_index]
                self.context.current_command = command

                # Execute command
                next_index = self._execute_command(command, routine.commands, command_index)

                if next_index is not None:
                    command_index = next_index
                else:
                    command_index += 1

            if self.context.state == ExecutionState.RUNNING:
                self.context.state = ExecutionState.COMPLETED

        except Exception as e:
            self.context.state = ExecutionState.ERROR
            self.context.last_error = str(e)
            self.context.error_count += 1
            logger.error(f"Routine {routine.code} error: {e}")
            self._emit_event("on_error", error=e)
            raise ExecutionError(str(e), routine.code) from e

        finally:
            logger.info(f"Routine {routine.code} completed with state {self.context.state.name}")
            self._emit_event("on_routine_complete", routine=routine)

        return self.context

    def stop(self) -> None:
        """Stop routine execution."""
        self._stop_event.set()

    def pause(self) -> None:
        """Pause routine execution."""
        self._pause_event.set()

    def resume(self) -> None:
        """Resume paused execution."""
        self._pause_event.clear()

    def _execute_command(
        self,
        command: RoutineCommand,
        all_commands: list[RoutineCommand],
        current_index: int,
    ) -> Optional[int]:
        """
        Execute a single command.

        Returns:
            Next command index, or None to continue normally
        """
        self._emit_event("on_command_start", command=command)

        try:
            if command.keyword == RoutineKeyword.DESCRIPTION:
                pass  # No action needed

            elif command.keyword == RoutineKeyword.COMMAND:
                self._execute_custom_command(command)

            elif command.keyword == RoutineKeyword.DURATION:
                self._execute_duration(command)

            elif command.keyword == RoutineKeyword.START_LOOP:
                return self._start_loop(command, all_commands, current_index)

            elif command.keyword == RoutineKeyword.STOP_LOOP:
                return self._stop_loop(all_commands, current_index)

            elif command.keyword == RoutineKeyword.SET_POINTING:
                self._execute_set_pointing(command)

            elif command.keyword == RoutineKeyword.SET_FILTERWHEELS:
                self._execute_set_filterwheels(command)

            elif command.keyword == RoutineKeyword.SET_SHADOWBAND:
                self._execute_set_shadowband(command)

            elif command.keyword == RoutineKeyword.SET_SPECTROMETER:
                self._execute_set_spectrometer(command)

            elif command.keyword == RoutineKeyword.MEASURE:
                self._execute_measure(command)

            elif command.keyword == RoutineKeyword.CHECK_INTENSITY:
                self._execute_check_intensity(command)

            elif command.keyword == RoutineKeyword.PROCESSINFO:
                self._execute_processinfo(command)

            else:
                logger.warning(f"Unknown command keyword: {command.keyword}")

        finally:
            self._emit_event("on_command_complete", command=command)

        return None

    def _execute_custom_command(self, command: RoutineCommand) -> None:
        """Execute a custom COMMAND."""
        value = command.get("VALUE", "")
        logger.debug(f"Custom command: {value}")

        # Execute as Python code if it looks like it
        if value.startswith("self.") or "=" in value:
            # Store references for execution
            try:
                exec(value)
            except Exception as e:
                logger.warning(f"Custom command error: {e}")

    def _execute_duration(self, command: RoutineCommand) -> None:
        """Execute a DURATION wait."""
        length = command.get("LENGTH", 0)
        timemode = command.get("TIMEMODE", "ADDED")

        if isinstance(length, (int, float)) and length > 0:
            logger.debug(f"Waiting {length} seconds (mode={timemode})")
            time.sleep(length)

    def _start_loop(
        self,
        command: RoutineCommand,
        all_commands: list[RoutineCommand],
        current_index: int,
    ) -> Optional[int]:
        """Start a loop, returns None to continue normally."""
        xij_value = command.get("XIJ", "")

        # Parse XIJ values
        if isinstance(xij_value, str):
            # Try to evaluate as Python expression
            try:
                values = eval(xij_value)
                if not isinstance(values, (list, tuple)):
                    values = [values]
            except Exception:
                values = [xij_value]
        else:
            values = xij_value if isinstance(xij_value, (list, tuple)) else [xij_value]

        # Push loop context
        self.context.push_loop(values)

        logger.debug(f"Starting loop with {len(values)} iterations")
        return None  # Continue to next command

    def _stop_loop(
        self,
        all_commands: list[RoutineCommand],
        current_index: int,
    ) -> Optional[int]:
        """Handle end of loop, returns index to jump to or None."""
        if not self.context.loop_stack:
            logger.warning("STOP LOOP without START LOOP")
            return None

        current_loop = self.context.loop_stack[-1]
        current_loop["index"] += 1
        current_loop["iteration"] += 1

        # Check if loop complete
        if current_loop["index"] >= len(current_loop["values"]):
            self.context.pop_loop()
            logger.debug("Loop completed")
            return None

        # Find matching START LOOP to jump back
        depth = 0
        for i in range(current_index - 1, -1, -1):
            cmd = all_commands[i]
            if cmd.keyword == RoutineKeyword.STOP_LOOP:
                depth += 1
            elif cmd.keyword == RoutineKeyword.START_LOOP:
                if depth == 0:
                    logger.debug(f"Loop iteration {current_loop['iteration']}")
                    return i + 1  # Continue after START LOOP
                depth -= 1

        logger.warning("Could not find matching START LOOP")
        return None

    def _execute_set_pointing(self, command: RoutineCommand) -> None:
        """Execute SET POINTING command."""
        tracker = self.context.hardware.get("tracker")
        if not tracker:
            logger.warning("SET POINTING: No tracker available")
            return

        # Get pointing parameters
        zen = self._resolve_value(command.get("ZEN", "CURRENT"))
        azi = self._resolve_value(command.get("AZI", "CURRENT"))
        zenmode = command.get("ZENMODE", "ABS")
        azimode = command.get("AZIMODE", "ABS")
        command.get("DELTA", "MIDDLE")

        # Handle special values
        if zen == "CURRENT":
            zen = self.context.pointing_zenith
        elif zen == "PARK":
            zen = 90.0  # Parking position

        if azi == "CURRENT":
            azi = self.context.pointing_azimuth
        elif azi == "RESET":
            # Trigger tracker reset
            try:
                tracker.reset()
            except Exception as e:
                logger.error(f"Tracker reset error: {e}")
            return

        # Convert relative modes
        if zenmode in ("RELSUN", "RELMOON"):
            target_pos = self._get_target_position(zenmode)
            if target_pos:
                zen = target_pos.zenith_angle + zen

        if azimode in ("RELSUN", "RELMOON"):
            target_pos = self._get_target_position(azimode)
            if target_pos:
                azi = target_pos.azimuth + azi

        # Move tracker
        try:
            logger.debug(f"Moving tracker to zen={zen}, azi={azi}")
            tracker.move_to(zenith=zen, azimuth=azi)
            self.context.pointing_zenith = zen
            self.context.pointing_azimuth = azi
        except Exception as e:
            logger.error(f"Tracker move error: {e}")

    def _execute_set_filterwheels(self, command: RoutineCommand) -> None:
        """Execute SET FILTERWHEELS command."""
        head_sensor = self.context.hardware.get("head_sensor")
        if not head_sensor:
            logger.warning("SET FILTERWHEELS: No head sensor available")
            return

        fw1 = self._resolve_value(command.get("FW1", "CURRENT"))
        fw2 = self._resolve_value(command.get("FW2", "CURRENT"))
        command.get("FUNCFILT", "XXX")

        # Handle filter wheel 1
        if fw1 != "CURRENT" and fw1 != "XXX":
            try:
                if fw1 == "RESET":
                    if hasattr(head_sensor, "filter_wheel_1"):
                        head_sensor.filter_wheel_1.home()
                elif isinstance(fw1, int):
                    if hasattr(head_sensor, "filter_wheel_1"):
                        head_sensor.filter_wheel_1.set_position(fw1)
                    self.context.filter_wheel_1_position = fw1
                else:
                    # Filter name
                    if hasattr(head_sensor, "filter_wheel_1"):
                        head_sensor.filter_wheel_1.set_filter(fw1)
            except Exception as e:
                logger.error(f"Filter wheel 1 error: {e}")

        # Handle filter wheel 2
        if fw2 != "CURRENT" and fw2 != "XXX":
            try:
                if fw2 == "RESET":
                    if hasattr(head_sensor, "filter_wheel_2"):
                        head_sensor.filter_wheel_2.home()
                elif isinstance(fw2, int):
                    if hasattr(head_sensor, "filter_wheel_2"):
                        head_sensor.filter_wheel_2.set_position(fw2)
                    self.context.filter_wheel_2_position = fw2
                else:
                    if hasattr(head_sensor, "filter_wheel_2"):
                        head_sensor.filter_wheel_2.set_filter(fw2)
            except Exception as e:
                logger.error(f"Filter wheel 2 error: {e}")

    def _execute_set_shadowband(self, command: RoutineCommand) -> None:
        """Execute SET SHADOWBAND command."""
        head_sensor = self.context.hardware.get("head_sensor")
        if not head_sensor or not hasattr(head_sensor, "shadowband"):
            logger.warning("SET SHADOWBAND: No shadowband available")
            return

        sbzen = self._resolve_value(command.get("SBZEN", "CURRENT"))
        command.get("SBZENMODE", "ABS")

        if sbzen == "CURRENT":
            return

        if sbzen == "RESET":
            try:
                head_sensor.shadowband.home()
            except Exception as e:
                logger.error(f"Shadowband reset error: {e}")
            return

        try:
            head_sensor.shadowband.move_to(sbzen)
            self.context.shadowband_zenith = sbzen
        except Exception as e:
            logger.error(f"Shadowband move error: {e}")

    def _execute_set_spectrometer(self, command: RoutineCommand) -> None:
        """Execute SET SPECTROMETER command."""
        it = self._resolve_value(command.get("IT", "CURRENT"))
        ncycles = self._resolve_value(command.get("NCYCLES", "AUTO"))
        nreps = self._resolve_value(command.get("NREPETITIONS", "AUTO"))

        # Store in context
        if it != "CURRENT" and isinstance(it, (int, float)):
            self.context.integration_time[0] = it

        if ncycles != "AUTO" and isinstance(ncycles, int):
            self.context.n_cycles[0] = ncycles

        if nreps != "AUTO" and isinstance(nreps, int):
            self.context.n_repetitions[0] = nreps

        logger.debug(f"Spectrometer settings: IT={it}, cycles={ncycles}, reps={nreps}")

    def _execute_measure(self, command: RoutineCommand) -> None:
        """Execute MEASURE command."""
        display = command.get("DISPLAY", "MEAN")
        save = command.get("SAVE", "NO")
        command.get("SATCHECK", "YES")

        self.context.measurement_count += 1

        # This would typically trigger actual measurement
        # For now, just log and emit event
        logger.debug(
            f"Measurement #{self.context.measurement_count}: display={display}, save={save}"
        )

        measurement_data = {
            "count": self.context.measurement_count,
            "timestamp": datetime.now(timezone.utc),
            "integration_time": self.context.integration_time.get(0, 100),
            "n_cycles": self.context.n_cycles.get(0, 1),
            "filter_wheel_1": self.context.filter_wheel_1_position,
            "filter_wheel_2": self.context.filter_wheel_2_position,
            "zenith": self.context.pointing_zenith,
            "azimuth": self.context.pointing_azimuth,
        }

        self.context.last_measurement = measurement_data
        self._emit_event("on_measurement", data=measurement_data)

    def _execute_check_intensity(self, command: RoutineCommand) -> None:
        """Execute CHECK INTENSITY command."""
        adjustit = command.get("ADJUSTIT", "FROMCURRENT")
        command.get("ADJUSTND", "NO")
        saturation_target = command.get("%SATURATION", 80)

        logger.debug(f"Check intensity: target={saturation_target}%, adjustit={adjustit}")

        # This would typically perform actual intensity check
        # For now, just log

    def _execute_processinfo(self, command: RoutineCommand) -> None:
        """Execute PROCESSINFO command."""
        ptype = command.get("TYPE", "ONLYL1")
        distance = command.get("DISTANCE", "NO")

        self.context.variables["process_type"] = ptype
        if distance != "NO":
            self.context.variables["target_distance"] = distance

    def _resolve_value(self, value: Any) -> Any:
        """Resolve a value, handling XIJ references."""
        if isinstance(value, str) and value.startswith("XIJ"):
            try:
                # Parse XIJ index
                if value == "XIJ":
                    index = 0
                else:
                    import re

                    match = re.match(r"XIJ\((\d+)\)", value)
                    if match:
                        index = int(match.group(1)) - 1
                    else:
                        return value

                return self.context.get_xij_value(index)
            except Exception as e:
                logger.warning(f"XIJ resolution error: {e}")
                return value

        return value

    def _get_target_position(
        self,
        mode: str,
    ) -> Optional[Union[SolarPosition, LunarPosition]]:
        """Get current position of sun or moon."""
        now = datetime.now(timezone.utc)

        if "SUN" in mode.upper():
            return self._time_calculator.calculate_solar_position(now)
        elif "MOON" in mode.upper():
            return self._time_calculator.calculate_lunar_position(now)

        return None


class ScheduleExecutor:
    """
    Executor for running schedules.

    Manages timing and execution of routine sequences according
    to schedule entries.

    Example:
        >>> executor = ScheduleExecutor(schedule, head_sensor=hs)
        >>> executor.start()
        >>> # ... schedule runs in background ...
        >>> executor.stop()
    """

    def __init__(
        self,
        schedule: Schedule,
        routines: list[Routine],
        head_sensor: Optional["HeadSensor"] = None,
        tracker: Optional["Tracker"] = None,
        latitude: float = 0.0,
        longitude: float = 0.0,
    ):
        """
        Initialize schedule executor.

        Args:
            schedule: Schedule to execute
            routines: List of available routines
            head_sensor: HeadSensor device
            tracker: Tracker device
            latitude: Location latitude
            longitude: Location longitude
        """
        self.schedule = schedule
        self.routines = {r.code: r for r in routines}

        # Create routine executor
        self.routine_executor = RoutineExecutor(
            head_sensor=head_sensor,
            tracker=tracker,
            latitude=latitude,
            longitude=longitude,
        )

        # Time calculator
        self._time_calculator = TimeCalculator(latitude, longitude)
        self._events: Optional[AstronomicalEvents] = None

        # Execution state
        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._state = ExecutionState.IDLE
        self._current_entry: Optional[ScheduleEntry] = None

        # Callbacks
        self._callbacks: dict[str, list[Callable]] = {
            "on_entry_start": [],
            "on_entry_complete": [],
            "on_schedule_start": [],
            "on_schedule_complete": [],
        }

    @property
    def state(self) -> ExecutionState:
        """Get current execution state."""
        return self._state

    @property
    def current_entry(self) -> Optional[ScheduleEntry]:
        """Get currently executing entry."""
        return self._current_entry

    def register_callback(
        self,
        event: str,
        callback: Callable,
    ) -> None:
        """Register a callback for schedule events."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _emit_event(self, event: str, **kwargs) -> None:
        """Emit an event to registered callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                callback(**kwargs)
            except Exception as e:
                logger.warning(f"Callback error for {event}: {e}")

    def calculate_times(self, date: Optional[datetime] = None) -> None:
        """
        Calculate execution times for schedule entries.

        Args:
            date: Date for which to calculate (default: today)
        """
        if date is None:
            date = datetime.now(timezone.utc)

        # Get astronomical events for the day
        self._events = self._time_calculator.calculate_events(date)

        # Calculate times for each entry
        previous_end: Optional[datetime] = None

        for entry in self.schedule.entries:
            entry.computed_start = self._calculate_entry_time(
                entry.start_time_ref,
                entry.start_offset,
                previous_end,
            )

            if entry.end_time_ref != TimeReference.UNDEFINED:
                entry.computed_end = self._calculate_entry_time(
                    entry.end_time_ref,
                    entry.end_offset,
                    entry.computed_start,
                )

            # Estimate end time for THEN calculation
            if entry.computed_start:
                duration = self._estimate_entry_duration(entry)
                previous_end = entry.computed_start + timedelta(seconds=duration)

    def _calculate_entry_time(
        self,
        ref: TimeReference,
        offset: timedelta,
        previous_end: Optional[datetime],
    ) -> Optional[datetime]:
        """Calculate absolute time for a time reference."""
        if not self._events:
            return None

        base_time: Optional[datetime] = None

        if ref == TimeReference.ABSOLUTE:
            # Offset contains the absolute time of day
            base_time = datetime.combine(
                self._events.date.date(), datetime.min.time(), tzinfo=timezone.utc
            )
            return base_time + offset

        elif ref == TimeReference.LOCAL_MIDNIGHT:
            base_time = self._events.date

        elif ref == TimeReference.LOCAL_NOON:
            base_time = self._events.solar_noon

        elif ref in (TimeReference.SOLAR_ZEN_90_AM, TimeReference.SUNRISE):
            base_time = self._events.sunrise

        elif ref in (TimeReference.SOLAR_ZEN_90_PM, TimeReference.SUNSET):
            base_time = self._events.sunset

        elif ref == TimeReference.THEN:
            base_time = previous_end

        if base_time:
            return base_time + offset

        return None

    def _estimate_entry_duration(self, entry: ScheduleEntry) -> float:
        """Estimate duration of a schedule entry in seconds."""
        total = 0.0

        # Get routines for this entry
        for code, _ in entry.routine_params:
            if code in self.routines:
                routine = self.routines[code]
                total += routine.get_duration_estimate()

        # Account for repetitions
        if entry.repetitions > 0:
            total *= entry.repetitions
        else:
            # For unlimited (-1), estimate one iteration
            pass

        return max(total, 60.0)  # Minimum 1 minute

    def start(self) -> None:
        """Start schedule execution in background thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Schedule already running")
            return

        self._stop_event.clear()
        self._thread = Thread(target=self._run_schedule, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop schedule execution."""
        self._stop_event.set()
        self.routine_executor.stop()

        if self._thread:
            self._thread.join(timeout=5.0)

    def _run_schedule(self) -> None:
        """Main schedule execution loop."""
        self._state = ExecutionState.RUNNING
        self._emit_event("on_schedule_start", schedule=self.schedule)

        logger.info(f"Starting schedule: {self.schedule.name}")

        try:
            # Calculate times for today
            self.calculate_times()

            # Get sorted entries by start time
            entries = sorted(
                self.schedule.entries,
                key=lambda e: e.computed_start or datetime.max.replace(tzinfo=timezone.utc),
            )

            for entry in entries:
                if self._stop_event.is_set():
                    break

                if not entry.computed_start:
                    logger.warning(f"Skipping entry {entry.label}: no start time")
                    continue

                # Wait until start time
                self._wait_until(entry.computed_start)

                if self._stop_event.is_set():
                    break

                # Check condition
                if not entry.check_condition(datetime.now(timezone.utc)):
                    logger.info(f"Skipping entry {entry.label}: condition not met")
                    continue

                # Execute entry
                self._execute_entry(entry)

            self._state = ExecutionState.COMPLETED

        except Exception as e:
            self._state = ExecutionState.ERROR
            logger.error(f"Schedule error: {e}")

        finally:
            self._emit_event("on_schedule_complete", schedule=self.schedule)
            logger.info(f"Schedule {self.schedule.name} completed")

    def _wait_until(self, target_time: datetime) -> None:
        """Wait until a target time, checking for stop signal."""
        while datetime.now(timezone.utc) < target_time:
            if self._stop_event.is_set():
                return

            # Calculate remaining time
            remaining = (target_time - datetime.now(timezone.utc)).total_seconds()

            # Sleep in short intervals to allow stop checking
            sleep_time = min(remaining, 1.0)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _execute_entry(self, entry: ScheduleEntry) -> None:
        """Execute a schedule entry."""
        self._current_entry = entry
        self._emit_event("on_entry_start", entry=entry)

        logger.info(f"Executing entry: {entry.label}")

        try:
            # Execute start_with routines (once)
            for code, _ in entry.start_with_params:
                if self._stop_event.is_set():
                    break

                if code in self.routines:
                    routine = self.routines[code]
                    self.routine_executor.execute(routine)

            # Execute main routine sequence
            iteration = 0
            while True:
                if self._stop_event.is_set():
                    break

                # Check repetitions
                if entry.repetitions > 0 and iteration >= entry.repetitions:
                    break

                # Check end time
                if entry.computed_end and datetime.now(timezone.utc) >= entry.computed_end:
                    break

                # Execute routines
                for code, _ in entry.routine_params:
                    if self._stop_event.is_set():
                        break

                    if code in self.routines:
                        routine = self.routines[code]
                        self.routine_executor.execute(routine)

                iteration += 1

        finally:
            self._emit_event("on_entry_complete", entry=entry)
            self._current_entry = None
