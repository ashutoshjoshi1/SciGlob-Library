#!/usr/bin/env python3
"""
SciGlob Automation Usage Examples

This example demonstrates how to use the routines and schedules
functionality in the SciGlob library, which follows the Blick software
pattern for automated measurements.

Topics covered:
1. Loading and parsing routines
2. Loading and parsing schedules
3. Executing routines manually
4. Running scheduled measurements
5. Astronomical calculations for timing
"""

from datetime import datetime, timezone
from pathlib import Path

# Import automation components
from sciglob.automation import (
    # Routines
    Routine,
    RoutineReader,
    RoutineKeyword,
    # Schedules
    Schedule,
    ScheduleReader,
    TimeReference,
    # Execution
    RoutineExecutor,
    ScheduleExecutor,
    ExecutionState,
    # Timing
    TimeCalculator,
    AstronomicalEvents,
    calculate_solar_position,
    calculate_lunar_position,
)


def example_load_routine():
    """Example: Loading a routine from file or string."""
    print("\n=== Loading Routines ===\n")
    
    # Method 1: Load from file
    routine_path = Path(__file__).parent / "routines" / "DS.rout"
    if routine_path.exists():
        ds_routine = Routine.from_file(routine_path)
        print(f"Loaded routine: {ds_routine.code}")
        print(f"Description: {ds_routine.description}")
        print(f"Number of commands: {len(ds_routine.commands)}")
        
        # Print commands
        for cmd in ds_routine.commands:
            print(f"  - {cmd.keyword.name}: {cmd.subkeywords}")
    
    # Method 2: Create from string
    routine_content = """
    DESCRIPTION -> Simple test routine
    SET SPECTROMETER -> IT=100; NCYCLES=10
    MEASURE -> DISPLAY=MEAN; SAVE=NO
    """
    
    test_routine = Routine.from_string("TT", routine_content)
    print(f"\nCreated routine from string: {test_routine.code}")
    print(f"Commands: {len(test_routine.commands)}")
    
    # Validate routine
    errors = test_routine.validate()
    if errors:
        print(f"Validation errors: {errors}")
    else:
        print("Routine is valid!")
    
    # Estimate duration
    duration = test_routine.get_duration_estimate()
    print(f"Estimated duration: {duration:.1f} seconds")


def example_load_all_routines():
    """Example: Loading all routines from a directory."""
    print("\n=== Loading All Routines ===\n")
    
    routines_dir = Path(__file__).parent / "routines"
    
    if routines_dir.exists():
        reader = RoutineReader()
        routines = reader.read_all_routines(routines_dir)
        
        print(f"Found {len(routines)} routines:")
        for routine in routines:
            print(f"  {routine.code}: {routine.description[:50]}...")
    else:
        print(f"Routines directory not found: {routines_dir}")


def example_load_schedule():
    """Example: Loading and parsing a schedule."""
    print("\n=== Loading Schedule ===\n")
    
    # Load from file
    schedule_path = Path(__file__).parent / "schedules" / "daily_measurement.sked"
    
    if schedule_path.exists():
        # First load routines (for validation)
        routines_dir = Path(__file__).parent / "routines"
        reader = RoutineReader()
        routines = reader.read_all_routines(routines_dir) if routines_dir.exists() else []
        
        # Load schedule
        schedule = Schedule.from_file(schedule_path, routines)
        
        print(f"Loaded schedule: {schedule.name}")
        print(f"Number of entries: {len(schedule.entries)}")
        
        # Print entries
        for entry in schedule.entries:
            print(f"\n  Entry: {entry.label}")
            print(f"    Start: {entry.start_time_ref.name} + {entry.start_offset}")
            print(f"    End: {entry.end_time_ref.name}")
            print(f"    Commands: {entry.commands}")
            print(f"    Priority: {entry.priority}")
            print(f"    Repetitions: {entry.repetitions}")
        
        # Get all routine codes used
        codes = schedule.get_all_routine_codes()
        print(f"\nRoutine codes used: {codes}")
        
        # Validate
        errors = schedule.validate(routines)
        if errors:
            print(f"\nValidation errors: {errors}")
        else:
            print("\nSchedule is valid!")
    else:
        print(f"Schedule file not found: {schedule_path}")


