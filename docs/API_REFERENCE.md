# SciGlob Library - API Reference Manual

## Version 0.1.0

This document provides a complete API reference for developers using the SciGlob Library.

---

## Table of Contents

1. [Installation](#1-installation)
2. [Quick Start](#2-quick-start)
3. [HeadSensor](#3-headsensor)
4. [Tracker](#4-tracker)
5. [FilterWheel](#5-filterwheel)
6. [Shadowband](#6-shadowband)
7. [TemperatureController](#7-temperaturecontroller)
8. [HumiditySensor](#8-humiditysensor)
9. [GPS/Positioning](#9-gpspositioning)
10. [Exceptions](#10-exceptions)
11. [Utility Functions](#11-utility-functions)
12. [Configuration](#12-configuration)
13. [Logging](#13-logging)

---

## 1. Installation

### From Source

```bash
git clone https://github.com/ashutoshjoshi1/SciGlob-Library.git
cd SciGlob-Library
pip install -e .
```

### With Development Dependencies

```bash
pip install -e ".[dev]"
```

### Requirements

- Python 3.9+
- pyserial >= 3.5
- pyyaml >= 6.0

---

## 2. Quick Start

```python
from sciglob import HeadSensor

# Connect to head sensor (main hub for all devices)
with HeadSensor(port="/dev/ttyUSB0") as hs:
    # Access tracker (motor control)
    hs.tracker.move_to(zenith=45.0, azimuth=180.0)
    
    # Access filter wheel
    hs.filter_wheel_1.set_filter("OPEN")
    
    # Read sensors
    print(hs.get_all_sensors())
```

### Import Shortcuts

```python
# Import main classes
from sciglob import (
    HeadSensor,
    Tracker,
    FilterWheel,
    Shadowband,
    TemperatureController,
    HumiditySensor,
    GlobalSatGPS,
    NovatelGPS,
)

# Import exceptions
from sciglob import (
    SciGlobError,
    ConnectionError,
    TrackerError,
    PositionError,
    FilterWheelError,
)

# Import utilities
from sciglob import degrees_to_steps, steps_to_degrees
```

---

## 3. HeadSensor

The `HeadSensor` class is the main communication hub that provides access to:
- Tracker (motor control)
- Filter Wheels (FW1, FW2)
- Shadowband
- Internal sensors (temperature, humidity, pressure)

### Import

```python
from sciglob import HeadSensor
```

### Constructor

```python
HeadSensor(
    port: str = None,
    baudrate: int = 9600,
    timeout: float = 1.0,
    name: str = "HeadSensor",
    sensor_type: str = None,
    fw1_filters: List[str] = None,
    fw2_filters: List[str] = None,
    tracker_type: str = "Directed Perceptions",
    degrees_per_step: float = 0.01,
    motion_limits: List[float] = None,
    home_position: List[float] = None,
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `port` | `str` | `None` | Serial port path (e.g., `/dev/ttyUSB0`, `COM3`) |
| `baudrate` | `int` | `9600` | Communication speed |
| `timeout` | `float` | `1.0` | Command timeout in seconds |
| `name` | `str` | `"HeadSensor"` | Device name for logging |
| `sensor_type` | `str` | `None` | Expected sensor type (`SciGlobHSN1` or `SciGlobHSN2`) |
| `fw1_filters` | `List[str]` | `["OPEN"]*9` | Filter names for Filter Wheel 1 (9 positions) |
| `fw2_filters` | `List[str]` | `["OPEN"]*9` | Filter names for Filter Wheel 2 (9 positions) |
| `tracker_type` | `str` | `"Directed Perceptions"` | Tracker type (`Directed Perceptions` or `LuftBlickTR1`) |
| `degrees_per_step` | `float` | `0.01` | Tracker resolution (100 steps per degree) |
| `motion_limits` | `List[float]` | `[0, 90, 0, 360]` | `[zen_min, zen_max, azi_min, azi_max]` |
| `home_position` | `List[float]` | `[0.0, 180.0]` | `[zenith_home, azimuth_home]` in degrees |

#### Example

```python
hs = HeadSensor(
    port="/dev/ttyUSB0",
    tracker_type="LuftBlickTR1",
    degrees_per_step=0.01,
    motion_limits=[0, 90, 0, 360],
    home_position=[0.0, 180.0],
    fw1_filters=["OPEN", "U340", "BP300", "LPNIR", "ND1", "ND2", "ND3", "ND4", "OPAQUE"],
)
```

---

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `device_id` | `str` | Device identification string |
| `sensor_type` | `str` | Detected sensor type (`SciGlobHSN1` or `SciGlobHSN2`) |
| `tracker_type` | `str` | Tracker type |
| `degrees_per_step` | `float` | Tracker resolution |
| `motion_limits` | `List[float]` | Motion limits `[zen_min, zen_max, azi_min, azi_max]` |
| `home_position` | `List[float]` | Home position `[zenith, azimuth]` |
| `fw1_filters` | `List[str]` | Filter Wheel 1 filter names |
| `fw2_filters` | `List[str]` | Filter Wheel 2 filter names |
| `is_connected` | `bool` | Connection status |
| `tracker` | `Tracker` | Tracker interface (lazy-loaded) |
| `filter_wheel_1` | `FilterWheel` | Filter Wheel 1 interface |
| `filter_wheel_2` | `FilterWheel` | Filter Wheel 2 interface |
| `shadowband` | `Shadowband` | Shadowband interface |

---

### Methods

#### `connect()`

Establish connection to the Head Sensor.

```python
def connect(self) -> None
```

**Raises:**
- `ConnectionError`: If connection fails
- `DeviceError`: If device identification fails

**Example:**
```python
hs = HeadSensor(port="/dev/ttyUSB0")
hs.connect()
```

---

#### `disconnect()`

Close connection to the Head Sensor.

```python
def disconnect(self) -> None
```

**Example:**
```python
hs.disconnect()
```

---

#### `get_id()`

Get device identification string.

```python
def get_id(self) -> str
```

**Returns:** Device ID string

**Example:**
```python
device_id = hs.get_id()
print(device_id)  # "SciGlobHSN2"
```

---

#### `get_temperature()`

Read head sensor temperature (SciGlobHSN2 only).

```python
def get_temperature(self) -> float
```

**Returns:** Temperature in °C

**Raises:** `SensorError` if sensor type doesn't support temperature

**Example:**
```python
temp = hs.get_temperature()
print(f"Temperature: {temp}°C")
```

---

#### `get_humidity()`

Read head sensor humidity (SciGlobHSN2 only).

```python
def get_humidity(self) -> float
```

**Returns:** Relative humidity in %

**Raises:** `SensorError` if sensor type doesn't support humidity

**Example:**
```python
humidity = hs.get_humidity()
print(f"Humidity: {humidity}%")
```

---

#### `get_pressure()`

Read head sensor pressure (SciGlobHSN2 only).

```python
def get_pressure(self) -> float
```

**Returns:** Pressure in mbar

**Raises:** `SensorError` if sensor type doesn't support pressure

**Example:**
```python
pressure = hs.get_pressure()
print(f"Pressure: {pressure} mbar")
```

---

#### `get_all_sensors()`

Read all available sensor values.

```python
def get_all_sensors(self) -> Dict[str, float]
```

**Returns:** Dictionary with keys: `temperature`, `humidity`, `pressure`

**Example:**
```python
sensors = hs.get_all_sensors()
# {'temperature': 25.0, 'humidity': 50.0, 'pressure': 1013.25}
```

---

#### `power_reset(device)`

Power reset a connected device.

```python
def power_reset(self, device: str) -> bool
```

**Parameters:**
- `device`: Device identifier (`TR`/`tracker`, `S1`, `S2`)

**Returns:** `True` if successful

**Example:**
```python
hs.power_reset("tracker")
```

---

#### `send_command(command, timeout)`

Send a raw command to the Head Sensor.

```python
def send_command(self, command: str, timeout: float = None) -> str
```

**Parameters:**
- `command`: Command string (without end character)
- `timeout`: Response timeout (optional)

**Returns:** Response string

**Example:**
```python
response = hs.send_command("?")
print(response)  # "SciGlobHSN2"
```

---

#### `get_status()`

Get comprehensive status of the Head Sensor.

```python
def get_status(self) -> Dict[str, Any]
```

**Returns:** Dictionary with status information

**Example:**
```python
status = hs.get_status()
# {
#     'connected': True,
#     'port': '/dev/ttyUSB0',
#     'device_id': 'SciGlobHSN2',
#     'sensor_type': 'SciGlobHSN2',
#     'tracker_type': 'LuftBlickTR1',
#     'sensors': {'temperature': 25.0, 'humidity': 50.0, 'pressure': 1013.25}
# }
```

---

### Context Manager

HeadSensor supports the `with` statement for automatic connection management:

```python
with HeadSensor(port="/dev/ttyUSB0") as hs:
    # Connected here
    hs.tracker.move_to(zenith=45.0, azimuth=180.0)
# Automatically disconnected
```

---

## 4. Tracker

The `Tracker` class controls azimuth (pan) and zenith (tilt) motors through the Head Sensor.

### Access

```python
# Access via HeadSensor
tracker = hs.tracker
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `tracker_type` | `str` | Tracker type |
| `degrees_per_step` | `float` | Resolution (degrees per step) |
| `is_luftblick` | `bool` | True if LuftBlickTR1 |
| `zenith_home` | `float` | Zenith home position (degrees) |
| `azimuth_home` | `float` | Azimuth home position (degrees) |
| `zenith_limits` | `Tuple[float, float]` | (min, max) degrees |
| `azimuth_limits` | `Tuple[float, float]` | (min, max) degrees |

---

### Methods

#### `get_position()`

Get current position in degrees.

```python
def get_position(self) -> Tuple[float, float]
```

**Returns:** `(zenith_degrees, azimuth_degrees)`

**Example:**
```python
zenith, azimuth = tracker.get_position()
print(f"Position: zenith={zenith}°, azimuth={azimuth}°")
```

---

#### `get_position_steps()`

Get current position in steps.

```python
def get_position_steps(self) -> Tuple[int, int]
```

**Returns:** `(azimuth_steps, zenith_steps)`

**Example:**
```python
azi_steps, zen_steps = tracker.get_position_steps()
print(f"Steps: azimuth={azi_steps}, zenith={zen_steps}")
```

---

#### `move_to(zenith, azimuth, wait)`

Move to position specified in degrees.

```python
def move_to(
    self,
    zenith: float = None,
    azimuth: float = None,
    wait: bool = True,
) -> None
```

**Parameters:**
- `zenith`: Target zenith angle in degrees (optional)
- `azimuth`: Target azimuth angle in degrees (optional)
- `wait`: If True, wait for movement to complete

**Raises:**
- `PositionError`: If position is out of limits
- `TrackerError`: If movement fails

**Example:**
```python
# Move both axes
tracker.move_to(zenith=45.0, azimuth=180.0)

# Move zenith only
tracker.move_to(zenith=30.0)

# Move azimuth only
tracker.move_to(azimuth=90.0)

# Non-blocking move
tracker.move_to(zenith=45.0, azimuth=180.0, wait=False)
```

---

#### `move_to_steps(zenith_steps, azimuth_steps, wait)`

Move to position specified in steps.

```python
def move_to_steps(
    self,
    zenith_steps: int = None,
    azimuth_steps: int = None,
    wait: bool = True,
) -> None
```

**Parameters:**
- `zenith_steps`: Target zenith position in steps
- `azimuth_steps`: Target azimuth position in steps
- `wait`: If True, wait for movement to complete

**Example:**
```python
tracker.move_to_steps(zenith_steps=4500, azimuth_steps=-1200)
```

---

#### `move_relative(delta_zenith, delta_azimuth, wait)`

Move relative to current position.

```python
def move_relative(
    self,
    delta_zenith: float = 0.0,
    delta_azimuth: float = 0.0,
    wait: bool = True,
) -> None
```

**Parameters:**
- `delta_zenith`: Degrees to move in zenith
- `delta_azimuth`: Degrees to move in azimuth
- `wait`: If True, wait for movement to complete

**Example:**
```python
tracker.move_relative(delta_zenith=10.0, delta_azimuth=-20.0)
```

---

#### `pan(azimuth, wait)`

Move azimuth only.

```python
def pan(self, azimuth: float, wait: bool = True) -> None
```

**Example:**
```python
tracker.pan(azimuth=90.0)
```

---

#### `tilt(zenith, wait)`

Move zenith only.

```python
def tilt(self, zenith: float, wait: bool = True) -> None
```

**Example:**
```python
tracker.tilt(zenith=45.0)
```

---

#### `home(wait)`

Move to home position.

```python
def home(self, wait: bool = True) -> None
```

**Example:**
```python
tracker.home()
```

---

#### `park(zenith, azimuth, wait)`

Move to parking position.

```python
def park(
    self,
    zenith: float = 90.0,
    azimuth: float = 0.0,
    wait: bool = True,
) -> None
```

**Example:**
```python
tracker.park()  # Default: zenith=90°, azimuth=0°
tracker.park(zenith=85.0, azimuth=180.0)  # Custom position
```

---

#### `reset()`

Perform soft reset of the tracker.

```python
def reset(self) -> bool
```

**Returns:** True if successful

**Example:**
```python
tracker.reset()
```

---

#### `power_reset()`

Perform power cycle of the tracker.

```python
def power_reset(self) -> bool
```

**Returns:** True if successful

**Example:**
```python
tracker.power_reset()
```

---

#### `get_motor_temperatures()` *(LuftBlickTR1 only)*

Get motor temperatures.

```python
def get_motor_temperatures(self) -> Dict[str, float]
```

**Returns:** Dictionary with keys:
- `azimuth_driver_temp`
- `azimuth_motor_temp`
- `zenith_driver_temp`
- `zenith_motor_temp`

**Raises:** `TrackerError` if not LuftBlickTR1

**Example:**
```python
if tracker.is_luftblick:
    temps = tracker.get_motor_temperatures()
    print(f"Azimuth motor: {temps['azimuth_motor_temp']}°C")
```

---

#### `get_motor_alarms()` *(LuftBlickTR1 only)*

Get motor alarm status.

```python
def get_motor_alarms(self) -> Dict[str, Tuple[int, str]]
```

**Returns:** Dictionary with keys `zenith` and `azimuth`, values are `(alarm_code, message)`

**Example:**
```python
alarms = tracker.get_motor_alarms()
# {'zenith': (0, 'No alarm'), 'azimuth': (0, 'No alarm')}
```

---

#### `check_alarms()` *(LuftBlickTR1 only)*

Check for motor alarms and raise exception if any found.

```python
def check_alarms(self) -> None
```

**Raises:** `MotorAlarmError` if any motor has an alarm

**Example:**
```python
try:
    tracker.check_alarms()
except MotorAlarmError as e:
    print(f"Alarm on {e.axis}: code {e.alarm_code}")
```

---

#### `get_magnetic_position_steps()` *(LuftBlickTR1 only)*

Get absolute encoder position.

```python
def get_magnetic_position_steps(self) -> Tuple[int, int]
```

**Returns:** `(azimuth_steps, zenith_steps)`

---

#### `get_status()`

Get comprehensive tracker status.

```python
def get_status(self) -> Dict[str, Any]
```

**Example:**
```python
status = tracker.get_status()
```

---

## 5. FilterWheel

The `FilterWheel` class controls filter wheel selection (9 positions each).

### Access

```python
# Access via HeadSensor
fw1 = hs.filter_wheel_1  # Filter Wheel 1
fw2 = hs.filter_wheel_2  # Filter Wheel 2
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `wheel_id` | `int` | Wheel identifier (1 or 2) |
| `device_id` | `str` | Device ID string (`F1` or `F2`) |
| `position` | `int` | Current position (1-9, or 0 if unknown) |
| `current_filter` | `str` | Name of current filter |
| `filter_names` | `List[str]` | List of filter names |
| `num_positions` | `int` | Number of positions (always 9) |

---

### Methods

#### `set_position(position)`

Set the filter wheel to a specific position.

```python
def set_position(self, position: int) -> None
```

**Parameters:**
- `position`: Target position (1-9)

**Raises:**
- `ValueError`: If position is invalid
- `FilterWheelError`: If movement fails

**Example:**
```python
fw1.set_position(5)
```

---

#### `set_filter(filter_name)`

Set the filter wheel by filter name.

```python
def set_filter(self, filter_name: str) -> None
```

**Parameters:**
- `filter_name`: Filter name (case-insensitive)

**Raises:** `FilterWheelError` if filter not found

**Example:**
```python
fw1.set_filter("U340")
fw1.set_filter("open")  # Case-insensitive
```

---

#### `reset()`

Reset the filter wheel to home position (position 1).

```python
def reset(self) -> None
```

**Example:**
```python
fw1.reset()
```

---

#### `get_filter_map()`

Get mapping of positions to filter names.

```python
def get_filter_map(self) -> Dict[int, str]
```

**Returns:** Dictionary `{position: filter_name}`

**Example:**
```python
filter_map = fw1.get_filter_map()
# {1: 'OPEN', 2: 'U340', 3: 'BP300', ...}
```

---

#### `get_position_for_filter(filter_name)`

Get the position for a specific filter name.

```python
def get_position_for_filter(self, filter_name: str) -> Optional[int]
```

**Returns:** Position (1-9) or None if not found

**Example:**
```python
pos = fw1.get_position_for_filter("U340")  # Returns 2
```

---

#### `get_available_filters()`

Get list of all configured filter names.

```python
def get_available_filters(self) -> List[str]
```

**Example:**
```python
filters = fw1.get_available_filters()
# ['OPEN', 'U340', 'BP300', 'LPNIR', 'ND1', 'ND2', 'ND3', 'ND4', 'OPAQUE']
```

---

#### `get_status()`

Get filter wheel status.

```python
def get_status(self) -> Dict[str, Any]
```

**Example:**
```python
status = fw1.get_status()
# {'wheel_id': 1, 'position': 2, 'current_filter': 'U340', 'filter_map': {...}}
```

---

## 6. Shadowband

The `Shadowband` class controls the shadowband arm position.

### Access

```python
# Access via HeadSensor
sb = hs.shadowband
```

### Constructor Parameters (set via HeadSensor)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resolution` | `float` | `0.36` | Degrees per step |
| `ratio` | `float` | `0.5` | Shadowband offset/radius ratio |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `position` | `int` | Current position in steps |
| `angle` | `float` | Current angle in degrees |
| `resolution` | `float` | Degrees per step |
| `ratio` | `float` | Offset/radius ratio |

---

### Methods

#### `move_to_position(position)`

Move shadowband to step position.

```python
def move_to_position(self, position: int) -> None
```

**Example:**
```python
sb.move_to_position(500)
sb.move_to_position(-300)
```

---

#### `move_to_angle(angle)`

Move shadowband to specified angle.

```python
def move_to_angle(self, angle: float) -> None
```

**Example:**
```python
sb.move_to_angle(45.0)
```

---

#### `move_relative(delta_steps)`

Move shadowband relative to current position.

```python
def move_relative(self, delta_steps: int) -> None
```

**Example:**
```python
sb.move_relative(100)   # Move forward 100 steps
sb.move_relative(-50)   # Move back 50 steps
```

---

#### `reset()`

Reset the shadowband to home position.

```python
def reset(self) -> None
```

---

#### `get_status()`

Get shadowband status.

```python
def get_status(self) -> Dict[str, Any]
```

---

## 7. TemperatureController

The `TemperatureController` class controls TETech temperature controllers.

### Import

```python
from sciglob import TemperatureController
```

### Constructor

```python
TemperatureController(
    port: str = None,
    baudrate: int = 9600,
    timeout: float = 1.0,
    name: str = "TempController",
    controller_type: str = "TETech1",
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `port` | `str` | `None` | Serial port path |
| `baudrate` | `int` | `9600` | Communication speed |
| `timeout` | `float` | `1.0` | Command timeout |
| `controller_type` | `str` | `"TETech1"` | `TETech1` (16-bit) or `TETech2` (32-bit) |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `controller_type` | `str` | Controller type |
| `nbits` | `int` | Bit width (16 or 32) |
| `is_connected` | `bool` | Connection status |

---

### Methods

#### `connect()` / `disconnect()`

Connection management.

```python
tc = TemperatureController(port="/dev/ttyUSB1", controller_type="TETech1")
tc.connect()
# ... use controller ...
tc.disconnect()
```

---

#### `set_temperature(temperature)`

Set target temperature.

```python
def set_temperature(self, temperature: float) -> bool
```

**Returns:** True if successful

**Example:**
```python
tc.set_temperature(25.0)
```

---

#### `get_temperature()`

Get control sensor temperature.

```python
def get_temperature(self) -> float
```

**Returns:** Temperature in °C

---

#### `get_secondary_temperature()`

Get secondary sensor temperature.

```python
def get_secondary_temperature(self) -> float
```

---

#### `get_setpoint()`

Get current temperature setpoint.

```python
def get_setpoint(self) -> float
```

---

#### `set_bandwidth(bandwidth)`

Set proportional bandwidth (PID parameter).

```python
def set_bandwidth(self, bandwidth: float) -> bool
```

---

#### `set_integral_gain(gain)`

Set integral gain (PID parameter).

```python
def set_integral_gain(self, gain: float) -> bool
```

---

#### `enable_output()` / `disable_output()`

Control temperature output.

```python
tc.enable_output()
tc.disable_output()
```

---

#### `get_status()`

Get controller status.

---

### Context Manager

```python
with TemperatureController(port="/dev/ttyUSB1") as tc:
    tc.set_temperature(25.0)
    tc.enable_output()
```

---

## 8. HumiditySensor

The `HumiditySensor` class interfaces with HDC2080EVM humidity sensors.

### Import

```python
from sciglob import HumiditySensor
```

### Constructor

```python
HumiditySensor(
    port: str = None,
    baudrate: int = 9600,
    timeout: float = 1.0,
    name: str = "HumiditySensor",
)
```

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `is_connected` | `bool` | Connection status |
| `is_initialized` | `bool` | Initialization status |

---

### Methods

#### `connect()` / `disconnect()`

Connection management.

---

#### `initialize()`

Initialize the sensor (stop any streaming).

```python
def initialize(self) -> bool
```

---

#### `get_temperature()`

Get temperature reading.

```python
def get_temperature(self) -> float
```

**Returns:** Temperature in °C

---

#### `get_humidity()`

Get humidity reading.

```python
def get_humidity(self) -> float
```

**Returns:** Relative humidity in %

---

#### `get_readings()`

Get both temperature and humidity readings.

```python
def get_readings(self) -> Dict[str, float]
```

**Returns:** `{'temperature': float, 'humidity': float}`

---

### Context Manager

```python
with HumiditySensor(port="/dev/ttyUSB2") as hs:
    readings = hs.get_readings()
    print(f"Temp: {readings['temperature']}°C, Humidity: {readings['humidity']}%")
```

---

## 9. GPS/Positioning

### GlobalSatGPS

Simple GPS receiver using NMEA protocol.

### Import

```python
from sciglob import GlobalSatGPS
```

### Constructor

```python
GlobalSatGPS(
    port: str = None,
    baudrate: int = 9600,
    timeout: float = 2.0,
    name: str = "GlobalSatGPS",
)
```

### Methods

#### `connect()` / `disconnect()`

Connection management.

---

#### `configure()`

Configure the GPS (disable automatic messages).

```python
def configure(self) -> bool
```

---

#### `get_position()`

Get current GPS position.

```python
def get_position(self) -> Dict[str, Any]
```

**Returns:**
```python
{
    'latitude': float,      # Decimal degrees (+ = North)
    'longitude': float,     # Decimal degrees (+ = East)
    'altitude': float,      # Meters above sea level
    'quality': int,         # Fix quality (0 = no fix, 1 = GPS, 2 = DGPS)
    'satellites': int,      # Number of satellites
}
```

---

### Example

```python
with GlobalSatGPS(port="/dev/ttyUSB3") as gps:
    pos = gps.get_position()
    if pos['quality'] > 0:
        print(f"Lat: {pos['latitude']}, Lon: {pos['longitude']}")
    else:
        print("No GPS fix")
```

---

### NovatelGPS

GPS + Gyroscope for position and orientation.

### Import

```python
from sciglob import NovatelGPS
```

### Constructor

```python
NovatelGPS(
    port: str = None,
    baudrate: int = 9600,
    timeout: float = 2.0,
    name: str = "NovatelGPS",
)
```

### Methods

#### `get_position()`

Get current GPS position.

```python
def get_position(self) -> Dict[str, Any]
```

**Returns:**
```python
{
    'latitude': float,
    'longitude': float,
    'altitude': float,
    'status': str,  # 'INS_SOLUTION_GOOD', 'INS_ALIGNMENT_COMPLETE', etc.
}
```

---

#### `get_orientation()`

Get current orientation from gyroscope.

```python
def get_orientation(self) -> Dict[str, float]
```

**Returns:**
```python
{
    'roll': float,   # East-West tilt (degrees)
    'pitch': float,  # North-South tilt (degrees)
    'yaw': float,    # Azimuth (degrees)
}
```

---

#### `start_logging(interval)` / `stop_logging()`

Control continuous logging.

```python
gps.start_logging(interval=1.0)  # Log every 1 second
gps.stop_logging()
```

---

### Example

```python
with NovatelGPS(port="/dev/ttyUSB4") as gps:
    pos = gps.get_position()
    orient = gps.get_orientation()
    print(f"Position: {pos['latitude']}, {pos['longitude']}")
    print(f"Heading (yaw): {orient['yaw']}°")
```

---

## 10. Exceptions

### Exception Hierarchy

```
SciGlobError (base)
├── ConnectionError      # Connection failures
├── CommunicationError   # Communication failures
├── TimeoutError         # Operation timeouts
├── ConfigurationError   # Configuration errors
├── RecoveryError        # Recovery attempts exhausted
├── DeviceError          # General device errors
│   ├── TrackerError     # Tracker-specific errors
│   │   ├── MotorError       # Motor operation failures
│   │   │   ├── PositionError    # Position out of range
│   │   │   ├── HomingError      # Homing failures
│   │   │   └── MotorAlarmError  # Motor alarm conditions
│   ├── FilterWheelError # Filter wheel errors
│   ├── SensorError      # Sensor reading errors
│   ├── SpectrometerError
│   └── CameraError
```

### Import

```python
from sciglob import (
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
```

### PositionError

Raised when a position is out of valid range.

**Attributes:**
- `position`: The invalid position value
- `min_pos`: Minimum allowed position
- `max_pos`: Maximum allowed position
- `axis`: Axis name ("Zenith", "Azimuth", etc.)

```python
try:
    tracker.move_to(zenith=100.0)  # Out of range
except PositionError as e:
    print(f"{e.axis} {e.position} is out of range [{e.min_pos}, {e.max_pos}]")
```

### MotorAlarmError

Raised when motor reports an alarm condition.

**Attributes:**
- `alarm_code`: Alarm code number
- `axis`: Motor axis ("zenith" or "azimuth")

```python
try:
    tracker.check_alarms()
except MotorAlarmError as e:
    print(f"Alarm on {e.axis}: code {e.alarm_code}")
```

### Example Error Handling

```python
from sciglob import (
    HeadSensor,
    ConnectionError,
    TrackerError,
    PositionError,
    FilterWheelError,
)

try:
    with HeadSensor(port="/dev/ttyUSB0") as hs:
        hs.tracker.move_to(zenith=45.0, azimuth=180.0)
        hs.filter_wheel_1.set_filter("U340")
        
except ConnectionError as e:
    print(f"Connection failed: {e}")
except PositionError as e:
    print(f"Position error: {e}")
except FilterWheelError as e:
    print(f"Filter wheel error: {e}")
except TrackerError as e:
    print(f"Tracker error: {e}")
```

---

## 11. Utility Functions

### Import

```python
from sciglob import degrees_to_steps, steps_to_degrees, normalize_azimuth
from sciglob.core.utils import (
    validate_angle,
    calculate_angular_distance,
    shortest_rotation_path,
    dec2hex,
    hex2dec,
    get_checksum,
)
```

### degrees_to_steps

Convert angle in degrees to tracker step position.

```python
def degrees_to_steps(
    degrees: float,
    degrees_per_step: float = 0.01,
    home_position: float = 0.0,
) -> int
```

**Example:**
```python
steps = degrees_to_steps(90.0, degrees_per_step=0.01, home_position=180.0)
# Returns 9000
```

---

### steps_to_degrees

Convert tracker step position to angle in degrees.

```python
def steps_to_degrees(
    steps: int,
    degrees_per_step: float = 0.01,
    home_position: float = 0.0,
) -> float
```

**Example:**
```python
degrees = steps_to_degrees(9000, degrees_per_step=0.01, home_position=180.0)
# Returns 90.0
```

---

### normalize_azimuth

Normalize azimuth angle to 0-360 range.

```python
def normalize_azimuth(azimuth: float) -> float
```

**Example:**
```python
normalize_azimuth(-90.0)   # Returns 270.0
normalize_azimuth(450.0)   # Returns 90.0
```

---

### shortest_rotation_path

Calculate shortest rotation to reach target angle.

```python
def shortest_rotation_path(
    current: float,
    target: float,
    max_angle: float = 360.0,
) -> float
```

**Returns:** Rotation delta (positive=clockwise, negative=counter-clockwise)

**Example:**
```python
shortest_rotation_path(350.0, 10.0)  # Returns 20.0 (not -340.0)
shortest_rotation_path(10.0, 350.0)  # Returns -20.0
```

---

### calculate_angular_distance

Calculate angular distance between two directions.

```python
def calculate_angular_distance(
    zen1: float, azi1: float,
    zen2: float, azi2: float,
) -> float
```

**Returns:** Angular distance in degrees

---

## 12. Configuration

### YAML Configuration File

```yaml
# config.yaml
sensor_head:
  port: "/dev/ttyUSB0"
  baudrate: 9600
  timeout: 1.0

motors:
  azimuth:
    port: "/dev/ttyUSB1"
    baudrate: 115200
    min_position: 0.0
    max_position: 360.0
    
  zenith:
    port: "/dev/ttyUSB2"
    baudrate: 115200
    min_position: 0.0
    max_position: 90.0
```

### Loading Configuration

```python
from sciglob.config import Settings, load_config

# Load from file
settings = Settings.from_yaml("config.yaml")

# Or load with defaults
settings = load_config("config.yaml")  # Returns defaults if file not found
```

---

## 13. Logging

### Enable Logging

```python
import logging

# Basic setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Enable debug for all sciglob components
logging.getLogger("sciglob").setLevel(logging.DEBUG)
```

### Component-Specific Logging

```python
# Debug specific components
logging.getLogger("sciglob.Tracker").setLevel(logging.DEBUG)
logging.getLogger("sciglob.serial").setLevel(logging.DEBUG)
logging.getLogger("sciglob.FilterWheel1").setLevel(logging.DEBUG)
```

### Log Output Example

```
2024-01-15 10:30:45 - sciglob.serial./dev/ttyUSB0 - INFO - Opened serial port /dev/ttyUSB0 at 9600 baud
2024-01-15 10:30:45 - sciglob.HeadSensor - INFO - Connected to SciGlobHSN2 on /dev/ttyUSB0
2024-01-15 10:30:46 - sciglob.Tracker - INFO - Moving tracker: TRb-1200,4500
2024-01-15 10:30:47 - sciglob.FilterWheel1 - INFO - Setting filter wheel 1 to position 2
```

---

## Appendix: Valid Filter Names

The following filter names are recognized by the library:

```
OPAQUE          - Blocks all light
OPEN            - No filter (open position)
DIFF            - Diffuser

U340            - UV filter (340nm)
U340+DIFF       - UV filter with diffuser
BP300           - Bandpass 300nm
BP300+DIFF      - Bandpass with diffuser
LPNIR           - Long-pass NIR
LPNIR+DIFF      - Long-pass NIR with diffuser

ND1 - ND5       - Neutral density filters
ND0.1 - ND5.0   - Fine-step neutral density (0.1 increments)

DIFF1 - DIFF5   - Diffuser variants
FILTER1 - FILTER9  - Custom filters

POL0 - POL359   - Polarizer angles (0-359°)
```

---

## Appendix: Error Codes

### Device Error Codes

| Code | Message |
|------|---------|
| 0 | OK |
| 1 | Cannot read from head sensor microcontroller memory |
| 2 | Wrong tracker echo response |
| 3 | Cannot find filterwheel mirror |
| 4 | Cannot write to head sensor microcontroller memory |
| 5 | Cannot read from tracker driver register |
| 6 | Cannot write to tracker driver register |
| 7 | Cannot read sensor data |
| 8 | Cannot reset head sensor software |
| 9 | Tracker did not reset power |
| 99 | Low level serial communication error |

### Motor Alarm Codes (LuftBlickTR1)

| Code | Message |
|------|---------|
| 0 | No alarm |
| 10 | Excessive position deviation |
| 26 | Motor overheating |
| 30 | Load exceeding maximum configured torque |
| 42 | Absolute position sensor error at power on |
| 72 | Wrap setting parameter error |
| 84 | RS-485 communication error |

---

*Document Version: 1.0*  
*SciGlob Library Version: 0.1.0*  
*Last Updated: 2024*

