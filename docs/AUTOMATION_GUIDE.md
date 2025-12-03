# SciGlob Automation Guide

This guide covers the automated measurement capabilities of the SciGlob library, including routines and schedules that follow the Blick software pattern.

## Overview

The automation module provides:

- **Routines**: Predefined measurement sequences (similar to Blick `.rout` files)
- **Schedules**: Time-based execution of routine sequences (similar to Blick `.sked` files)
- **Astronomical Timing**: Calculate sunrise/sunset, solar/lunar positions for schedule timing

## Table of Contents

1. [Routines](#routines)
2. [Schedules](#schedules)
3. [Execution](#execution)
4. [Astronomical Timing](#astronomical-timing)
5. [Examples](#examples)

---

## Routines

Routines are predefined measurement sequences identified by a two-letter code (e.g., "DS" for direct sun, "SS" for sun search).

### Routine File Format

Routine files use the `.rout` extension and contain keyword-based commands:

```
# Comments start with #
DESCRIPTION -> Brief description of the routine

SET POINTING -> DELTA=MIDDLE; ZEN=0; AZI=0; ZENMODE=RELSUN; AZIMODE=RELSUN
SET FILTERWHEELS -> FW1=OPEN; FW2=DIFF
SET SPECTROMETER -> IT=100; NCYCLES=10; NREPETITIONS=5
CHECK INTENSITY -> ADJUSTIT=FROMCURRENT; %SATURATION=80
MEASURE -> DISPLAY=MEAN; SAVE=STDERR
```

### Keywords

| Keyword | Description | Subkeywords |
|---------|-------------|-------------|
| `DESCRIPTION` | Routine description | (text value) |
| `SET POINTING` | Configure tracker position | DELTA, AZI, ZEN, AZIMODE, ZENMODE |
| `SET FILTERWHEELS` | Configure filter positions | FUNCFILT, FW1, FW2 |
| `SET SHADOWBAND` | Configure shadowband | SBZEN, SBZENMODE |
| `SET SPECTROMETER` | Configure spectrometer | IT, NCYCLES, NREPETITIONS, DURATION, DARKRATIO |
| `CHECK INTENSITY` | Adjust intensity settings | ADJUSTIT, ADJUSTND, %SATURATION, DARKESTIMATION, ITLIMIT |
| `MEASURE` | Perform measurement | DISPLAY, SAVE, SATCHECK |
| `PROCESSINFO` | Set processing metadata | TYPE, DISTANCE |
| `DURATION` | Wait for duration | LENGTH, TIMEMODE |
| `START LOOP` | Begin loop | XIJ |
| `STOP LOOP` | End loop | (none) |

### Pointing Modes

- `ABS` - Absolute angles
- `RELSUN` - Relative to sun position
- `RELMOON` - Relative to moon position
- `ANGSUN` - Fixed scattering angle relative to sun
- `ANGMOON` - Fixed scattering angle relative to moon

### Loop Variables (XIJ)

Loop variables allow iterating through values:

```
START LOOP -> XIJ=30,45,60,75,90
SET POINTING -> ZEN=XIJ; AZI=180
MEASURE -> DISPLAY=MEAN
STOP LOOP
```

You can also use multi-dimensional XIJ values:

```
START LOOP -> XIJ=[(30,0),(45,90),(60,180)]
SET POINTING -> ZEN=XIJ(1); AZI=XIJ(2)
MEASURE -> DISPLAY=MEAN
STOP LOOP
```

### Loading Routines

```python
from sciglob.automation import Routine, RoutineReader

# Load from file
routine = Routine.from_file("routines/DS.rout")

# Create from string
routine = Routine.from_string("TT", '''
DESCRIPTION -> Test routine
SET SPECTROMETER -> IT=100; NCYCLES=10
MEASURE -> DISPLAY=MEAN
''')

# Load all routines from directory
reader = RoutineReader()
routines = reader.read_all_routines("routines/")
```

---

## Schedules

Schedules define when to execute routine sequences based on time references.

### Schedule File Format

Schedule files use the `.sked` extension:

```
# Comments start with #

{
    'label' -> 'morning_sunsearch',
    'start' -> 'solarzen90am+00:30',
    'priority' -> 10,
    'commands' -> 'SS'
}

{
    'label' -> 'direct_sun_measurements',
    'start' -> 'THEN+00:05',
    'end' -> 'localnoon',
    'repetitions' -> -1,
    'priority' -> 8,
    'commands' -> 'DS5'
}
```

### Schedule Entry Keywords

| Keyword | Required | Description |
|---------|----------|-------------|
| `label` | Yes | Unique identifier |
| `start` | Yes | Start time reference |
| `end` | No | End time reference |
| `commands` | Yes | Routine sequence (e.g., "DS", "DS5", "SSDS") |
| `priority` | Yes | Execution priority (higher = more important) |
| `repetitions` | No | Number of repetitions (-1 for unlimited until end) |
| `startwith` | No | Routine to execute once before main commands |
| `refrout` | No | Reference routine for time calculation |
| `reftime` | No | Reference time: "b" (beginning), "m" (middle), "e" (end) |
| `if` | No | Conditional execution |

### Time References

| Reference | Description |
|-----------|-------------|
| `localmidnight` | Local midnight |
| `localnoon` | Local solar noon |
| `solarzen90am` | Sunrise (solar zenith = 90°) |
| `solarzen90pm` | Sunset (solar zenith = 90°) |
| `sunrise` | Same as solarzen90am |
| `sunset` | Same as solarzen90pm |
| `moonrise` | Moon rise |
| `moonset` | Moon set |
| `THEN` | After previous entry completes |
| `HH:MM:SS` | Absolute UTC time |

Time references can include offsets: `sunrise+01:30`, `sunset-00:30`

### Routine Sequences

Commands can be combined and repeated:
- `DS` - Execute DS routine once
- `DS5` - Execute DS routine 5 times
- `SSDS` - Execute SS, then DS
- `SS2DS3` - Execute SS twice, then DS three times

### Conditions

```
'if' -> 'sun_visible'      # Execute only when sun is above horizon
'if' -> 'moon_visible'     # Execute only when moon is above horizon
'if' -> 'monthday_15'      # Execute only on the 15th of the month
'if' -> 'moonphase_full'   # Execute only during full moon
```

### Loading Schedules

```python
from sciglob.automation import Schedule, ScheduleReader

# Load from file
schedule = Schedule.from_file("schedules/daily.sked")

# With routine validation
from sciglob.automation import RoutineReader
reader = RoutineReader()
routines = reader.read_all_routines("routines/")
schedule = Schedule.from_file("schedules/daily.sked", routines)

# Validate schedule
errors = schedule.validate(routines)
if errors:
    print(f"Validation errors: {errors}")
```

---

## Execution

### Routine Executor

Execute individual routines:

```python
from sciglob.automation import RoutineExecutor
from sciglob import HeadSensor

# With hardware
with HeadSensor(port="/dev/ttyUSB0") as hs:
    executor = RoutineExecutor(
        head_sensor=hs,
        tracker=hs.tracker,
        latitude=40.0,
        longitude=-105.0
    )
    
    # Register callbacks
    def on_measurement(context, data):
        print(f"Measurement: {data}")
    
    executor.register_callback("on_measurement", on_measurement)
    
    # Execute routine
    result = executor.execute(routine)
    print(f"Completed: {result.measurement_count} measurements")
```

### Schedule Executor

Run a complete schedule:

```python
from sciglob.automation import ScheduleExecutor

# Create executor
executor = ScheduleExecutor(
    schedule=schedule,
    routines=routines,  # List of Routine objects
    head_sensor=hs,
    latitude=40.0,
    longitude=-105.0
)

# Calculate today's times
executor.calculate_times()

# View calculated times
for entry in schedule.entries:
    print(f"{entry.label}: {entry.computed_start}")

# Start execution (runs in background)
executor.start()

# Later, stop execution
executor.stop()
```

### Execution Callbacks

Available callbacks:

| Callback | Arguments | Description |
|----------|-----------|-------------|
| `on_routine_start` | routine | When routine begins |
| `on_routine_complete` | routine | When routine ends |
| `on_command_start` | command | Before each command |
| `on_command_complete` | command | After each command |
| `on_measurement` | data | When measurement is taken |
| `on_error` | error | When error occurs |
| `on_entry_start` | entry | When schedule entry begins |
| `on_entry_complete` | entry | When schedule entry ends |

---

## Astronomical Timing

### Time Calculator

```python
from sciglob.automation import TimeCalculator
from datetime import datetime, timezone

# Create calculator for location
calculator = TimeCalculator(
    latitude=40.0,    # degrees, positive=north
    longitude=-105.0,  # degrees, positive=east
    altitude=1500.0    # meters
)

# Get current solar position
now = datetime.now(timezone.utc)
solar = calculator.calculate_solar_position(now)

print(f"Zenith: {solar.zenith_angle:.1f}°")
print(f"Azimuth: {solar.azimuth:.1f}°")
print(f"Daytime: {solar.is_daytime}")

# Get lunar position
lunar = calculator.calculate_lunar_position(now)
print(f"Moon phase: {lunar.phase:.2f}")
print(f"Illumination: {lunar.illumination:.1%}")

# Get daily events
events = calculator.calculate_events(now)
print(f"Sunrise: {events.sunrise}")
print(f"Solar noon: {events.solar_noon}")
print(f"Sunset: {events.sunset}")
print(f"Day length: {events.day_length}")
```

### Convenience Functions

```python
from sciglob.automation import calculate_solar_position, calculate_lunar_position

# Quick solar position calculation
solar = calculate_solar_position(latitude=40.0, longitude=-105.0)
print(f"Sun zenith: {solar.zenith_angle}°")

# Quick lunar position calculation
lunar = calculate_lunar_position(latitude=40.0, longitude=-105.0)
print(f"Moon visible: {lunar.is_above_horizon}")
```

---

## Examples

### Example 1: Direct Sun Routine

File: `routines/DS.rout`
```
DESCRIPTION -> Direct sun measurement with intensity adjustment

CHECK INTENSITY -> ADJUSTIT=FROMCURRENT; ADJUSTND=FROMMAX; %SATURATION=80
SET POINTING -> DELTA=MIDDLE; ZEN=0; AZI=0; ZENMODE=RELSUN; AZIMODE=RELSUN
SET FILTERWHEELS -> FUNCFILT=OPEN
SET SPECTROMETER -> IT=CURRENT; NCYCLES=10; NREPETITIONS=5
PROCESSINFO -> TYPE=SUN
MEASURE -> DISPLAY=MEAN; SAVE=STDERR; SATCHECK=YES
```

### Example 2: Sky Scan Routine

File: `routines/SK.rout`
```
DESCRIPTION -> Sky scan at multiple zenith angles

SET FILTERWHEELS -> FUNCFILT=OPEN; FW2=DIFF
SET SPECTROMETER -> IT=100; NCYCLES=20; NREPETITIONS=3
PROCESSINFO -> TYPE=SKY

START LOOP -> XIJ=30,45,60,75,85
SET POINTING -> ZEN=XIJ; AZI=0; ZENMODE=ABS; AZIMODE=RELSUN
MEASURE -> DISPLAY=MEAN; SAVE=STDERR
STOP LOOP
```

### Example 3: Daily Schedule

File: `schedules/daily.sked`
```
# Morning sun search at sunrise
{
    'label' -> 'morning_sunsearch',
    'start' -> 'sunrise+00:30',
    'priority' -> 10,
    'commands' -> 'SS',
    'if' -> 'sun_visible'
}

# Direct sun measurements until noon
{
    'label' -> 'morning_directsun',
    'start' -> 'THEN+00:05',
    'end' -> 'localnoon',
    'repetitions' -> -1,
    'priority' -> 8,
    'commands' -> 'DS'
}

# Midday sky scan
{
    'label' -> 'midday_skyscan',
    'start' -> 'localnoon-00:15',
    'priority' -> 7,
    'commands' -> 'SK'
}

# Afternoon measurements
{
    'label' -> 'afternoon_directsun',
    'start' -> 'localnoon+00:30',
    'end' -> 'sunset-01:00',
    'repetitions' -> -1,
    'priority' -> 8,
    'commands' -> 'DS'
}
```

### Example 4: Complete Python Script

```python
#!/usr/bin/env python3
"""Complete automation example."""

from pathlib import Path
from sciglob import HeadSensor
from sciglob.automation import (
    Routine, RoutineReader,
    Schedule, ScheduleExecutor,
    TimeCalculator
)

# Location
LATITUDE = 40.0
LONGITUDE = -105.0

# Paths
ROUTINES_DIR = Path("routines")
SCHEDULE_FILE = Path("schedules/daily.sked")

def main():
    # Load all routines
    reader = RoutineReader()
    routines = reader.read_all_routines(ROUTINES_DIR)
    print(f"Loaded {len(routines)} routines")
    
    # Load schedule
    schedule = Schedule.from_file(SCHEDULE_FILE, routines)
    print(f"Loaded schedule with {len(schedule.entries)} entries")
    
    # Validate
    errors = schedule.validate(routines)
    if errors:
        print(f"Validation errors: {errors}")
        return
    
    # Connect to hardware
    with HeadSensor(port="/dev/ttyUSB0") as hs:
        # Create executor
        executor = ScheduleExecutor(
            schedule=schedule,
            routines=routines,
            head_sensor=hs,
            latitude=LATITUDE,
            longitude=LONGITUDE
        )
        
        # Calculate times
        executor.calculate_times()
        
        # Print schedule
        print("\nToday's schedule:")
        for entry in schedule.entries:
            if entry.computed_start:
                print(f"  {entry.computed_start.strftime('%H:%M')} - {entry.label}")
        
        # Start schedule
        print("\nStarting schedule...")
        executor.start()
        
        # Wait for user to stop
        try:
            input("Press Enter to stop...")
        except KeyboardInterrupt:
            pass
        
        executor.stop()
        print("Schedule stopped.")

if __name__ == "__main__":
    main()
```

---

## Error Handling

```python
from sciglob.automation import (
    AutomationError,
    RoutineError,
    ScheduleError,
    RoutineParseError,
    ScheduleParseError,
    RoutineNotFoundError,
    ExecutionError
)

try:
    routine = Routine.from_file("nonexistent.rout")
except RoutineNotFoundError as e:
    print(f"Routine not found: {e}")

try:
    schedule = Schedule.from_file("invalid.sked")
except ScheduleParseError as e:
    print(f"Parse error at line {e.line_number}: {e}")

try:
    result = executor.execute(routine)
except ExecutionError as e:
    print(f"Execution failed: {e.command}")
```

---

## Comparison with Blick

| Blick | SciGlob | Notes |
|-------|---------|-------|
| `.rout` files | `Routine` class | Same format supported |
| `.sked` files | `Schedule` class | Same format supported |
| `blick_routinereader` | `RoutineReader` | Similar API |
| `blick_atmos` | `TimeCalculator` | Astronomical calculations |
| System status | `ExecutionContext` | Execution state tracking |

The SciGlob automation module is designed to be compatible with Blick routine and schedule files, making it easy to migrate existing measurement configurations.

