# SciGlob Library - Quick Reference Guide

## Version 0.1.4

A complete reference of all functions and methods with practical examples.

---

## Table of Contents

1. [Library Functions](#1-library-functions)
2. [HeadSensor](#2-headsensor)
3. [Tracker](#3-tracker)
4. [FilterWheel](#4-filterwheel)
5. [Shadowband](#5-shadowband)
6. [TemperatureController](#6-temperaturecontroller)
7. [HumiditySensor](#7-humiditysensor)
8. [GlobalSatGPS](#8-globalsatgps)
9. [NovatelGPS](#9-novatelgps)
10. [Configuration Classes](#10-configuration-classes)
11. [Utility Functions](#11-utility-functions)
12. [Exceptions](#12-exceptions)

---

## 1. Library Functions

### `sciglob.help()`
Display library overview and usage information.

```python
import sciglob
sciglob.help()
```

### `sciglob.help_config()`
Display configuration help and YAML examples.

```python
import sciglob
sciglob.help_config()
```

---

## 2. HeadSensor

The main communication hub for all SciGlob instruments.

### Import
```python
from sciglob import HeadSensor
```

### Constructor
```python
HeadSensor(
    port=None,              # Serial port (e.g., 'COM3', '/dev/ttyUSB0')
    baudrate=9600,          # Communication speed
    timeout=1.0,            # Command timeout in seconds
    name="HeadSensor",      # Device name for logging
    sensor_type=None,       # 'SciGlobHSN1' or 'SciGlobHSN2'
    fw1_filters=None,       # List of 9 filter names for FW1
    fw2_filters=None,       # List of 9 filter names for FW2
    tracker_type="Directed Perceptions",  # or 'LuftBlickTR1'
    degrees_per_step=0.01,  # Motor resolution
    motion_limits=None,     # [zen_min, zen_max, azi_min, azi_max]
    home_position=None,     # [zenith_home, azimuth_home]
    config=None,            # HeadSensorConfig object
    serial_config=None,     # SerialConfig object
)
```

### Example: Basic Usage
```python
from sciglob import HeadSensor

# Simple connection
hs = HeadSensor(port='/dev/ttyUSB0')
hs.connect()
print(f"Connected to: {hs.device_id}")
hs.disconnect()

# Using context manager (recommended)
with HeadSensor(port='/dev/ttyUSB0') as hs:
    print(f"Device: {hs.device_id}")
    print(f"Type: {hs.sensor_type}")
```

### Example: With Configuration
```python
from sciglob import HeadSensor
from sciglob.config import HeadSensorConfig, SerialConfig

config = HeadSensorConfig(
    serial=SerialConfig(port='COM3', baudrate=9600),
    tracker_type='LuftBlickTR1',
    degrees_per_step=0.01,
    motion_limits=[0, 90, 0, 360],
    home_position=[0.0, 180.0],
    fw1_filters=['OPEN', 'U340', 'BP300', 'LPNIR', 'ND1', 'ND2', 'ND3', 'ND4', 'OPAQUE'],
)

with HeadSensor(config=config) as hs:
    print(f"Tracker: {hs.tracker_type}")
```

---

### HeadSensor Methods

#### `connect()`
Establish connection to the head sensor.
```python
hs = HeadSensor(port='/dev/ttyUSB0')
hs.connect()
print(f"Connected: {hs.is_connected}")
```

#### `disconnect()`
Close the connection.
```python
hs.disconnect()
print(f"Connected: {hs.is_connected}")  # False
```

#### `get_id()`
Get device identification string.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    device_id = hs.get_id()
    print(f"Device ID: {device_id}")  # "SciGlobHSN2"
```

#### `get_temperature()`
Read head sensor temperature (SciGlobHSN2 only).
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    if hs.sensor_type == "SciGlobHSN2":
        temp = hs.get_temperature()
        print(f"Temperature: {temp}°C")
```

#### `get_humidity()`
Read head sensor humidity (SciGlobHSN2 only).
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    humidity = hs.get_humidity()
    print(f"Humidity: {humidity}%")
```

#### `get_pressure()`
Read head sensor pressure (SciGlobHSN2 only).
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    pressure = hs.get_pressure()
    print(f"Pressure: {pressure} mbar")
```

#### `get_all_sensors()`
Read all sensor values at once.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    sensors = hs.get_all_sensors()
    print(f"Temperature: {sensors['temperature']}°C")
    print(f"Humidity: {sensors['humidity']}%")
    print(f"Pressure: {sensors['pressure']} mbar")
```

#### `send_command(command, timeout=None)`
Send a raw command to the head sensor.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    response = hs.send_command("?")
    print(f"Response: {response}")
```

#### `power_reset(device)`
Power cycle a connected device.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.power_reset("tracker")  # Reset tracker
    hs.power_reset("S1")       # Reset device S1
```

#### `get_status()`
Get comprehensive status information.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    status = hs.get_status()
    print(f"Connected: {status['connected']}")
    print(f"Port: {status['port']}")
    print(f"Device ID: {status['device_id']}")
```

#### `help(method=None)`
Display help information.
```python
hs = HeadSensor()
hs.help()                    # Full help
hs.help('connect')           # Help for connect method
```

#### `list_methods()`
List all available methods.
```python
hs = HeadSensor()
methods = hs.list_methods()
print(methods)  # ['connect', 'disconnect', 'get_id', ...]
```

#### `list_properties()`
List all properties.
```python
hs = HeadSensor()
props = hs.list_properties()
print(props)  # ['device_id', 'is_connected', 'tracker', ...]
```

---

### HeadSensor Properties

```python
hs = HeadSensor(port='/dev/ttyUSB0')

# Connection properties
hs.port                  # Serial port path
hs.baudrate              # Communication speed
hs.is_connected          # Connection status (bool)

# Device properties
hs.device_id             # Device ID string
hs.sensor_type           # 'SciGlobHSN1' or 'SciGlobHSN2'

# Tracker properties
hs.tracker_type          # 'Directed Perceptions' or 'LuftBlickTR1'
hs.degrees_per_step      # Motor resolution
hs.motion_limits         # [zen_min, zen_max, azi_min, azi_max]
hs.home_position         # [zenith_home, azimuth_home]

# Filter wheel properties
hs.fw1_filters           # List of FW1 filter names
hs.fw2_filters           # List of FW2 filter names

# Sub-device access
hs.tracker               # Tracker instance
hs.filter_wheel_1        # FilterWheel instance (FW1)
hs.filter_wheel_2        # FilterWheel instance (FW2)
hs.shadowband            # Shadowband instance
```

---

## 3. Tracker

Controls azimuth (pan) and zenith (tilt) motors.

### Access
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    tracker = hs.tracker
```

---

### Tracker Methods

#### `get_position()`
Get current position in degrees.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    zenith, azimuth = hs.tracker.get_position()
    print(f"Zenith: {zenith}°, Azimuth: {azimuth}°")
```

#### `get_position_steps()`
Get current position in steps.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    azi_steps, zen_steps = hs.tracker.get_position_steps()
    print(f"Steps: azimuth={azi_steps}, zenith={zen_steps}")
```

#### `move_to(zenith=None, azimuth=None, wait=True)`
Move to position in degrees.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    # Move both axes
    hs.tracker.move_to(zenith=45.0, azimuth=180.0)
    
    # Move zenith only
    hs.tracker.move_to(zenith=30.0)
    
    # Move azimuth only
    hs.tracker.move_to(azimuth=90.0)
    
    # Non-blocking move
    hs.tracker.move_to(zenith=45.0, azimuth=180.0, wait=False)
```

#### `move_to_steps(zenith_steps=None, azimuth_steps=None, wait=True)`
Move to position in steps.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.tracker.move_to_steps(zenith_steps=4500, azimuth_steps=-1200)
```

#### `move_relative(delta_zenith=0.0, delta_azimuth=0.0, wait=True)`
Move relative to current position.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    # Move 10° up, 20° left
    hs.tracker.move_relative(delta_zenith=10.0, delta_azimuth=-20.0)
```

#### `pan(azimuth, wait=True)`
Move azimuth only.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.tracker.pan(azimuth=90.0)
```

#### `tilt(zenith, wait=True)`
Move zenith only.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.tracker.tilt(zenith=45.0)
```

#### `home(wait=True)`
Move to home position.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.tracker.home()
    print("Tracker at home position")
```

#### `park(zenith=90.0, azimuth=0.0, wait=True)`
Move to parking position.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.tracker.park()  # Default: zenith=90°, azimuth=0°
    hs.tracker.park(zenith=85.0, azimuth=180.0)  # Custom
```

#### `reset()`
Soft reset the tracker.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    success = hs.tracker.reset()
    print(f"Reset successful: {success}")
```

#### `power_reset()`
Power cycle the tracker.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    success = hs.tracker.power_reset()
    print(f"Power reset successful: {success}")
```

#### `get_motor_temperatures()` *(LuftBlickTR1 only)*
Get motor temperatures.
```python
with HeadSensor(port='/dev/ttyUSB0', tracker_type='LuftBlickTR1') as hs:
    temps = hs.tracker.get_motor_temperatures()
    print(f"Azimuth motor: {temps['azimuth_motor_temp']}°C")
    print(f"Zenith motor: {temps['zenith_motor_temp']}°C")
```

#### `get_motor_alarms()` *(LuftBlickTR1 only)*
Get motor alarm status.
```python
with HeadSensor(port='/dev/ttyUSB0', tracker_type='LuftBlickTR1') as hs:
    alarms = hs.tracker.get_motor_alarms()
    print(f"Zenith alarm: {alarms['zenith']}")   # (code, message)
    print(f"Azimuth alarm: {alarms['azimuth']}")
```

#### `check_alarms()` *(LuftBlickTR1 only)*
Check for alarms and raise exception if found.
```python
from sciglob import HeadSensor, MotorAlarmError

with HeadSensor(port='/dev/ttyUSB0', tracker_type='LuftBlickTR1') as hs:
    try:
        hs.tracker.check_alarms()
        print("No alarms")
    except MotorAlarmError as e:
        print(f"Alarm on {e.axis}: code {e.alarm_code}")
```

#### `get_magnetic_position_steps()` *(LuftBlickTR1 only)*
Get absolute encoder position.
```python
with HeadSensor(port='/dev/ttyUSB0', tracker_type='LuftBlickTR1') as hs:
    azi_steps, zen_steps = hs.tracker.get_magnetic_position_steps()
    print(f"Magnetic: azimuth={azi_steps}, zenith={zen_steps}")
```

#### `get_status()`
Get tracker status.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    status = hs.tracker.get_status()
    print(status)
```

#### `help(method=None)`
Display help.
```python
tracker.help()
tracker.help('move_to')
```

---

### Tracker Properties

```python
tracker.tracker_type          # 'Directed Perceptions' or 'LuftBlickTR1'
tracker.degrees_per_step      # Resolution
tracker.is_luftblick          # True if LuftBlickTR1
tracker.zenith_home           # Zenith home position (degrees)
tracker.azimuth_home          # Azimuth home position (degrees)
tracker.zenith_limits         # (min, max) degrees
tracker.azimuth_limits        # (min, max) degrees
```

---

## 4. FilterWheel

Controls filter wheel selection (9 positions per wheel).

### Access
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    fw1 = hs.filter_wheel_1
    fw2 = hs.filter_wheel_2
```

---

### FilterWheel Methods

#### `set_position(position)`
Set filter wheel to position (1-9).
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.filter_wheel_1.set_position(1)  # Position 1
    hs.filter_wheel_1.set_position(5)  # Position 5
```

#### `set_filter(filter_name)`
Set filter by name.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.filter_wheel_1.set_filter("OPEN")
    hs.filter_wheel_1.set_filter("U340")
    hs.filter_wheel_1.set_filter("open")  # Case-insensitive
```

#### `reset()`
Reset to home position (position 1).
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.filter_wheel_1.reset()
```

#### `get_filter_map()`
Get position to filter name mapping.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    filter_map = hs.filter_wheel_1.get_filter_map()
    print(filter_map)  # {1: 'OPEN', 2: 'U340', ...}
```

#### `get_position_for_filter(filter_name)`
Get position for a filter name.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    pos = hs.filter_wheel_1.get_position_for_filter("U340")
    print(f"U340 is at position {pos}")  # 2
```

#### `get_available_filters()`
Get list of all filter names.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    filters = hs.filter_wheel_1.get_available_filters()
    print(filters)  # ['OPEN', 'U340', 'BP300', ...]
```

#### `get_status()`
Get filter wheel status.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    status = hs.filter_wheel_1.get_status()
    print(f"Position: {status['position']}")
    print(f"Filter: {status['current_filter']}")
```

#### `help(method=None)`
Display help.
```python
fw1.help()
```

---

### FilterWheel Properties

```python
fw1.wheel_id          # 1 or 2
fw1.device_id         # 'F1' or 'F2'
fw1.position          # Current position (1-9)
fw1.current_filter    # Current filter name
fw1.filter_names      # List of filter names
fw1.num_positions     # Number of positions (9)
```

---

## 5. Shadowband

Controls the shadowband arm position.

### Access
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    sb = hs.shadowband
```

---

### Shadowband Methods

#### `move_to_position(position)`
Move to step position.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.shadowband.move_to_position(500)
    hs.shadowband.move_to_position(-300)  # Negative allowed
```

#### `move_to_angle(angle)`
Move to specified angle.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.shadowband.move_to_angle(45.0)
```

#### `move_relative(delta_steps)`
Move relative to current position.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.shadowband.move_relative(100)   # Forward 100 steps
    hs.shadowband.move_relative(-50)   # Back 50 steps
```

#### `reset()`
Reset to home position.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    hs.shadowband.reset()
```

#### `get_status()`
Get shadowband status.
```python
with HeadSensor(port='/dev/ttyUSB0') as hs:
    status = hs.shadowband.get_status()
    print(f"Position: {status['position']} steps")
    print(f"Angle: {status['angle']}°")
```

#### `help(method=None)`
Display help.
```python
sb.help()
```

---

### Shadowband Properties

```python
sb.position      # Current position (steps)
sb.angle         # Current angle (degrees)
sb.resolution    # Degrees per step (default 0.36)
sb.ratio         # Offset/radius ratio (default 0.5)
```

---

## 6. TemperatureController

Controls TETech temperature controllers.

### Import
```python
from sciglob import TemperatureController
```

### Constructor
```python
TemperatureController(
    port=None,                    # Serial port
    baudrate=9600,                # Communication speed
    timeout=1.0,                  # Timeout
    name="TempController",        # Device name
    controller_type="TETech1",    # 'TETech1' or 'TETech2'
    config=None,                  # TemperatureControllerConfig
    serial_config=None,           # SerialConfig
)
```

### Example
```python
from sciglob import TemperatureController

with TemperatureController(port='COM4', controller_type='TETech1') as tc:
    tc.set_temperature(25.0)
    tc.enable_output()
    
    temp = tc.get_temperature()
    print(f"Current: {temp}°C")
```

---

### TemperatureController Methods

#### `connect()`
Connect to the controller.
```python
tc = TemperatureController(port='COM4')
tc.connect()
```

#### `disconnect()`
Disconnect from the controller.
```python
tc.disconnect()
```

#### `set_temperature(temperature)`
Set target temperature.
```python
with TemperatureController(port='COM4') as tc:
    tc.set_temperature(25.0)
```

#### `get_temperature()`
Get control sensor temperature.
```python
with TemperatureController(port='COM4') as tc:
    temp = tc.get_temperature()
    print(f"Temperature: {temp}°C")
```

#### `get_secondary_temperature()`
Get secondary sensor temperature.
```python
with TemperatureController(port='COM4') as tc:
    temp = tc.get_secondary_temperature()
    print(f"Secondary: {temp}°C")
```

#### `get_setpoint()`
Get current temperature setpoint.
```python
with TemperatureController(port='COM4') as tc:
    setpoint = tc.get_setpoint()
    print(f"Setpoint: {setpoint}°C")
```

#### `set_bandwidth(bandwidth)`
Set proportional bandwidth (PID parameter).
```python
with TemperatureController(port='COM4') as tc:
    tc.set_bandwidth(10.0)
```

#### `set_integral_gain(gain)`
Set integral gain (PID parameter).
```python
with TemperatureController(port='COM4') as tc:
    tc.set_integral_gain(0.5)
```

#### `enable_output()`
Enable temperature control output.
```python
with TemperatureController(port='COM4') as tc:
    tc.enable_output()
```

#### `disable_output()`
Disable temperature control output.
```python
with TemperatureController(port='COM4') as tc:
    tc.disable_output()
```

#### `get_status()`
Get controller status.
```python
with TemperatureController(port='COM4') as tc:
    status = tc.get_status()
    print(status)
```

#### `help(method=None)`
Display help.
```python
tc.help()
```

---

### TemperatureController Properties

```python
tc.controller_type    # 'TETech1' or 'TETech2'
tc.nbits              # Bit width (16 or 32)
tc.is_connected       # Connection status
```

---

## 7. HumiditySensor

Interfaces with HDC2080EVM humidity sensors.

### Import
```python
from sciglob import HumiditySensor
```

### Constructor
```python
HumiditySensor(
    port=None,               # Serial port
    baudrate=9600,           # Communication speed
    timeout=1.0,             # Timeout
    name="HumiditySensor",   # Device name
    config=None,             # HumiditySensorConfig
    serial_config=None,      # SerialConfig
)
```

### Example
```python
from sciglob import HumiditySensor

with HumiditySensor(port='COM5') as hs:
    readings = hs.get_readings()
    print(f"Temperature: {readings['temperature']}°C")
    print(f"Humidity: {readings['humidity']}%")
```

---

### HumiditySensor Methods

#### `connect()`
Connect to the sensor.
```python
hs = HumiditySensor(port='COM5')
hs.connect()
```

#### `disconnect()`
Disconnect from the sensor.
```python
hs.disconnect()
```

#### `initialize()`
Initialize the sensor (stop streaming).
```python
with HumiditySensor(port='COM5') as hs:
    hs.initialize()
```

#### `get_temperature()`
Get temperature reading.
```python
with HumiditySensor(port='COM5') as hs:
    temp = hs.get_temperature()
    print(f"Temperature: {temp}°C")
```

#### `get_humidity()`
Get humidity reading.
```python
with HumiditySensor(port='COM5') as hs:
    humidity = hs.get_humidity()
    print(f"Humidity: {humidity}%")
```

#### `get_readings()`
Get both temperature and humidity.
```python
with HumiditySensor(port='COM5') as hs:
    readings = hs.get_readings()
    print(f"Temperature: {readings['temperature']}°C")
    print(f"Humidity: {readings['humidity']}%")
```

#### `get_status()`
Get sensor status.
```python
with HumiditySensor(port='COM5') as hs:
    status = hs.get_status()
    print(status)
```

#### `help(method=None)`
Display help.
```python
hs.help()
```

---

### HumiditySensor Properties

```python
hs.is_connected      # Connection status
hs.is_initialized    # Initialization status
```

---

## 8. GlobalSatGPS

Simple GPS receiver using NMEA protocol.

### Import
```python
from sciglob import GlobalSatGPS
```

### Constructor
```python
GlobalSatGPS(
    port=None,              # Serial port
    baudrate=9600,          # Communication speed
    timeout=2.0,            # Timeout
    name="GlobalSatGPS",    # Device name
    config=None,            # GPSConfig
    serial_config=None,     # SerialConfig
)
```

### Example
```python
from sciglob import GlobalSatGPS

with GlobalSatGPS(port='COM6') as gps:
    pos = gps.get_position()
    if pos['quality'] > 0:
        print(f"Lat: {pos['latitude']:.6f}")
        print(f"Lon: {pos['longitude']:.6f}")
        print(f"Alt: {pos['altitude']:.1f}m")
        print(f"Satellites: {pos['satellites']}")
    else:
        print("No GPS fix")
```

---

### GlobalSatGPS Methods

#### `connect()`
Connect to the GPS.
```python
gps = GlobalSatGPS(port='COM6')
gps.connect()
```

#### `disconnect()`
Disconnect from the GPS.
```python
gps.disconnect()
```

#### `configure()`
Configure the GPS (disable automatic messages).
```python
with GlobalSatGPS(port='COM6') as gps:
    gps.configure()
```

#### `get_position()`
Get current GPS position.
```python
with GlobalSatGPS(port='COM6') as gps:
    pos = gps.get_position()
    # Returns: {
    #   'latitude': float,      # Decimal degrees (+ = North)
    #   'longitude': float,     # Decimal degrees (+ = East)
    #   'altitude': float,      # Meters above sea level
    #   'quality': int,         # 0 = no fix, 1 = GPS, 2 = DGPS
    #   'satellites': int,      # Number of satellites
    # }
```

#### `get_status()`
Get GPS status.
```python
with GlobalSatGPS(port='COM6') as gps:
    status = gps.get_status()
    print(status)
```

#### `help(method=None)`
Display help.
```python
gps.help()
```

---

## 9. NovatelGPS

GPS + Gyroscope for position and orientation.

### Import
```python
from sciglob import NovatelGPS
```

### Constructor
```python
NovatelGPS(
    port=None,            # Serial port
    baudrate=9600,        # Communication speed
    timeout=2.0,          # Timeout
    name="NovatelGPS",    # Device name
    config=None,          # GPSConfig
    serial_config=None,   # SerialConfig
)
```

### Example
```python
from sciglob import NovatelGPS

with NovatelGPS(port='COM7') as gps:
    pos = gps.get_position()
    orient = gps.get_orientation()
    
    print(f"Lat: {pos['latitude']:.6f}")
    print(f"Lon: {pos['longitude']:.6f}")
    print(f"Roll: {orient['roll']:.2f}°")
    print(f"Pitch: {orient['pitch']:.2f}°")
    print(f"Yaw: {orient['yaw']:.2f}°")
```

---

### NovatelGPS Methods

#### `connect()`
Connect to the Novatel system.
```python
gps = NovatelGPS(port='COM7')
gps.connect()
```

#### `disconnect()`
Disconnect from the system.
```python
gps.disconnect()
```

#### `configure()`
Configure the Novatel.
```python
with NovatelGPS(port='COM7') as gps:
    gps.configure()
```

#### `get_position()`
Get current GPS position.
```python
with NovatelGPS(port='COM7') as gps:
    pos = gps.get_position()
    # Returns: {
    #   'latitude': float,
    #   'longitude': float,
    #   'altitude': float,
    #   'status': str,  # 'INS_SOLUTION_GOOD', etc.
    # }
```

#### `get_orientation()`
Get current orientation from gyroscope.
```python
with NovatelGPS(port='COM7') as gps:
    orient = gps.get_orientation()
    # Returns: {
    #   'roll': float,   # East-West tilt (degrees)
    #   'pitch': float,  # North-South tilt (degrees)
    #   'yaw': float,    # Azimuth (degrees)
    # }
```

#### `start_logging(interval=1.0)`
Start continuous logging.
```python
with NovatelGPS(port='COM7') as gps:
    gps.start_logging(interval=1.0)  # Log every 1 second
```

#### `stop_logging()`
Stop continuous logging.
```python
with NovatelGPS(port='COM7') as gps:
    gps.stop_logging()
```

#### `get_status()`
Get Novatel status.
```python
with NovatelGPS(port='COM7') as gps:
    status = gps.get_status()
    print(status)
```

#### `help(method=None)`
Display help.
```python
gps.help()
```

---

## 10. Configuration Classes

### SerialConfig
Serial port settings.

```python
from sciglob.config import SerialConfig

config = SerialConfig(
    port='/dev/ttyUSB0',   # Serial port
    baudrate=9600,         # Communication speed
    bytesize=8,            # Data bits
    parity='N',            # 'N', 'E', 'O', 'M', 'S'
    stopbits=1,            # Stop bits
    timeout=0,             # Read timeout
    write_timeout=20.0,    # Write timeout
)

# Convert to dictionary
print(config.to_dict())

# Get help
print(SerialConfig.help())
```

### HeadSensorConfig
Head sensor configuration.

```python
from sciglob.config import HeadSensorConfig, SerialConfig

config = HeadSensorConfig(
    serial=SerialConfig(port='COM3', baudrate=9600),
    sensor_type=None,                    # Auto-detect
    tracker_type='LuftBlickTR1',
    degrees_per_step=0.01,
    motion_limits=[0, 90, 0, 360],
    home_position=[0.0, 180.0],
    fw1_filters=['OPEN', 'U340', 'BP300', 'LPNIR', 'ND1', 'ND2', 'ND3', 'ND4', 'OPAQUE'],
    fw2_filters=['OPEN', 'DIFF', 'U340+DIFF', 'BP300+DIFF', 'LPNIR+DIFF', 'ND1', 'ND2', 'ND3', 'OPAQUE'],
    shadowband_resolution=0.36,
    shadowband_ratio=0.5,
)

# Get help
print(HeadSensorConfig.help())
```

### TemperatureControllerConfig
Temperature controller configuration.

```python
from sciglob.config import TemperatureControllerConfig, SerialConfig

config = TemperatureControllerConfig(
    serial=SerialConfig(port='COM4'),
    controller_type='TETech1',    # or 'TETech2'
    set_temperature=25.0,
    proportional_bandwidth=10.0,
    integral_gain=0.5,
)

# Get help
print(TemperatureControllerConfig.help())
```

### HumiditySensorConfig
Humidity sensor configuration.

```python
from sciglob.config import HumiditySensorConfig, SerialConfig

config = HumiditySensorConfig(
    serial=SerialConfig(port='COM5', baudrate=9600),
)

# Get help
print(HumiditySensorConfig.help())
```

### GPSConfig
GPS configuration.

```python
from sciglob.config import GPSConfig, SerialConfig

config = GPSConfig(
    serial=SerialConfig(port='COM6', baudrate=9600),
    system_type='GlobalSat',    # or 'Novatel'
)

# Get help
print(GPSConfig.help())
```

### HardwareConfig
Complete system configuration.

```python
from sciglob.config import HardwareConfig

# Create default config
config = HardwareConfig()

# Modify settings
config.head_sensor.serial.port = 'COM3'
config.head_sensor.tracker_type = 'LuftBlickTR1'
config.temperature_controller_1.serial.port = 'COM4'
config.gps.serial.port = 'COM6'

# Save to YAML
config.to_yaml('my_config.yaml')

# Load from YAML
config = HardwareConfig.from_yaml('my_config.yaml')

# Get help
print(HardwareConfig.help())
```

### Example YAML Configuration
```yaml
head_sensor:
  serial:
    port: COM3
    baudrate: 9600
  tracker_type: LuftBlickTR1
  degrees_per_step: 0.01
  motion_limits: [0, 90, 0, 360]
  home_position: [0.0, 180.0]
  fw1_filters: [OPEN, U340, BP300, LPNIR, ND1, ND2, ND3, ND4, OPAQUE]

temperature_controller_1:
  serial:
    port: COM4
  controller_type: TETech1

temperature_controller_2:
  serial:
    port: COM5
  controller_type: TETech2

humidity_sensor:
  serial:
    port: COM6

gps:
  serial:
    port: COM7
  system_type: GlobalSat
```

---

## 11. Utility Functions

### `degrees_to_steps(degrees, degrees_per_step, home_position)`
Convert degrees to motor steps.

```python
from sciglob import degrees_to_steps

# Convert 90° to steps (home at 180°)
steps = degrees_to_steps(90.0, degrees_per_step=0.01, home_position=180.0)
print(f"Steps: {steps}")  # 9000
```

### `steps_to_degrees(steps, degrees_per_step, home_position)`
Convert motor steps to degrees.

```python
from sciglob import steps_to_degrees

# Convert 9000 steps to degrees
degrees = steps_to_degrees(9000, degrees_per_step=0.01, home_position=180.0)
print(f"Degrees: {degrees}")  # 90.0
```

### `normalize_azimuth(azimuth)`
Normalize azimuth to 0-360 range.

```python
from sciglob import normalize_azimuth

print(normalize_azimuth(-90.0))   # 270.0
print(normalize_azimuth(450.0))   # 90.0
print(normalize_azimuth(360.0))   # 0.0
```

---

## 12. Exceptions

### Exception Hierarchy
```
SciGlobError (base)
├── ConnectionError       # Connection failures
├── CommunicationError    # Communication failures
├── TimeoutError          # Operation timeouts
├── ConfigurationError    # Configuration errors
├── RecoveryError         # Recovery exhausted
└── DeviceError           # General device errors
    ├── TrackerError      # Tracker errors
    │   ├── MotorError        # Motor failures
    │   │   ├── PositionError     # Out of range
    │   │   ├── HomingError       # Homing failed
    │   │   └── MotorAlarmError   # Motor alarm
    ├── FilterWheelError  # Filter wheel errors
    └── SensorError       # Sensor errors
```

### Import
```python
from sciglob import (
    SciGlobError,
    ConnectionError,
    CommunicationError,
    TimeoutError,
    ConfigurationError,
    TrackerError,
    MotorError,
    PositionError,
    HomingError,
    MotorAlarmError,
    FilterWheelError,
    SensorError,
    RecoveryError,
)
```

### PositionError
```python
from sciglob import PositionError

try:
    # ... code that raises PositionError
    raise PositionError(100, 0, 90, axis="Zenith")
except PositionError as e:
    print(f"Position {e.position} out of range [{e.min_pos}, {e.max_pos}]")
    print(f"Axis: {e.axis}")
```

### MotorAlarmError
```python
from sciglob import MotorAlarmError

try:
    # ... code that raises MotorAlarmError
    raise MotorAlarmError("Motor overheat", alarm_code=26, axis="zenith")
except MotorAlarmError as e:
    print(f"Alarm code {e.alarm_code} on {e.axis}")
```

### Example Error Handling
```python
from sciglob import (
    HeadSensor,
    ConnectionError,
    TrackerError,
    PositionError,
    FilterWheelError,
    MotorAlarmError,
)

try:
    with HeadSensor(port='/dev/ttyUSB0') as hs:
        hs.tracker.move_to(zenith=45.0, azimuth=180.0)
        hs.filter_wheel_1.set_filter("U340")
        
except ConnectionError as e:
    print(f"Failed to connect: {e}")
except PositionError as e:
    print(f"Position {e.position} out of range [{e.min_pos}, {e.max_pos}]")
except MotorAlarmError as e:
    print(f"Motor alarm on {e.axis}: code {e.alarm_code}")
except FilterWheelError as e:
    print(f"Filter wheel error: {e}")
except TrackerError as e:
    print(f"Tracker error: {e}")
```

---

## Complete Example

```python
"""Complete example using all SciGlob components."""

from sciglob import (
    HeadSensor,
    TemperatureController,
    HumiditySensor,
    GlobalSatGPS,
    ConnectionError,
    PositionError,
)
from sciglob.config import (
    HardwareConfig,
    HeadSensorConfig,
    SerialConfig,
)

# Load configuration
config = HardwareConfig()
config.head_sensor.serial.port = '/dev/ttyUSB0'
config.head_sensor.tracker_type = 'LuftBlickTR1'
config.head_sensor.fw1_filters = [
    'OPEN', 'U340', 'BP300', 'LPNIR',
    'ND1', 'ND2', 'ND3', 'ND4', 'OPAQUE'
]

try:
    # Connect to head sensor
    with HeadSensor(config=config.head_sensor) as hs:
        print(f"Connected to: {hs.device_id}")
        
        # Move tracker
        hs.tracker.move_to(zenith=45.0, azimuth=180.0)
        zen, azi = hs.tracker.get_position()
        print(f"Position: zenith={zen}°, azimuth={azi}°")
        
        # Change filter
        hs.filter_wheel_1.set_filter("U340")
        print(f"Filter: {hs.filter_wheel_1.current_filter}")
        
        # Read sensors (SciGlobHSN2 only)
        if hs.sensor_type == "SciGlobHSN2":
            sensors = hs.get_all_sensors()
            print(f"Temperature: {sensors['temperature']}°C")
            print(f"Humidity: {sensors['humidity']}%")
            print(f"Pressure: {sensors['pressure']} mbar")
        
        # Park tracker at end
        hs.tracker.park()

except ConnectionError as e:
    print(f"Connection failed: {e}")
except PositionError as e:
    print(f"Position error: {e}")
```

---

*Document Version: 1.0*  
*SciGlob Library Version: 0.1.4*