def example_astronomical_calculations():
    """Example: Calculating astronomical events for scheduling."""
    print("\n=== Astronomical Calculations ===\n")
    
    # Example location: Boulder, Colorado
    latitude = 40.0150
    longitude = -105.2705
    
    # Create time calculator
    calculator = TimeCalculator(latitude, longitude)
    
    # Get current time
    now = datetime.now(timezone.utc)
    print(f"Current UTC time: {now}")
    
    # Calculate solar position
    solar = calculator.calculate_solar_position(now)
    print(f"\nSolar Position:")
    print(f"  Zenith angle: {solar.zenith_angle:.2f}°")
    print(f"  Azimuth: {solar.azimuth:.2f}°")
    print(f"  Above horizon: {solar.is_above_horizon}")
    print(f"  Is daytime: {solar.is_daytime}")
    
    # Calculate lunar position
    lunar = calculator.calculate_lunar_position(now)
    print(f"\nLunar Position:")
    print(f"  Zenith angle: {lunar.zenith_angle:.2f}°")
    print(f"  Azimuth: {lunar.azimuth:.2f}°")
    print(f"  Phase: {lunar.phase:.2f}")
    print(f"  Illumination: {lunar.illumination:.1%}")
    
    # Calculate today's events
    events = calculator.calculate_events(now)
    print(f"\nToday's Events:")
    if events.sunrise:
        print(f"  Sunrise: {events.sunrise}")
    if events.solar_noon:
        print(f"  Solar noon: {events.solar_noon}")
    if events.sunset:
        print(f"  Sunset: {events.sunset}")
    if events.day_length:
        hours = events.day_length.total_seconds() / 3600
        print(f"  Day length: {hours:.2f} hours")


def example_calculate_schedule_times():
    """Example: Calculating absolute times for schedule entries."""
    print("\n=== Schedule Time Calculation ===\n")
    
    # Location
    latitude = 40.0150
    longitude = -105.2705
    
    # Load schedule and routines
    schedule_path = Path(__file__).parent / "schedules" / "daily_measurement.sked"
    routines_dir = Path(__file__).parent / "routines"
    
    if schedule_path.exists():
        reader = RoutineReader()
        routines = reader.read_all_routines(routines_dir) if routines_dir.exists() else []
        schedule = Schedule.from_file(schedule_path, routines)
        
        # Create schedule executor to calculate times
        executor = ScheduleExecutor(
            schedule=schedule,
            routines=routines,
            latitude=latitude,
            longitude=longitude,
        )
        
        # Calculate times for today
        executor.calculate_times()
        
        print(f"Schedule times for today ({datetime.now().date()}):\n")
        
        for entry in schedule.entries:
            print(f"  {entry.label}:")
            if entry.computed_start:
                print(f"    Start: {entry.computed_start.strftime('%H:%M:%S')} UTC")
            else:
                print(f"    Start: Could not calculate")
            if entry.computed_end:
                print(f"    End: {entry.computed_end.strftime('%H:%M:%S')} UTC")


def example_execute_routine():
    """Example: Executing a routine (without hardware)."""
    print("\n=== Routine Execution (Demo) ===\n")
    
    # Create a simple routine
    routine_content = """
    DESCRIPTION -> Demo routine for execution example
    SET SPECTROMETER -> IT=100; NCYCLES=5
    START LOOP -> XIJ=1,2,3
    SET FILTERWHEELS -> FW1=XIJ
    MEASURE -> DISPLAY=MEAN; SAVE=NO
    STOP LOOP
    """
    
    routine = Routine.from_string("DM", routine_content)
    print(f"Created routine: {routine.code} - {routine.description}")
    
    # Create executor (no hardware connected)
    executor = RoutineExecutor(latitude=40.0, longitude=-105.0)
    
    # Register callbacks
    def on_command_start(context, command):
        print(f"  Starting: {command.keyword.name}")
    
    def on_measurement(context, data):
        print(f"  Measurement #{data['count']} at filter position {data['filter_wheel_1']}")
    
    executor.register_callback("on_command_start", on_command_start)
    executor.register_callback("on_measurement", on_measurement)
    
    # Execute routine
    print("\nExecuting routine:")
    result = executor.execute(routine)
    
    print(f"\nExecution completed!")
    print(f"  State: {result.state.name}")
    print(f"  Measurements: {result.measurement_count}")
    print(f"  Errors: {result.error_count}")


def example_routine_with_loop():
    """Example: Creating and executing a routine with loops."""
    print("\n=== Routine with Loop Variables ===\n")
    
    # Create routine that loops through zenith angles
    routine_content = """
    DESCRIPTION -> Sky scan at multiple angles
    SET FILTERWHEELS -> FW1=OPEN; FW2=DIFF
    SET SPECTROMETER -> IT=100; NCYCLES=10
    START LOOP -> XIJ=[30,45,60,75]
    SET POINTING -> ZEN=XIJ; AZI=180; ZENMODE=ABS; AZIMODE=ABS
    MEASURE -> DISPLAY=MEAN; SAVE=STDERR
    STOP LOOP
    """
    
    routine = Routine.from_string("SL", routine_content)
    
    # List commands
    print("Routine commands:")
    for i, cmd in enumerate(routine.commands):
        print(f"  {i+1}. {cmd.keyword.name}")
        if cmd.subkeywords:
            for k, v in cmd.subkeywords.items():
                print(f"      {k}={v}")


def main():
    """Run all examples."""
    print("=" * 60)
    print("SciGlob Automation Examples")
    print("=" * 60)
    
    # Run examples
    example_load_routine()
    example_load_all_routines()
    example_load_schedule()
    example_astronomical_calculations()
    example_calculate_schedule_times()
    example_execute_routine()
    example_routine_with_loop()
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()

