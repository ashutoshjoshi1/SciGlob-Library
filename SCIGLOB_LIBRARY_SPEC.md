# SciGlob Library - Hardware Connection Specification Document

## Document Purpose

This document provides comprehensive specifications for all hardware connections and communication protocols used in the Blick Software Suite. It serves as a blueprint for creating the **SciGlob Library** - a reusable Python library for hardware communication across all SciGlob projects.

---

## Table of Contents

1. [Library Overview](#1-library-overview)
2. [Architecture Design](#2-architecture-design)
3. [Serial Communication Base Layer](#3-serial-communication-base-layer)
4. [Head Sensor Module](#4-head-sensor-module)
5. [Tracker/Motor Control Module](#5-trackermotor-control-module)
6. [Filter Wheel Module](#6-filter-wheel-module)
7. [Temperature Controller Module](#7-temperature-controller-module)
8. [Humidity Sensor Module](#8-humidity-sensor-module)
9. [Positioning System (GPS) Module](#9-positioning-system-gps-module)
10. [Spectrometer Module](#10-spectrometer-module)
11. [Camera Module](#11-camera-module)
12. [Error Handling & Recovery](#12-error-handling--recovery)
13. [Implementation Prompts](#13-implementation-prompts)

---

## 1. Library Overview

### 1.1 Purpose
The SciGlob Library provides a unified, reusable hardware abstraction layer for communicating with scientific instruments used in atmospheric monitoring systems.

### 1.2 Supported Hardware

| Category | Device Types | Connection Type |
|----------|-------------|-----------------|
| Head Sensor | SciGlobHSN1, SciGlobHSN2 | RS-232 |
| Tracker/Motor | Directed Perceptions, LuftBlickTR1 | RS-232 (via Head Sensor) |
| Filter Wheel | FW1, FW2 (9 positions each) | RS-232 (via Head Sensor) |
| Shadowband | SB | RS-232 (via Head Sensor) |
| Temperature Controller | TETech1, TETech2 | RS-232 |
| Humidity Sensor | HDC2080EVM | RS-232 |
| Positioning System | Novatel (GPS+Gyro), GlobalSat (GPS) | RS-232 |
| Spectrometer | Avantes, Hamamatsu, Ocean Optics, JETI | USB (DLL/SDK) |
| Camera | DirectX, OpenCV compatible | USB |

### 1.3 Technology Stack

```
Python 3.11+
├── pyserial >= 3.5 (Serial communication)
├── numpy >= 1.24.0 (Data handling)
├── ctypes (DLL interfaces)
├── opencv-python >= 4.8.0 (Camera)
├── threading (Async operations)
└── logging (Diagnostics)
```

### 1.4 Library Structure

```
sciglob_library/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── base.py              # Abstract base classes
│   ├── serial_base.py       # Serial communication layer
│   ├── exceptions.py        # Custom exceptions
│   ├── protocols.py         # Protocol definitions
│   └── utils.py             # Utility functions
├── devices/
│   ├── __init__.py
│   ├── head_sensor.py       # Head sensor interface
│   ├── tracker.py           # Tracker/motor control
│   ├── filter_wheel.py      # Filter wheel control
│   ├── shadowband.py        # Shadowband control
│   ├── temperature.py       # Temperature controller
│   ├── humidity.py          # Humidity sensor
│   ├── positioning.py       # GPS/positioning system
│   ├── spectrometer/        # Spectrometer interfaces
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── avantes.py
│   │   ├── hamamatsu.py
│   │   ├── ocean_optics.py
│   │   └── jeti.py
│   └── camera.py            # Camera interface
├── tests/
│   ├── __init__.py
│   ├── test_serial.py
│   ├── test_head_sensor.py
│   └── ... (other tests)
└── examples/
    ├── basic_connection.py
    ├── head_sensor_example.py
    └── full_system_example.py
```

---

## 2. Architecture Design

### 2.1 Class Hierarchy

```
HardwareInterface (ABC)
├── SerialDevice (ABC)
│   ├── HeadSensor
│   │   ├── SciGlobHSN1
│   │   └── SciGlobHSN2
│   ├── TemperatureController
│   │   ├── TETech1Controller
│   │   └── TETech2Controller
│   ├── HumiditySensor
│   │   └── HDC2080EVM
│   └── PositioningSystem
│       ├── NovatelGPS
│       └── GlobalSatGPS
├── SpectrometerInterface (ABC)
│   ├── AvantesSpectrometer
│   ├── HamamatsuSpectrometer
│   ├── OceanOpticsSpectrometer
│   └── JETISpectrometer
└── CameraInterface (ABC)
    ├── DirectXCamera
    └── OpenCVCamera
```

### 2.2 Communication Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        Application Layer                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SciGlob Library API                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │  Head   │ │ Tracker │ │ Filter  │ │  Temp   │ │  Spec   │   │
│  │ Sensor  │ │ Control │ │  Wheel  │ │ Control │ │ Control │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
└───────┼──────────┼──────────┼──────────┼──────────┼─────────────┘
        │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Serial/USB Communication Layer                 │
│  ┌─────────────────────────────┐  ┌─────────────────────────┐   │
│  │      RS-232 Protocol        │  │    USB/DLL Protocol     │   │
│  │  (pyserial)                 │  │    (ctypes)             │   │
│  └─────────────────────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Physical Hardware                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Serial Communication Base Layer

### 3.1 Connection Parameters

| Parameter | Default Value | Description |
|-----------|--------------|-------------|
| Baudrate | 9600 | Bits per second |
| Bytesize | 8 | Data bits |
| Parity | 'N' (None) | Parity checking |
| Stopbits | 1 | Stop bits |
| Timeout | 0 | Read timeout (non-blocking) |
| Write Timeout | 20s | Write timeout |
| XonXoff | 0 | Software flow control |
| RtsCts | 0 | Hardware flow control |
| DsrDtr | 0 | DSR/DTR flow control |

### 3.2 Serial Port Configuration

```python
# From blick_serial.py: config_port()
def config_port(portnum: int, baudrate: int = 9600) -> tuple[str, serial.Serial]:
    """
    Configure serial port with standard parameters.
    
    Parameters:
        portnum: Port number (0-255, or <=-9 for simulation)
        baudrate: Communication speed (default 9600)
    
    Returns:
        tuple: ("OK", serial_handle) on success, ("Error...", -1) on failure
    """
    ser = serial.Serial(portnum)
    ser.baudrate = baudrate
    ser.bytesize = 8
    ser.parity = 'N'
    ser.stopbits = 1
    ser.timeout = 0
    ser.writeTimeout = 20
    ser.xonxoff = 0
    ser.rtscts = 0
    ser.dsrdtr = 0
    return "OK", ser
```

### 3.3 Question-Answer Protocol

The core communication pattern is **Question-Answer (Q/A)**:

1. **Clear buffer** - Read and flush any pending data
2. **Send question** - Write command + end character (usually `\r`)
3. **Wait for answer** - Poll for response with timeout
4. **Parse answer** - Validate response format and extract data

```python
# From blick_serial.py: ser_question()
def ser_question(ser, question: str, readbuff: bool = True, endchar: str = '\r') -> tuple[str, str]:
    """
    Send a question to serial port and manage buffer.
    
    Parameters:
        ser: Serial port handle
        question: Command string to send
        readbuff: If True, read buffer first; if False, flush directly
        endchar: End-of-text character to append (default '\r')
    
    Returns:
        tuple: ("OK", buffer_contents) on success, ("Error...", "") on failure
    """
```

### 3.4 Answer Validation

The library uses a sophisticated answer validation system:

```python
# Expected answer format specification
expans = [
    "ID",           # Element 0: ID prefix that answer must start with
    [               # Element 1: List of valid response codes
        ["0"],      # Simple integer response
        ["h", ["I","","",","], ["I","","",[]]],  # Complex: "h" + int + "," + int
    ]
]

# Example valid answers:
# "TR0\n"           -> matches ["0"]
# "TRh-120,3100\n"  -> matches ["h", int, ",", int]
```

### 3.5 Status Management

Each serial device maintains a 15-element status list:

| Index | Description | Values |
|-------|-------------|--------|
| 0 | Low-level status | -2=lost, -1=error, 0=free, 1=low-level-only, 2=busy, 3=answer-received, 9=not-from-qa |
| 1 | High-level status | 0=idle, 1=to-initiate, 2=checking, 3=waiting |
| 2 | Last command time | MJD2000 timestamp |
| 3 | Max allowed time | Seconds |
| 4 | Action details | [ID, value] |
| 5 | Last question | String |
| 6 | Expected answer | Format specification |
| 7 | Max wait time | Seconds |
| 8 | Q/A statistics | List of [time, buffer, raw_ans, readings, polished_ans, leftover, last_raw, error] |
| 9 | Unexpected answers | [actual, max_allowed] |
| 10 | Recovery info | [level, max_level, last_written, action_string, counters...] |
| 11 | Callback function | String |
| 12 | Callback arguments | List |
| 13 | Error log | String |
| 14 | Final error | String |

---

## 4. Head Sensor Module

### 4.1 Supported Types

| Type | ID Query | End Char | Features |
|------|----------|----------|----------|
| SciGlobHSN1 | "?" | "\n" | Basic head sensor |
| SciGlobHSN2 | "?" | "\n" | Extended sensors (temp, humidity, pressure) |

### 4.2 Connection Parameters (hst_pars)

| Index | Parameter | Description |
|-------|-----------|-------------|
| 0 | Port handle | Serial port object or -1 (disconnected) or <=-9 (simulation) |
| 1 | Connection type | "RS232" |
| 2 | Baudrate | Usually 9600 |
| 3 | ID string | Expected identification response |
| 4 | Sensor type | "SciGlobHSN1" or "SciGlobHSN2" |
| 5 | FW1 positions | List of 9 filter names |
| 6 | FW2 positions | List of 9 filter names |
| 7 | Tracker type | "Directed Perceptions" or "LuftBlickTR1" |
| 8 | Degrees per step | Tracker resolution |
| 9 | Motion limits | [zenith_min, zenith_max, azimuth_min, azimuth_max] |
| 13 | Shadowband params | Shadowband configuration |
| 21 | Port number | Fixed port number (0 = auto-search) |
| 22 | Home position | [zenith_home, azimuth_home] |

### 4.3 Sensor Reading Commands

```python
# SciGlobHSN2 sensor reading commands
SENSOR_COMMANDS = {
    "temperature": {"hw": "HT", "cmd": "t?", "conv_factor": 100.0, "error_val": 999.0},
    "humidity":    {"hw": "HT", "cmd": "h?", "conv_factor": 1024.0, "error_val": -9.0},
    "pressure":    {"hw": "HT", "cmd": "p?", "conv_factor": 100.0, "error_val": -9.0},
    "az_driver_temp": {"hw": "MA", "cmd": "d?", "conv_factor": 10.0, "error_val": 999.0},
    "az_motor_temp":  {"hw": "MA", "cmd": "m?", "conv_factor": 10.0, "error_val": 999.0},
    "ze_driver_temp": {"hw": "MZ", "cmd": "d?", "conv_factor": 10.0, "error_val": 999.0},
    "ze_motor_temp":  {"hw": "MZ", "cmd": "m?", "conv_factor": 10.0, "error_val": 999.0},
}

# Example: Read head sensor temperature
# Send: "HTt?\r"
# Response: "HT!91253\n"  -> Temperature = 91253 / 100.0 = 912.53°C (raw value needs scaling)
```

### 4.4 Head Sensor API

```python
class HeadSensor:
    """Head Sensor interface for SciGlob instruments."""
    
    def connect(self, port: int = None, baudrate: int = 9600) -> bool:
        """Connect to head sensor. Auto-detect port if not specified."""
        
    def disconnect(self) -> None:
        """Disconnect from head sensor."""
        
    def get_id(self) -> str:
        """Get head sensor identification string."""
        
    def get_temperature(self) -> float:
        """Read head sensor temperature (SciGlobHSN2 only)."""
        
    def get_humidity(self) -> float:
        """Read head sensor humidity (SciGlobHSN2 only)."""
        
    def get_pressure(self) -> float:
        """Read head sensor pressure (SciGlobHSN2 only)."""
        
    def power_reset(self, device: str) -> bool:
        """Power reset a connected device. device: 'TR' (tracker), 'S1' (spec1), etc."""
```

---

## 5. Tracker/Motor Control Module

### 5.1 Supported Tracker Types

| Type | Features | Aux Data Indices |
|------|----------|------------------|
| Directed Perceptions | Legacy tracker | None |
| LuftBlickTR1 | Modern tracker with motor temp sensors | [18, 19, 20, 21] |

### 5.2 Tracker Commands

| Command | Code | Description | Parameters |
|---------|------|-------------|------------|
| PAN | "p" | Move azimuth only | position (steps) |
| TILT | "t" | Move zenith only | position (steps) |
| BOTH | "b" | Move both axes | azimuth, zenith (steps) |
| RESET | "r" | Soft reset tracker | None |
| POWER | "s" | Power cycle tracker | None |
| WHERE | "w" | Get current position | None |
| MAGNETIC | "m" | Get absolute encoder position (LuftBlickTR1) | None |

### 5.3 Command Protocol

```python
# Tracker command format: "TR" + command_code + parameters + "\r"

# Examples:
# Move to position:     "TRb3100,-120\r"  -> Move to zenith=3100, azimuth=-120 (steps)
# Get position:         "TRw\r"           -> Response: "TRh-120,3100\n"
# Reset tracker:        "TRr\r"           -> Response: "TR0\n"
# Power reset:          "TRs\r"           -> Response: "TR0\n"

# Position response format: "TRh<azimuth>,<zenith>\n"
# Where h = "heading" indicator, followed by comma-separated step positions
```

### 5.4 Angle-to-Position Conversion

```python
def angle_to_position(zenith_deg: float, azimuth_deg: float, 
                      degrees_per_step: float, leveling_angles: list,
                      motion_limits: list = [0, 90, 0, 360],
                      home_position: tuple = (0.0, 180.0)) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert true horizontal angles to tracker step positions.
    
    Parameters:
        zenith_deg: True zenith angle in degrees
        azimuth_deg: True azimuth angle in degrees
        degrees_per_step: Tracker resolution (typically 0.01°/step)
        leveling_angles: [roll, pitch, yaw, zzax, azax] corrections
        motion_limits: [zen_min, zen_max, azi_min, azi_max]
        home_position: (zenith_home, azimuth_home) in degrees
    
    Returns:
        positions: Array of possible (zenith_steps, azimuth_steps)
        deltas: Angular distance to each position
    """
    # Apply leveling corrections
    zt, at, delta = horizontal_to_tracker(zenith_deg, azimuth_deg, leveling_angles, motion_limits)
    
    # Convert to steps
    zenith_steps = round((home_position[0] - zt) / degrees_per_step)
    azimuth_steps = round((home_position[1] - at) / degrees_per_step)
    
    return positions, deltas
```

### 5.5 Motor Alarm Codes (LuftBlickTR1)

```python
# Query motor alarms
# Zenith motor: "MZa?\r"  -> Response: "Alarm Code = N\n" or "MZN\n"
# Azimuth motor: "MAa?\r" -> Response: "Alarm Code = N\n" or "MAN\n"

LBTR_ALARM_CODES = {
    0: "No alarm",
    1: "Position limit exceeded",
    2: "Motor stalled",
    3: "Communication error",
    4: "Over temperature",
    5: "Cannot read from driver register",
    # ... additional codes
}
```

### 5.6 Tracker API

```python
class Tracker:
    """Tracker/Motor control interface."""
    
    def __init__(self, head_sensor: HeadSensor):
        """Initialize tracker with connected head sensor."""
        
    def move_to(self, zenith: float, azimuth: float, 
                mode: str = "ABS") -> bool:
        """
        Move tracker to position.
        
        Parameters:
            zenith: Zenith angle in degrees (or steps if mode="STEPS")
            azimuth: Azimuth angle in degrees (or steps if mode="STEPS")
            mode: "ABS" (absolute), "REL" (relative), "STEPS" (raw steps)
        """
        
    def get_position(self) -> tuple[float, float]:
        """Get current position as (zenith, azimuth) in degrees."""
        
    def get_position_steps(self) -> tuple[int, int]:
        """Get current position as (zenith_steps, azimuth_steps)."""
        
    def home(self) -> bool:
        """Move tracker to home position."""
        
    def park(self, zenith: float = 90, azimuth: float = 0) -> bool:
        """Move tracker to parking position."""
        
    def reset(self) -> bool:
        """Perform soft reset of tracker."""
        
    def power_reset(self) -> bool:
        """Perform power cycle of tracker."""
        
    def get_motor_alarms(self) -> dict:
        """Get motor alarm status (LuftBlickTR1 only)."""
        
    def get_motor_temperatures(self) -> dict:
        """Get motor temperatures (LuftBlickTR1 only)."""
```

---

## 6. Filter Wheel Module

### 6.1 Filter Wheel Configuration

| Parameter | Value |
|-----------|-------|
| Number of positions | 9 per wheel |
| Wheels | FW1, FW2 |
| Position range | 1-9 |

### 6.2 Valid Filter Types

```python
VALID_FILTERS = [
    "OPAQUE",           # Blocks all light
    "OPEN",             # No filter
    "DIFF",             # Diffuser
    "U340",             # UV filter
    "BP300",            # Bandpass 300nm
    "LPNIR",            # Long-pass NIR
    "U340+DIFF",        # Combined filters
    "BP300+DIFF",
    "LPNIR+DIFF",
    "ND1", "ND2", "ND3", "ND4", "ND5",  # Neutral density
    "ND0.1", "ND0.2", ..., "ND5.0",     # Fine ND steps
    "DIFF1", "DIFF2", ..., "DIFF5",     # Diffuser variants
    "FILTER1", ..., "FILTER9",          # Custom filters
    "POL0", "POL1", ..., "POL359",      # Polarizer angles
]
```

### 6.3 Filter Wheel Commands

```python
# Command format: "<FW_ID><action>\r"
# FW_ID: "F1" or "F2"
# action: position (1-9) or "r" (reset)

# Examples:
# Set FW1 to position 5:  "F15\r"  -> Response: "F10\n" (success)
# Reset FW1:              "F1r\r"  -> Response: "F10\n" (success)
# Set FW2 to position 3:  "F23\r"  -> Response: "F20\n" (success)
# Reset FW2:              "F2r\r"  -> Response: "F20\n" (success)

# Error responses:
# "F1N\n" where N is error code (1-9)
```

### 6.4 Filter Wheel API

```python
class FilterWheel:
    """Filter wheel control interface."""
    
    def __init__(self, head_sensor: HeadSensor, wheel_id: int = 1):
        """
        Initialize filter wheel.
        
        Parameters:
            head_sensor: Connected HeadSensor instance
            wheel_id: 1 for FW1, 2 for FW2
        """
        
    def set_position(self, position: int) -> bool:
        """
        Set filter wheel to position.
        
        Parameters:
            position: Position 1-9
        """
        
    def get_position(self) -> int:
        """Get current filter wheel position."""
        
    def reset(self) -> bool:
        """Reset filter wheel to home position."""
        
    def set_filter(self, filter_name: str) -> bool:
        """
        Set filter wheel to position containing specified filter.
        
        Parameters:
            filter_name: Filter name (e.g., "OPEN", "U340", "OPAQUE")
        """
        
    def get_filter(self) -> str:
        """Get name of current filter."""
        
    @property
    def filter_map(self) -> dict[int, str]:
        """Get mapping of positions to filter names."""
```

---

## 7. Temperature Controller Module

### 7.1 Supported Controllers

| Type | Protocol | Bit Width | Features |
|------|----------|-----------|----------|
| TETech1 | Hex commands | 16-bit | Basic control |
| TETech2 | Hex commands | 32-bit | Extended precision |

### 7.2 Connection Parameters (tc_pars)

| Index | Parameter | Description |
|-------|-----------|-------------|
| 0 | Port handle | Serial port object |
| 1 | Connection type | "RS232" |
| 2 | Baudrate | Usually 9600 |
| 3 | ID string | Expected response to ID query |
| 4 | Controller type | "TETech1" or "TETech2" |
| 5 | Set temperature | Target temperature (°C) |
| 6 | Proportional bandwidth | PID parameter |
| 7 | Integral gain | PID parameter |
| 8 | Port number | Fixed port (0 = auto) |

### 7.3 TETech Protocol

```python
# TETech1 command format: "*<cmd><hex_value><checksum>"
# TETech2 command format: "*<addr><cmd><hex_value><checksum>"

# End character: "^"

# Connection test commands:
# TETech1: "*0060"       -> Response: ID string + "^"
# TETech2: "*00430000000047" -> Response: ID string + "^"

# Write commands (TETech1):
TETECH1_WRITE_CMDS = {
    "ST": "1c",  # Set temperature
    "BW": "1d",  # Proportional bandwidth
    "IG": "1e",  # Integral gain
    "EO": "30",  # Enable output
}

# Write commands (TETech2):
TETECH2_WRITE_CMDS = {
    "ST": "1c",  # Set temperature
    "BW": "1d",  # Proportional bandwidth
    "IG": "1e",  # Integral gain
    "EO": "2d",  # Enable output
}

# Read commands (TETech1):
TETECH1_READ_CMDS = {
    "ST": "5065",  # Set temperature
    "BW": "5166",  # Proportional bandwidth
    "IG": "5267",  # Integral gain
    "T1": "0161",  # Control sensor temperature
    "T2": "0464",  # Secondary sensor temperature
}

# Read commands (TETech2):
TETECH2_READ_CMDS = {
    "ST": "00500000000045",  # Set temperature
    "BW": "00510000000046",  # Proportional bandwidth
    "IG": "00520000000047",  # Integral gain
    "T1": "00010000000041",  # Control sensor temperature
    "T2": "00060000000046",  # Secondary sensor temperature
}

# Conversion factors:
# TETech1: temperature * 10, bandwidth * 10, gain * 100
# TETech2: temperature * 100, bandwidth * 100, gain * 100
```

### 7.4 Hex Conversion Functions

```python
def dec2hex(value: int, nbits: int = 16) -> str:
    """
    Convert decimal to hex string with checksum.
    
    Parameters:
        value: Decimal integer (can be negative)
        nbits: Bit width (16 for TETech1, 32 for TETech2)
    
    Returns:
        Hex string padded to nbits/4 characters
    """
    vmax = 2 ** nbits
    nchar = nbits // 4
    if value < 0:
        vhex = hex(vmax + value)[2:-1]
    else:
        vhex = hex(abs(value))[2:-1]
    return vhex.zfill(nchar)

def get_checksum(hex_string: str) -> str:
    """Calculate checksum for TETech commands."""
    # Sum of ASCII values mod 256, as 2-char hex
    checksum = sum(ord(c) for c in hex_string) % 256
    return format(checksum, '02x')
```

### 7.5 Temperature Controller API

```python
class TemperatureController:
    """Temperature controller interface for TETech devices."""
    
    def connect(self, port: int = None, baudrate: int = 9600,
                controller_type: str = "TETech1") -> bool:
        """Connect to temperature controller."""
        
    def disconnect(self) -> None:
        """Disconnect from temperature controller."""
        
    def set_temperature(self, temp: float) -> bool:
        """Set target temperature in °C."""
        
    def get_temperature(self) -> float:
        """Get control sensor temperature in °C."""
        
    def get_secondary_temperature(self) -> float:
        """Get secondary sensor temperature in °C."""
        
    def get_setpoint(self) -> float:
        """Get current temperature setpoint in °C."""
        
    def set_pid_parameters(self, bandwidth: float = None, 
                           integral_gain: float = None) -> bool:
        """Set PID control parameters."""
        
    def enable_output(self) -> bool:
        """Enable temperature control output."""
        
    def disable_output(self) -> bool:
        """Disable temperature control output."""
```

---

## 8. Humidity Sensor Module

### 8.1 Supported Sensors

| Type | Protocol | Features |
|------|----------|----------|
| HDC2080EVM | RS-232 | Temperature + Humidity |

### 8.2 HDC2080EVM Protocol

```python
# End character: "\r\n"

# Commands:
# ID query: "?"           -> Response: "S,HDC2080EVM,part,\r\n"
# Initialize: "stream stop" -> Response: "stream stop\r\n"
# Read humidity: "H"      -> Response: 4-char hex + "\r\n"
# Read temperature: "T"   -> Response: 4-char hex + "\r\n"

# Humidity conversion:
# Raw hex is little-endian (last 2 chars + first 2 chars)
# H = (int_value / 2^16) * 100  [%]

# Temperature conversion:
# T = (int_value / 2^16) * 165 - 40  [°C]
```

### 8.3 Humidity Sensor API

```python
class HumiditySensor:
    """Humidity sensor interface for HDC2080EVM."""
    
    def connect(self, port: int = None, baudrate: int = 9600) -> bool:
        """Connect to humidity sensor."""
        
    def disconnect(self) -> None:
        """Disconnect from humidity sensor."""
        
    def initialize(self) -> bool:
        """Initialize sensor (stop any streaming)."""
        
    def get_humidity(self) -> float:
        """Get relative humidity in %."""
        
    def get_temperature(self) -> float:
        """Get temperature in °C."""
        
    def get_readings(self) -> dict:
        """Get both humidity and temperature."""
```

---

## 9. Positioning System (GPS) Module

### 9.1 Supported Systems

| Type | Protocol | Features |
|------|----------|----------|
| Novatel | NMEA + Proprietary | GPS + Gyroscope (tilt sensing) |
| GlobalSat | NMEA | GPS only |

### 9.2 Novatel Protocol

```python
# End character: "\r\n[USB1]"

# Commands:
# Clear logs:     "unlogall"              -> Response: "\r\n<OK"
# Read once:      "log inspva once"       -> Response: INSPVA data
# Start logging:  "log inspva ontime 1"   -> Response: "\r\n<OK"

# INSPVA response format:
# <INSPVA USB1 0 95.0 FINESTEERING week seconds status ...
# < week seconds lat lon alt vn ve vu roll pitch yaw INS_SOLUTION_GOOD

# Data extraction:
# Position: lat (index 2), lon (index 3), alt (index 4)
# Orientation: roll (index 8), pitch (index 9), yaw (index 10)
```

### 9.3 GlobalSat Protocol

```python
# End character: "\r\n"

# Disable automatic messages:
# "$PSRF103,04,00,00,01*20"  # Disable RMC
# "$PSRF103,02,00,00,01*26"  # Disable GSA
# "$PSRF103,03,00,00,01*27"  # Disable GSV
# "$PSRF103,00,00,00,01*24"  # Disable GGA

# Query GGA:
# "$PSRF103,00,01,00,01*25" -> Response: $GPGGA,...

# GPGGA format:
# $GPGGA,time,lat,N/S,lon,E/W,quality,sats,hdop,alt,M,geoid,M,age,refid*checksum
# Example: $GPGGA,170145.000,3859.3500,N,07652.8949,W,1,07,1.7,42.0,M,-33.5,M,,0000*5C

# Latitude conversion: DDMM.MMMM -> DD + MM.MMMM/60
# Longitude conversion: DDDMM.MMMM -> DDD + MM.MMMM/60
```

### 9.4 Positioning System API

```python
class PositioningSystem:
    """GPS/Positioning system interface."""
    
    def connect(self, port: int = None, baudrate: int = 9600,
                system_type: str = "GlobalSat") -> bool:
        """Connect to positioning system."""
        
    def disconnect(self) -> None:
        """Disconnect from positioning system."""
        
    def configure(self) -> bool:
        """Configure device (disable automatic messages)."""
        
    def get_position(self) -> dict:
        """
        Get current position.
        
        Returns:
            {
                "latitude": float,    # Degrees (+ = North)
                "longitude": float,   # Degrees (+ = East)
                "altitude": float,    # Meters above sea level
                "quality": int,       # Fix quality (0 = no fix)
            }
        """
        
    def get_orientation(self) -> dict:
        """
        Get orientation (Novatel only).
        
        Returns:
            {
                "roll": float,   # East-West tilt (degrees)
                "pitch": float,  # North-South tilt (degrees)
                "yaw": float,    # Azimuth (degrees)
            }
        """
        
    def start_logging(self, interval: float = 1.0) -> bool:
        """Start continuous logging (Novatel only)."""
        
    def stop_logging(self) -> bool:
        """Stop continuous logging."""
```

---

## 10. Spectrometer Module

### 10.1 Supported Spectrometers

| Type | Interface | DLL | Features |
|------|-----------|-----|----------|
| Avantes (Ava1) | USB | avaspec.dll | High-speed, temperature sensor |
| Hamamatsu (Hama1) | USB | Hamamatsu SDK | Anti-blooming |
| Ocean Optics (OcOpt1) | USB | OmniDriver.jar | Java-based |
| JETI (JETI1) | USB | jeti_core.dll | High dynamic range |

### 10.2 Spectrometer Parameters (spec_pars)

| Index | Parameter | Description |
|-------|-----------|-------------|
| 0 | Handle | Device handle or <=-9 (simulation) |
| 3 | ROE type | "Ava1", "Hama1", "OcOpt1", "JETI1" |
| 5 | Pixel info | [active_pixels, blind_pixels] |
| 6 | Bit depth | Number of bits (e.g., 16) |
| 8 | Min IT | Minimum integration time (ms) |
| 9 | Max IT | Maximum integration time (ms) |
| 10 | IT resolution | Integration time resolution (ms) |
| 17 | Shutter | 0 = no shutter, 1 = has shutter |
| 19 | Max cycles | Maximum cycles per measurement |
| -1 | Saturation | Saturation count level |

### 10.3 Common Spectrometer Operations

```python
# Main operations (from blick_spectrometer.py):
# 1. reset() - Initialize and test spectrometer
# 2. disconnect() - Clean disconnection
# 3. set_it() - Set integration time
# 4. access_settings() - Read/write settings
# 5. measure() - Take measurements
# 6. get_temp() - Read temperature sensor
# 7. get_error() - Translate error codes
```

### 10.4 Measurement Data Structure

```python
# Measurement results:
# rcm[ispec] - Mean counts per pixel (array)
# rcs[ispec] - Standard deviation per pixel (array, if ncy > 1)
# rcl[ispec] - Linear fit residual per pixel (array, if ncy > 2)

# Data status (data_status[ispec]):
# [0] - Status: 0=idle, 1=measuring, 2=received, 3=processed
# [1] - Measurement start time
# [2] - Data receive time
# [3] - [min_expected_time, max_expected_time]
# [4] - Number of cycles (ncy)
# [5] - Current cycle index
# [6] - Number of repetitions (nrep)
# [7] - Current repetition index
# [8] - Saturation check mode
# [9] - Recovery level info
# [10] - Integration time (ms)
# ...
```

### 10.5 Spectrometer API

```python
class Spectrometer(ABC):
    """Abstract base class for spectrometer interfaces."""
    
    @abstractmethod
    def connect(self) -> bool:
        """Connect to spectrometer."""
        
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from spectrometer."""
        
    @abstractmethod
    def reset(self, full_init: bool = True) -> bool:
        """Reset spectrometer."""
        
    @abstractmethod
    def set_integration_time(self, time_ms: float) -> bool:
        """Set integration time in milliseconds."""
        
    @abstractmethod
    def get_integration_time(self) -> float:
        """Get current integration time in milliseconds."""
        
    @abstractmethod
    def measure(self, cycles: int = 1) -> MeasurementResult:
        """
        Take measurement.
        
        Parameters:
            cycles: Number of integration cycles
            
        Returns:
            MeasurementResult with mean, std, and metadata
        """
        
    @abstractmethod
    def get_temperature(self, sensor: str = "detector") -> float:
        """Get temperature reading."""
        
    @abstractmethod
    def get_wavelength_calibration(self) -> np.ndarray:
        """Get wavelength calibration array."""
        
    @property
    @abstractmethod
    def pixel_count(self) -> int:
        """Get number of active pixels."""
        
    @property
    @abstractmethod
    def saturation_level(self) -> int:
        """Get saturation count level."""


class AvantesSpectrometer(Spectrometer):
    """Avantes spectrometer implementation."""
    
    def __init__(self, dll_path: str = None):
        """Initialize with optional DLL path."""
        
    # ... implementation details


class MeasurementResult:
    """Container for spectrometer measurement results."""
    
    timestamp: float          # Measurement time (MJD2000)
    integration_time: float   # Integration time (ms)
    cycles: int              # Number of cycles
    mean_counts: np.ndarray  # Mean counts per pixel
    std_counts: np.ndarray   # Standard deviation (if cycles > 1)
    linear_residual: np.ndarray  # Linear fit residual (if cycles > 2)
    temperature: float       # Detector temperature
    saturated: bool          # Saturation detected
    error: str               # Error message or "OK"
```

---

## 11. Camera Module

### 11.1 Supported Backends

| Backend | Platform | Features |
|---------|----------|----------|
| DirectX | Windows | Low-latency capture |
| OpenCV | Cross-platform | Universal compatibility |

### 11.2 Camera Parameters (cam_pars)

| Index | Parameter | Description |
|-------|-----------|-------------|
| 0 | Backend | "DirectX" or "OpenCV" |
| 1 | Device index | Camera index |
| 2 | Resolution | [width, height] |
| 3 | Frame rate | Frames per second |
| 4 | Exposure | Exposure time (ms) |
| 5 | Gain | Camera gain |

### 11.3 Solar Tracking Parameters

```python
# Camera tracking configuration:
# - Update interval: 100 ms
# - Effective center: [x_pixels, y_pixels]
# - Effective solar radius: pixels
# - Pixels per degree: conversion factor
# - RMS tolerances: [sun_tolerance, moon_tolerance]
# - Optical FOV: degrees
# - Rotation angle: degrees (camera mounting)
# - Angular tolerance: degrees
```

### 11.4 Camera API

```python
class Camera:
    """Camera interface for solar/lunar tracking."""
    
    def connect(self, device_index: int = 0, 
                backend: str = "OpenCV") -> bool:
        """Connect to camera."""
        
    def disconnect(self) -> None:
        """Disconnect from camera."""
        
    def capture_frame(self) -> np.ndarray:
        """Capture single frame."""
        
    def start_stream(self) -> None:
        """Start continuous capture."""
        
    def stop_stream(self) -> None:
        """Stop continuous capture."""
        
    def get_frame(self) -> np.ndarray:
        """Get latest frame from stream."""
        
    def set_exposure(self, exposure_ms: float) -> bool:
        """Set exposure time."""
        
    def set_gain(self, gain: int) -> bool:
        """Set camera gain."""
        
    def find_sun_position(self, frame: np.ndarray = None) -> tuple[int, int]:
        """
        Find sun position in frame.
        
        Returns:
            (x, y) pixel coordinates of sun center, or None if not found
        """
        
    def calculate_pointing_offset(self, sun_position: tuple[int, int],
                                   target_position: tuple[int, int]) -> tuple[float, float]:
        """
        Calculate angular offset from target.
        
        Returns:
            (azimuth_offset, zenith_offset) in degrees
        """
```

---

## 12. Error Handling & Recovery

### 12.1 Error Code System

```python
# Common error codes (from blick_serial.LoadErrorCodes):
ERROR_CODES = [
    (0, "OK"),
    (1, "General error"),
    (2, "Communication timeout"),
    (3, "Invalid response"),
    (4, "Command not acknowledged"),
    (5, "Device busy"),
    (6, "Position limit exceeded"),
    (7, "Motor blocked"),
    (8, "Temperature out of range"),
    (9, "Calibration error"),
    (99, "Low level serial communication error"),
]
```

### 12.2 Recovery System

The library implements a multi-level recovery system:

```python
# Recovery levels for head sensor/tracker:
HST_RECOVERY_LEVELS = [
    (0, "Normal operation"),
    (1, "Retry command"),
    (2, "Wait for device"),
    (3, "Check communication"),
    (4, "Reset filterwheel 1"),
    (5, "Reset filterwheel 2"),
    (6, "Soft reset device"),
    (7, "Wait for reset"),
    (8, "Power cycle device"),
    (9, "Wait for power cycle"),
    (10, "Close/reopen serial port"),
    (11, "Query device status"),
    (12, "Check motor alarms"),
    (13, "Maximum recovery - abort"),
]

# Recovery is automatic and transparent to the user
# Each level is tried before escalating to the next
```

### 12.3 Exception Hierarchy

```python
class SciGlobError(Exception):
    """Base exception for SciGlob Library."""
    pass

class ConnectionError(SciGlobError):
    """Failed to connect to device."""
    pass

class CommunicationError(SciGlobError):
    """Communication with device failed."""
    pass

class TimeoutError(SciGlobError):
    """Operation timed out."""
    pass

class DeviceError(SciGlobError):
    """Device reported an error."""
    pass

class ConfigurationError(SciGlobError):
    """Invalid configuration."""
    pass

class RecoveryError(SciGlobError):
    """Recovery attempts exhausted."""
    pass
```

---

## 13. Implementation Prompts

### Prompt 1: Core Infrastructure

```
Create the core infrastructure for the SciGlob Library:

1. Create `sciglob_library/core/base.py`:
   - Abstract base class `HardwareInterface` with:
     - Methods: connect(), disconnect(), is_connected(), reset(), get_status()
     - Properties: device_id, connection_type, status
   - Enum `HardwareStatus`: DISCONNECTED, CONNECTING, CONNECTED, ERROR
   - Exception classes: SciGlobError, ConnectionError, CommunicationError, etc.

2. Create `sciglob_library/core/serial_base.py`:
   - Class `SerialDevice(HardwareInterface)` with:
     - Serial port configuration (baudrate, parity, etc.)
     - Question-answer protocol implementation
     - Buffer management
     - Timeout handling
     - Status tracking (15-element list as documented)
   - Methods: config_port(), ser_question(), check_answer(), scan_ports()

3. Create `sciglob_library/core/protocols.py`:
   - Protocol definitions for answer validation
   - Checksum calculation functions
   - Hex conversion utilities

4. Create `sciglob_library/core/utils.py`:
   - Timestamp utilities (MJD2000 conversion)
   - Angle conversion functions
   - Data validation helpers

5. Unit tests for all core components

Use Python 3.11+ with type hints, dataclasses, and comprehensive docstrings.
Reference the Blick codebase for exact protocol details.
```

### Prompt 2: Head Sensor Module

```
Create the Head Sensor module for SciGlob Library:

1. Create `sciglob_library/devices/head_sensor.py`:
   - Class `HeadSensor(SerialDevice)` supporting:
     - SciGlobHSN1 and SciGlobHSN2 types
     - Auto-detection of sensor type
     - Connection with port auto-search
     - Sensor readings (temperature, humidity, pressure)
     - Power reset commands for connected devices
   
2. Implement the exact protocol from Blick:
   - ID query: "?" with "\n" end character
   - Sensor commands: "HTt?", "HTh?", "HTp?"
   - Response parsing with conversion factors
   - Error code handling

3. Parameters structure (hst_pars equivalent):
   - Port handle, connection type, baudrate
   - ID string, sensor type
   - Filter wheel configurations
   - Tracker parameters
   - Motion limits

4. Create comprehensive unit tests with mocked serial ports

Reference blick_serial.py: get_port(), get_sensorreading(), hst_recoverycycle()
```

### Prompt 3: Tracker Module

```
Create the Tracker/Motor Control module for SciGlob Library:

1. Create `sciglob_library/devices/tracker.py`:
   - Class `Tracker` that uses HeadSensor for communication
   - Support for "Directed Perceptions" and "LuftBlickTR1"
   
2. Implement tracker commands:
   - PAN (azimuth only): "TRp<steps>"
   - TILT (zenith only): "TRt<steps>"
   - BOTH (both axes): "TRb<azi>,<zen>"
   - RESET: "TRr"
   - POWER: "TRs"
   - WHERE: "TRw" -> "TRh<azi>,<zen>"
   - MAGNETIC: "TRm" (LuftBlickTR1 only)

3. Implement angle-to-position conversion:
   - Leveling angle corrections
   - Motion limit checking
   - Home position offset
   - Multiple valid positions calculation

4. Implement motor alarm queries (LuftBlickTR1):
   - "MZa?" for zenith motor
   - "MAa?" for azimuth motor
   - Alarm code interpretation

5. Implement recovery system with 18 levels

Reference blick_serial.py: set_tracker(), get_tracker(), angle2pos(), pos2angle()
```

### Prompt 4: Filter Wheel Module

```
Create the Filter Wheel module for SciGlob Library:

1. Create `sciglob_library/devices/filter_wheel.py`:
   - Class `FilterWheel` that uses HeadSensor for communication
   - Support for FW1 and FW2 (9 positions each)

2. Implement commands:
   - Set position: "F1<1-9>" or "F2<1-9>"
   - Reset: "F1r" or "F2r"
   - Response parsing: "F10" (success) or "F1N" (error N)

3. Features:
   - Filter name to position mapping
   - Position validation
   - Error handling with codes

4. Create valid filter list:
   - OPAQUE, OPEN, DIFF
   - U340, BP300, LPNIR (with +DIFF variants)
   - ND1-ND5, ND0.1-ND5.0
   - DIFF1-DIFF5
   - FILTER1-FILTER9
   - POL0-POL359

Reference blick_serial.py: set_headsensor() with part="F1"/"F2"
Reference blick_routinereader.py: MakeFilterwheelCommands()
```

### Prompt 5: Temperature Controller Module

```
Create the Temperature Controller module for SciGlob Library:

1. Create `sciglob_library/devices/temperature.py`:
   - Class `TemperatureController(SerialDevice)`
   - Support for TETech1 (16-bit) and TETech2 (32-bit)

2. Implement TETech protocol:
   - Connection test: "*0060" (TETech1), "*00430000000047" (TETech2)
   - End character: "^"
   - Hex encoding with checksum
   - Read/write commands for ST, BW, IG, EO, T1, T2

3. Implement hex conversion:
   - dec2hex() with signed number support
   - get_checksum() for command validation
   - Conversion factors: 10 (TETech1), 100 (TETech2)

4. Features:
   - Set/get temperature setpoint
   - Set/get PID parameters
   - Read control and secondary sensors
   - Enable/disable output

Reference blick_serial.py: set_tcparam(), get_tcparam(), dec2hex()
```

### Prompt 6: Humidity Sensor Module

```
Create the Humidity Sensor module for SciGlob Library:

1. Create `sciglob_library/devices/humidity.py`:
   - Class `HumiditySensor(SerialDevice)`
   - Support for HDC2080EVM

2. Implement HDC2080EVM protocol:
   - ID query: "?" -> "S,HDC2080EVM,part,"
   - Initialize: "stream stop"
   - Read humidity: "H" -> 4-char hex
   - Read temperature: "T" -> 4-char hex
   - End character: "\r\n"

3. Implement data conversion:
   - Little-endian hex parsing
   - Humidity: (value / 2^16) * 100 [%]
   - Temperature: (value / 2^16) * 165 - 40 [°C]

Reference blick_serial.py: sbhs_control()
Reference blick_params.py: valsbhstyp
```

### Prompt 7: Positioning System Module

```
Create the Positioning System (GPS) module for SciGlob Library:

1. Create `sciglob_library/devices/positioning.py`:
   - Class `PositioningSystem(SerialDevice)`
   - Support for Novatel and GlobalSat

2. Implement Novatel protocol:
   - Commands: unlogall, log inspva once, log inspva ontime N
   - End character: "\r\n[USB1]"
   - INSPVA response parsing
   - Position and orientation extraction

3. Implement GlobalSat protocol:
   - NMEA message disabling
   - GGA query: "$PSRF103,00,01,00,01*25"
   - GPGGA parsing
   - Coordinate conversion (DDMM.MMMM -> decimal degrees)

4. Implement position decoding:
   - Latitude, longitude, altitude
   - Roll, pitch, yaw (Novatel)
   - Coordinate system conversions

Reference blick_serial.py: qa_position(), decode_position()
```

### Prompt 8: Spectrometer Base Module

```
Create the Spectrometer base module for SciGlob Library:

1. Create `sciglob_library/devices/spectrometer/base.py`:
   - Abstract class `Spectrometer(HardwareInterface)`
   - MeasurementResult dataclass
   - Common interfaces for all spectrometer types

2. Define abstract methods:
   - connect(), disconnect(), reset()
   - set_integration_time(), get_integration_time()
   - measure(), get_temperature()
   - get_wavelength_calibration()

3. Define common properties:
   - pixel_count, saturation_level
   - min_integration_time, max_integration_time
   - bit_depth, has_shutter

4. Implement measurement status tracking:
   - Status states (idle, measuring, received, processed)
   - Timing information
   - Saturation detection
   - Recovery level management

5. Create factory function:
   - create_spectrometer(roe_type, **params) -> Spectrometer

Reference blick_spectrometer.py: class structure and data_status
```

### Prompt 9: Avantes Spectrometer Implementation

```
Create the Avantes spectrometer implementation for SciGlob Library:

1. Create `sciglob_library/devices/spectrometer/avantes.py`:
   - Class `AvantesSpectrometer(Spectrometer)`
   - ctypes interface to avaspec.dll

2. Implement DLL interface:
   - Device discovery and enumeration
   - Connection/disconnection
   - Integration time control
   - Measurement triggering
   - Data retrieval
   - Temperature reading

3. Implement data structures:
   - AVS_HANDLE, AVS_IDENTITY
   - Measurement configuration
   - Pixel data arrays

4. Implement measurement workflow:
   - Start measurement with cycle count
   - Wait for data arrival
   - Retrieve and process data
   - Calculate mean, std, linear residual

5. Error handling:
   - DLL error code translation
   - Recovery from communication failures

Reference blick_spectrometer.py: reset_Ava1(), measure_Ava1(), etc.
```

### Prompt 10: Integration and Testing

```
Create integration layer and comprehensive tests for SciGlob Library:

1. Create `sciglob_library/__init__.py`:
   - Export all public classes
   - Version information
   - Convenience factory functions

2. Create `sciglob_library/examples/`:
   - basic_connection.py: Connect to single device
   - head_sensor_example.py: Full head sensor workflow
   - measurement_example.py: Take spectrometer measurements
   - full_system_example.py: Complete instrument control

3. Create comprehensive test suite:
   - Unit tests with mocked hardware
   - Integration tests (optional, with real hardware)
   - Protocol compliance tests
   - Error handling tests
   - Recovery system tests

4. Create documentation:
   - API reference
   - Usage examples
   - Protocol specifications
   - Troubleshooting guide

5. Create setup.py/pyproject.toml:
   - Package metadata
   - Dependencies
   - Entry points
```

---

## Appendix A: Quick Reference

### Serial Port Commands Quick Reference

| Device | Command | Response | Description |
|--------|---------|----------|-------------|
| Head Sensor | `?` | ID string | Identification |
| Head Sensor | `HTt?` | `HT!NNNNN` | Temperature |
| Head Sensor | `HTh?` | `HT!NNNNN` | Humidity |
| Head Sensor | `HTp?` | `HT!NNNNN` | Pressure |
| Tracker | `TRw` | `TRhA,Z` | Get position |
| Tracker | `TRbA,Z` | `TR0` | Move both |
| Tracker | `TRr` | `TR0` | Reset |
| Tracker | `TRs` | `TR0` | Power reset |
| Filter Wheel | `F1N` | `F10` | Set FW1 to N |
| Filter Wheel | `F1r` | `F10` | Reset FW1 |
| Temp Controller | `*0060` | ID + `^` | TETech1 ID |
| Humidity | `?` | `S,HDC2080EVM,...` | ID |
| Humidity | `H` | 4-char hex | Read humidity |
| GPS (GlobalSat) | `$PSRF103,00,01,00,01*25` | `$GPGGA,...` | Query position |

### Error Codes Quick Reference

| Code | Meaning |
|------|---------|
| 0 | OK - Success |
| 1 | General error |
| 2 | Timeout |
| 3 | Invalid response |
| 4 | Command not acknowledged |
| 5 | Device busy |
| 99 | Low-level communication error |

---

*This document provides the complete specification for implementing the SciGlob Library. Each prompt in Section 13 can be given to an AI coder to implement that specific module.*

*Document Version: 1.0*
*Last Updated: 2024*

