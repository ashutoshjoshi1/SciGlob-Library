# SciGlob Library - Complete Command Reference

## Document Purpose

This document provides a **complete reference of all serial commands, protocols, and message formats** used in the Blick Software Suite for hardware communication. Use this document alongside `SCIGLOB_LIBRARY_SPEC.md` for implementing the SciGlob Library.

---

## Table of Contents

1. [Communication Protocol Overview](#1-communication-protocol-overview)
2. [Head Sensor Commands](#2-head-sensor-commands)
3. [Tracker Commands](#3-tracker-commands)
4. [Filter Wheel Commands](#4-filter-wheel-commands)
5. [Shadowband Commands](#5-shadowband-commands)
6. [Temperature Controller Commands](#6-temperature-controller-commands)
7. [Humidity Sensor Commands](#7-humidity-sensor-commands)
8. [Positioning System Commands](#8-positioning-system-commands)
9. [Error Codes Reference](#9-error-codes-reference)
10. [Response Parsing Patterns](#10-response-parsing-patterns)
11. [Timing Parameters](#11-timing-parameters)
12. [Code Examples](#12-code-examples)

---

## 1. Communication Protocol Overview

### 1.1 Serial Port Configuration

```python
# Standard RS-232 Configuration
SERIAL_CONFIG = {
    "baudrate": 9600,      # Default baud rate
    "bytesize": 8,         # Data bits
    "parity": "N",         # No parity
    "stopbits": 1,         # Stop bits
    "timeout": 0,          # Non-blocking read
    "writeTimeout": 20,    # Write timeout (seconds)
    "xonxoff": 0,          # No software flow control
    "rtscts": 0,           # No hardware flow control
    "dsrdtr": 0,           # No DSR/DTR
}
```

### 1.2 Message Format

All serial commands follow this general pattern:

```
COMMAND = <DEVICE_ID><ACTION_CODE>[<PARAMETERS>]<END_CHAR>
RESPONSE = <DEVICE_ID><RESULT>[<DATA>]<END_CHAR>
```

### 1.3 End Characters by Device

| Device | Command End Char | Response End Char |
|--------|-----------------|-------------------|
| Head Sensor | `\r` | `\n` |
| Tracker | `\r` | `\n` |
| Filter Wheel | `\r` | `\n` |
| Shadowband | `\r` | `\n` |
| TETech Controller | `\r` | `^` |
| HDC2080EVM | `\r` | `\r\n` |
| Novatel GPS | `\r` | `\r\n[USB1]` |
| GlobalSat GPS | `\r\n` | `\r\n` |

---

## 2. Head Sensor Commands

### 2.1 Device Identification

| Command | Description | Expected Response |
|---------|-------------|-------------------|
| `?` | Query device ID | Device ID string (e.g., "SciGlobHSN2") |

**Protocol Details:**
```
Send:    "?\r"
Receive: "<device_id>\n"

Example:
Send:    "?\r"
Receive: "SciGlobHSN2\n"
```

### 2.2 Sensor Readings (SciGlobHSN2 only)

#### 2.2.1 Temperature Reading

| Command | Description | Response Format | Conversion |
|---------|-------------|-----------------|------------|
| `HTt?` | Read head temperature | `HT!NNNNN\n` | value / 100.0 °C |

```
Send:    "HTt?\r"
Receive: "HT!23456\n"
Result:  23456 / 100.0 = 234.56°C (Note: raw value, check scaling)

Error Response: "HT<error_code>\n"
```

#### 2.2.2 Humidity Reading

| Command | Description | Response Format | Conversion |
|---------|-------------|-----------------|------------|
| `HTh?` | Read head humidity | `HT!NNNNN\n` | value / 1024.0 % |

```
Send:    "HTh?\r"
Receive: "HT!51200\n"
Result:  51200 / 1024.0 = 50.0%

Error Response: "HT<error_code>\n"
```

#### 2.2.3 Pressure Reading

| Command | Description | Response Format | Conversion |
|---------|-------------|-----------------|------------|
| `HTp?` | Read head pressure | `HT!NNNNN\n` | value / 100.0 mbar |

```
Send:    "HTp?\r"
Receive: "HT!101325\n"
Result:  101325 / 100.0 = 1013.25 mbar

Error Response: "HT<error_code>\n"
```

### 2.3 Motor Temperature Readings (LuftBlickTR1 Tracker)

#### 2.3.1 Azimuth Motor Temperatures

| Command | Description | Response Format | Conversion |
|---------|-------------|-----------------|------------|
| `MAd?` | Azimuth driver temperature | `MA!NNNNN\n` | value / 10.0 °C |
| `MAm?` | Azimuth motor temperature | `MA!NNNNN\n` | value / 10.0 °C |

```
Send:    "MAd?\r"
Receive: "MA!215\n"
Result:  215 / 10.0 = 21.5°C
```

#### 2.3.2 Zenith Motor Temperatures

| Command | Description | Response Format | Conversion |
|---------|-------------|-----------------|------------|
| `MZd?` | Zenith driver temperature | `MZ!NNNNN\n` | value / 10.0 °C |
| `MZm?` | Zenith motor temperature | `MZ!NNNNN\n` | value / 10.0 °C |

```
Send:    "MZd?\r"
Receive: "MZ!223\n"
Result:  223 / 10.0 = 22.3°C
```

### 2.4 Sensor Reading Command Summary

```python
# Complete sensor command reference
HEAD_SENSOR_COMMANDS = {
    # Head Sensor Type: SciGlobHSN2
    "temperature": {
        "device_id": "HT",
        "command": "t?",
        "full_command": "HTt?",
        "conversion_factor": 100.0,
        "unit": "°C",
        "error_value": 999.0,
        "simulated_value": 20.0,
    },
    "humidity": {
        "device_id": "HT",
        "command": "h?",
        "full_command": "HTh?",
        "conversion_factor": 1024.0,
        "unit": "%",
        "error_value": -9.0,
        "simulated_value": 60.0,
    },
    "pressure": {
        "device_id": "HT",
        "command": "p?",
        "full_command": "HTp?",
        "conversion_factor": 100.0,
        "unit": "mbar",
        "error_value": -9.0,
        "simulated_value": 1013.0,
    },
    # Tracker Motor Temperatures (LuftBlickTR1)
    "azimuth_driver_temp": {
        "device_id": "MA",
        "command": "d?",
        "full_command": "MAd?",
        "conversion_factor": 10.0,
        "unit": "°C",
        "error_value": 999.0,
        "simulated_value": 21.0,
    },
    "azimuth_motor_temp": {
        "device_id": "MA",
        "command": "m?",
        "full_command": "MAm?",
        "conversion_factor": 10.0,
        "unit": "°C",
        "error_value": 999.0,
        "simulated_value": 22.0,
    },
    "zenith_driver_temp": {
        "device_id": "MZ",
        "command": "d?",
        "full_command": "MZd?",
        "conversion_factor": 10.0,
        "unit": "°C",
        "error_value": 999.0,
        "simulated_value": 23.0,
    },
    "zenith_motor_temp": {
        "device_id": "MZ",
        "command": "m?",
        "full_command": "MZm?",
        "conversion_factor": 10.0,
        "unit": "°C",
        "error_value": 999.0,
        "simulated_value": 24.0,
    },
}
```

---

## 3. Tracker Commands

### 3.1 Device ID: `TR`

All tracker commands use the prefix `TR`.

### 3.2 Movement Commands

| Command | Format | Description | Response |
|---------|--------|-------------|----------|
| PAN | `TRp<azimuth>` | Move azimuth only | `TR0\n` (success) |
| TILT | `TRt<zenith>` | Move zenith only | `TR0\n` (success) |
| BOTH | `TRb<azimuth>,<zenith>` | Move both axes | `TR0\n` (success) |
| RESET | `TRr` | Soft reset tracker | `TR0\n` (success) |
| POWER | `TRs` | Power cycle tracker | `TR0\n` (success) |

**Position values are in STEPS (integer), not degrees!**

```
# Move azimuth to step position -1200
Send:    "TRp-1200\r"
Receive: "TR0\n"

# Move zenith to step position 3100
Send:    "TRt3100\r"
Receive: "TR0\n"

# Move both axes: azimuth=-1200, zenith=3100
Send:    "TRb-1200,3100\r"
Receive: "TR0\n"

# Reset tracker
Send:    "TRr\r"
Receive: "TR0\n"

# Power cycle tracker
Send:    "TRs\r"
Receive: "TR0\n"
```

### 3.3 Position Query Commands

| Command | Description | Response Format |
|---------|-------------|-----------------|
| `TRw` | Get current position | `TRh<azimuth>,<zenith>\n` |
| `TRm` | Get magnetic encoder position (LuftBlickTR1) | `TRh<azimuth>,<zenith>\n` |

```
# Query current position
Send:    "TRw\r"
Receive: "TRh-1200,3100\n"
Result:  azimuth = -1200 steps, zenith = 3100 steps

# Query absolute encoder position (LuftBlickTR1 only)
Send:    "TRm\r"
Receive: "TRh-1198,3102\n"
```

### 3.4 Motor Alarm Commands (LuftBlickTR1 only)

| Command | Description | Response Format |
|---------|-------------|-----------------|
| `MZa?` | Query zenith motor alarms | `Alarm Code = N\n` or `MZN\n` |
| `MAa?` | Query azimuth motor alarms | `Alarm Code = N\n` or `MAN\n` |

```
# Query zenith motor alarm
Send:    "MZa?\r"
Receive: "Alarm Code = 0\n"  # No alarm
   -or-  "Alarm Code = 26\n" # Motor overheating
   -or-  "MZ5\n"             # Error code 5

# Query azimuth motor alarm
Send:    "MAa?\r"
Receive: "Alarm Code = 0\n"  # No alarm
```

### 3.5 Tracker Command Summary

```python
# Complete tracker command reference
TRACKER_COMMANDS = {
    "pan": {
        "code": "p",
        "format": "TRp{azimuth_steps}",
        "description": "Move azimuth only",
        "parameters": ["azimuth_steps (int)"],
        "response": "TR0 (success) or TR<error_code>",
    },
    "tilt": {
        "code": "t",
        "format": "TRt{zenith_steps}",
        "description": "Move zenith only",
        "parameters": ["zenith_steps (int)"],
        "response": "TR0 (success) or TR<error_code>",
    },
    "both": {
        "code": "b",
        "format": "TRb{azimuth_steps},{zenith_steps}",
        "description": "Move both axes",
        "parameters": ["azimuth_steps (int)", "zenith_steps (int)"],
        "response": "TR0 (success) or TR<error_code>",
    },
    "reset": {
        "code": "r",
        "format": "TRr",
        "description": "Soft reset tracker",
        "parameters": [],
        "response": "TR0 (success) or TR<error_code>",
    },
    "power": {
        "code": "s",
        "format": "TRs",
        "description": "Power cycle tracker",
        "parameters": [],
        "response": "TR0 (success) or TR<error_code>",
    },
    "where": {
        "code": "w",
        "format": "TRw",
        "description": "Query current position",
        "parameters": [],
        "response": "TRh<azimuth>,<zenith>",
    },
    "magnetic": {
        "code": "m",
        "format": "TRm",
        "description": "Query magnetic encoder position (LuftBlickTR1)",
        "parameters": [],
        "response": "TRh<azimuth>,<zenith>",
    },
}

# Motor alarm commands
MOTOR_ALARM_COMMANDS = {
    "zenith_alarm": {
        "format": "MZa?",
        "description": "Query zenith motor alarm",
        "response": "Alarm Code = N or MZ<error_code>",
    },
    "azimuth_alarm": {
        "format": "MAa?",
        "description": "Query azimuth motor alarm",
        "response": "Alarm Code = N or MA<error_code>",
    },
}
```

### 3.6 Position Conversion

```python
def degrees_to_steps(degrees: float, degrees_per_step: float, 
                     home_position: float) -> int:
    """
    Convert degrees to tracker steps.
    
    Parameters:
        degrees: Angle in degrees
        degrees_per_step: Tracker resolution (typically 0.01°/step)
        home_position: Home angle in degrees
    
    Returns:
        Step position (integer)
    """
    return round((home_position - degrees) / degrees_per_step)

def steps_to_degrees(steps: int, degrees_per_step: float,
                     home_position: float) -> float:
    """
    Convert tracker steps to degrees.
    """
    return home_position - (steps * degrees_per_step)

# Typical values:
# degrees_per_step = 0.01 (100 steps per degree)
# zenith_home = 0.0
# azimuth_home = 180.0
```

---

## 4. Filter Wheel Commands

### 4.1 Device IDs

| Filter Wheel | Device ID |
|--------------|-----------|
| Filter Wheel 1 | `F1` |
| Filter Wheel 2 | `F2` |

### 4.2 Commands

| Command | Format | Description | Response |
|---------|--------|-------------|----------|
| Set Position | `F1<1-9>` or `F2<1-9>` | Move to position 1-9 | `F10\n` or `F20\n` (success) |
| Reset | `F1r` or `F2r` | Reset filter wheel | `F10\n` or `F20\n` (success) |

```
# Set Filter Wheel 1 to position 5
Send:    "F15\r"
Receive: "F10\n"  # Success

# Set Filter Wheel 2 to position 3
Send:    "F23\r"
Receive: "F20\n"  # Success

# Reset Filter Wheel 1
Send:    "F1r\r"
Receive: "F10\n"  # Success

# Reset Filter Wheel 2
Send:    "F2r\r"
Receive: "F20\n"  # Success

# Error response example
Send:    "F15\r"
Receive: "F13\n"  # Error code 3: Cannot find filterwheel mirror
```

### 4.3 Filter Wheel Command Summary

```python
FILTER_WHEEL_COMMANDS = {
    "set_position": {
        "format": "{device_id}{position}",
        "device_ids": ["F1", "F2"],
        "positions": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "description": "Move filter wheel to position",
        "response": "{device_id}0 (success) or {device_id}<error_code>",
    },
    "reset": {
        "format": "{device_id}r",
        "device_ids": ["F1", "F2"],
        "description": "Reset filter wheel to home position",
        "response": "{device_id}0 (success) or {device_id}<error_code>",
    },
}

# Valid filter names for each position
VALID_FILTERS = [
    "OPAQUE",                    # Blocks all light
    "OPEN", "DIFF",              # Open/Diffuser
    "U340", "U340+DIFF",         # UV filter
    "BP300", "BP300+DIFF",       # Bandpass 300nm
    "LPNIR", "LPNIR+DIFF",       # Long-pass NIR
    "ND1", "ND2", "ND3", "ND4", "ND5",  # Neutral density 1-5
    # ND0.1 through ND5.0 (0.1 increments)
    # DIFF1 through DIFF5
    # FILTER1 through FILTER9
    # POL0 through POL359 (polarizer angles)
]
```

---

## 5. Shadowband Commands

### 5.1 Device ID: `SB`

### 5.2 Commands

| Command | Format | Description | Response |
|---------|--------|-------------|----------|
| Move | `SBm<position>` | Move to step position | `SB0\n` (success) |
| Reset | `SBr` | Reset shadowband | `SB0\n` (success) |

```
# Move shadowband to position 500
Send:    "SBm500\r"
Receive: "SB0\n"  # Success

# Move shadowband to position -300
Send:    "SBm-300\r"
Receive: "SB0\n"  # Success

# Reset shadowband
Send:    "SBr\r"
Receive: "SB0\n"  # Success
```

### 5.3 Shadowband Position Conversion

```python
def shadowband_angle_to_position(angle_deg: float, 
                                  resolution: float,
                                  ratio: float) -> int:
    """
    Convert shadowband angle to step position.
    
    Parameters:
        angle_deg: Relative shadowband angle in degrees
        resolution: Degrees per step
        ratio: Shadowband offset / radius ratio
    
    Returns:
        Step position (integer, typically -1000 to 1000)
    """
    import math
    delta = math.asin(math.sin(angle_deg * math.pi / 180) * ratio) * 180 / math.pi
    alfa = angle_deg - delta
    return int(round((alfa + 90) / resolution))

def position_to_shadowband_angle(position: int,
                                  resolution: float,
                                  ratio: float) -> float:
    """
    Convert step position to shadowband angle.
    """
    import math
    alfa = position * resolution - 90
    xq = 1 + ratio**2 - 2 * ratio * math.cos(alfa * math.pi / 180)
    sbeta = math.sin(alfa * math.pi / 180) / (xq ** 0.5)
    sbangle = math.asin(sbeta) * 180 / math.pi
    if xq > (1 - ratio**2):
        sbangle = 180 - sbangle
    if sbangle > 180:
        sbangle -= 360
    return sbangle
```

---

## 6. Temperature Controller Commands

### 6.1 TETech1 Protocol (16-bit)

#### 6.1.1 Connection Test

```
Send:    "*0060\r"
Receive: "<device_id>^"
```

#### 6.1.2 Command Format

```
Format: "*<command><hex_value><checksum>\r"
Response: "<hex_value><checksum>^" or "XXXX60^" (error)
```

#### 6.1.3 TETech1 Commands

| Parameter | Write Command | Read Command | Factor |
|-----------|--------------|--------------|--------|
| Set Temperature | `1c` | `5065` | 10 |
| Proportional Bandwidth | `1d` | `5166` | 10 |
| Integral Gain | `1e` | `5267` | 100 |
| Enable Output | `30` | - | 1 |
| Control Sensor Temp | - | `0161` | 10 |
| Secondary Sensor Temp | - | `0464` | 10 |

```python
# TETech1 Write Example: Set temperature to 25.0°C
# Value = 25.0 * 10 = 250 = 0x00FA
# Command: "*1c00FA<checksum>\r"

def tetech1_set_temperature(temp_celsius: float) -> str:
    """Generate TETech1 set temperature command."""
    value = int(temp_celsius * 10)
    hex_value = format(value & 0xFFFF, '04x')
    cmd = f"1c{hex_value}"
    checksum = format(sum(ord(c) for c in cmd) % 256, '02x')
    return f"*{cmd}{checksum}"

# TETech1 Read Example: Read control sensor temperature
# Command: "*5065\r"
# Response: "00FA3A^" -> 0x00FA = 250 -> 25.0°C
```

### 6.2 TETech2 Protocol (32-bit)

#### 6.2.1 Connection Test

```
Send:    "*00430000000047\r"
Receive: "<device_id>^"
```

#### 6.2.2 TETech2 Commands

| Parameter | Write Command | Read Command | Factor |
|-----------|--------------|--------------|--------|
| Set Temperature | `1c` | `00500000000045` | 100 |
| Proportional Bandwidth | `1d` | `00510000000046` | 100 |
| Integral Gain | `1e` | `00520000000047` | 100 |
| Enable Output | `2d` | - | 1 |
| Control Sensor Temp | - | `00010000000041` | 100 |
| Secondary Sensor Temp | - | `00060000000046` | 100 |

```python
# TETech2 Write Example: Set temperature to 25.0°C
# Value = 25.0 * 100 = 2500 = 0x000009C4
# Command: "*001c000009C4<checksum>\r"

def tetech2_set_temperature(temp_celsius: float) -> str:
    """Generate TETech2 set temperature command."""
    value = int(temp_celsius * 100)
    hex_value = format(value & 0xFFFFFFFF, '08x')
    cmd = f"001c{hex_value}"
    checksum = format(sum(ord(c) for c in cmd) % 256, '02x')
    return f"*{cmd}{checksum}"
```

### 6.3 Hex Conversion Functions

```python
def dec2hex(value: int, nbits: int = 16) -> str:
    """
    Convert decimal to hex string for TETech commands.
    
    Handles negative values using two's complement.
    """
    vmax = 2 ** nbits
    nchar = nbits // 4
    if value < 0:
        hex_value = hex(vmax + value)[2:]
    else:
        hex_value = hex(abs(value))[2:]
    # Remove 'L' suffix if present (Python 2 legacy)
    hex_value = hex_value.rstrip('L')
    return hex_value.zfill(nchar)

def get_checksum(hex_string: str) -> str:
    """Calculate checksum for TETech commands."""
    total = sum(ord(c) for c in hex_string)
    return format(total % 256, '02x')

def hex2dec(hex_string: str, nbits: int = 16) -> float:
    """Convert hex response to decimal value."""
    value = int(hex_string, 16)
    # Check if negative (first nibble > 7)
    if int(hex_string[0], 16) > 7:
        value = value - (2 ** nbits)
    return value
```

### 6.4 Temperature Controller Command Summary

```python
TETECH_COMMANDS = {
    "TETech1": {
        "connection_test": "*0060",
        "end_char": "^",
        "nbits": 16,
        "write": {
            "ST": {"cmd": "1c", "factor": 10},   # Set temperature
            "BW": {"cmd": "1d", "factor": 10},   # Proportional bandwidth
            "IG": {"cmd": "1e", "factor": 100},  # Integral gain
            "EO": {"cmd": "30", "factor": 1},    # Enable output
        },
        "read": {
            "ST": {"cmd": "5065", "factor": 10},   # Set temperature
            "BW": {"cmd": "5166", "factor": 10},   # Proportional bandwidth
            "IG": {"cmd": "5267", "factor": 100},  # Integral gain
            "T1": {"cmd": "0161", "factor": 10},   # Control sensor temp
            "T2": {"cmd": "0464", "factor": 10},   # Secondary sensor temp
        },
        "error_response": "XXXX60",
    },
    "TETech2": {
        "connection_test": "*00430000000047",
        "end_char": "^",
        "nbits": 32,
        "write": {
            "ST": {"cmd": "1c", "factor": 100},
            "BW": {"cmd": "1d", "factor": 100},
            "IG": {"cmd": "1e", "factor": 100},
            "EO": {"cmd": "2d", "factor": 1},
        },
        "read": {
            "ST": {"cmd": "00500000000045", "factor": 100},
            "BW": {"cmd": "00510000000046", "factor": 100},
            "IG": {"cmd": "00520000000047", "factor": 100},
            "T1": {"cmd": "00010000000041", "factor": 100},
            "T2": {"cmd": "00060000000046", "factor": 100},
        },
        "error_response": "XXXXXXXXc0",
    },
}
```

---

## 7. Humidity Sensor Commands

### 7.1 HDC2080EVM Protocol

| Command | Send | Response | Description |
|---------|------|----------|-------------|
| ID | `?` | `S,HDC2080EVM,part,` | Query device ID |
| Initialize | `4` | `stream stop` | Stop data streaming |
| Temperature | `1` | 4-char hex | Read temperature |
| Humidity | `2` | 4-char hex | Read humidity |

### 7.2 Command Details

```
# Query device ID
Send:    "?\r"
Receive: "S,HDC2080EVM,part,\r\n"

# Initialize (stop streaming)
Send:    "4\r"
Receive: "stream stop\r\n"

# Read temperature
Send:    "1\r"
Receive: "ABCD\r\n"  # 4-character hex value

# Read humidity
Send:    "2\r"
Receive: "EFGH\r\n"  # 4-character hex value
```

### 7.3 Data Conversion

```python
def hdc2080_parse_humidity(hex_response: str) -> float:
    """
    Parse HDC2080EVM humidity response.
    
    Response is 4-char hex in little-endian format.
    Humidity = (value / 2^16) * 100 [%]
    """
    # Swap bytes (little-endian)
    hex_value = hex_response[-2:] + hex_response[:2]
    int_value = int(hex_value, 16)
    humidity = (float(int_value) / (2**16)) * 100
    return round(humidity, 2)

def hdc2080_parse_temperature(hex_response: str) -> float:
    """
    Parse HDC2080EVM temperature response.
    
    Response is 4-char hex in little-endian format.
    Temperature = (value / 2^16) * 165 - 40 [°C]
    """
    # Swap bytes (little-endian)
    hex_value = hex_response[-2:] + hex_response[:2]
    int_value = int(hex_value, 16)
    temperature = (float(int_value) / (2**16)) * 165 - 40
    return round(temperature, 2)

# Example:
# Humidity response: "8000" -> swap -> "0080" -> 128 -> (128/65536)*100 = 0.20%
# Temperature response: "6666" -> swap -> "6666" -> 26214 -> (26214/65536)*165-40 = 25.99°C
```

### 7.4 Humidity Sensor Command Summary

```python
HDC2080EVM_COMMANDS = {
    "id": {
        "send": "?",
        "end_char": "\r",
        "response_end_char": "\r\n",
        "expected_response": "HDC2080EVM",
        "description": "Query device ID",
    },
    "initialize": {
        "send": "4",
        "end_char": "\r",
        "response_end_char": "\r\n",
        "expected_response": "stream stop",
        "description": "Stop data streaming",
    },
    "temperature": {
        "send": "1",
        "end_char": "\r",
        "response_end_char": "\r\n",
        "conversion": "(value / 2^16) * 165 - 40",
        "unit": "°C",
        "description": "Read temperature",
    },
    "humidity": {
        "send": "2",
        "end_char": "\r",
        "response_end_char": "\r\n",
        "conversion": "(value / 2^16) * 100",
        "unit": "%",
        "description": "Read relative humidity",
    },
}
```

---

## 8. Positioning System Commands

### 8.1 Novatel GPS/Gyroscope

#### 8.1.1 Commands

| Command | Description | Response |
|---------|-------------|----------|
| `unlogall` | Clear all log commands | `\r\n<OK` |
| `log inspva once` | Request single position | INSPVA data |
| `log inspva ontime N` | Start logging every N seconds | `\r\n<OK` |

```
# Clear logs
Send:    "unlogall\r"
Receive: "\r\n<OK\r\n[USB1]"

# Request single position
Send:    "log inspva once\r"
Receive: "\r\n<OK\r\n[USB1]"
         (followed by INSPVA data)

# Start continuous logging (1 second interval)
Send:    "log inspva ontime 1\r"
Receive: "\r\n<OK\r\n[USB1]"
```

#### 8.1.2 INSPVA Response Format

```
<INSPVA USB1 0 95.0 FINESTEERING week seconds status ...
< week seconds latitude longitude altitude vn ve vu roll pitch yaw status

Example:
<INSPVA USB1 0 95.0 FINESTEERING 1918 131036.000 20000000 0000 312
< 1918 131036.002500000 52.458109776 13.310504415 112.364119180 
  0.003697356 0.001826098 0.000169055 0.188712512 -0.332215923 
  350.645755624 INS_SOLUTION_GOOD

Fields:
- week: GPS week number
- seconds: Seconds into week
- latitude: Degrees
- longitude: Degrees
- altitude: Meters above ellipsoid
- vn, ve, vu: Velocity north, east, up (m/s)
- roll: East-West tilt (degrees)
- pitch: North-South tilt (degrees)
- yaw: Azimuth (degrees)
- status: INS_SOLUTION_GOOD or INS_ALIGNMENT_COMPLETE
```

### 8.2 GlobalSat GPS

#### 8.2.1 Configuration Commands

```
# Disable automatic messages
"$PSRF103,04,00,00,01*20\r\n"  # Disable RMC
"$PSRF103,02,00,00,01*26\r\n"  # Disable GSA
"$PSRF103,03,00,00,01*27\r\n"  # Disable GSV
"$PSRF103,00,00,00,01*24\r\n"  # Disable GGA
```

#### 8.2.2 Query Position

```
Send:    "$PSRF103,00,01,00,01*25\r\n"
Receive: "$GPGGA,170145.000,3859.3500,N,07652.8949,W,1,07,1.7,42.0,M,-33.5,M,,0000*5C\r\n"
```

#### 8.2.3 GPGGA Response Format

```
$GPGGA,time,lat,N/S,lon,E/W,quality,sats,hdop,alt,M,geoid,M,age,refid*checksum

Fields:
- time: HHMMSS.sss (UTC)
- lat: DDMM.MMMM (degrees + minutes)
- N/S: North or South
- lon: DDDMM.MMMM (degrees + minutes)
- E/W: East or West
- quality: 0=invalid, 1=GPS fix, 2=DGPS fix
- sats: Number of satellites
- hdop: Horizontal dilution of precision
- alt: Altitude above mean sea level (meters)
- geoid: Geoid separation (meters)
- age: Age of differential data
- refid: Reference station ID
- checksum: XOR checksum
```

### 8.3 GPS Coordinate Conversion

```python
def nmea_to_decimal(coord: str, direction: str) -> float:
    """
    Convert NMEA coordinate to decimal degrees.
    
    NMEA format: DDMM.MMMM (lat) or DDDMM.MMMM (lon)
    """
    if len(coord) == 0:
        return 0.0
    
    # Split degrees and minutes
    if direction in ['N', 'S']:
        degrees = float(coord[:2])
        minutes = float(coord[2:])
    else:  # E, W
        degrees = float(coord[:3])
        minutes = float(coord[3:])
    
    decimal = degrees + minutes / 60.0
    
    if direction in ['S', 'W']:
        decimal = -decimal
    
    return decimal

# Example:
# "3859.3500", "N" -> 38 + 59.35/60 = 38.9892°N
# "07652.8949", "W" -> -(76 + 52.8949/60) = -76.8816°W
```

### 8.4 Positioning System Command Summary

```python
GPS_COMMANDS = {
    "Novatel": {
        "end_char": "\r",
        "response_end_char": "\r\n[USB1]",
        "commands": {
            "clear_logs": "unlogall",
            "read_once": "log inspva once",
            "start_logging": "log inspva ontime {interval}",
        },
        "response_markers": {
            "success": "INS_SOLUTION_GOOD",
            "alignment": "INS_ALIGNMENT_COMPLETE",
        },
    },
    "GlobalSat": {
        "end_char": "\r\n",
        "response_end_char": "\r\n",
        "commands": {
            "disable_rmc": "$PSRF103,04,00,00,01*20",
            "disable_gsa": "$PSRF103,02,00,00,01*26",
            "disable_gsv": "$PSRF103,03,00,00,01*27",
            "disable_gga": "$PSRF103,00,00,00,01*24",
            "query_gga": "$PSRF103,00,01,00,01*25",
        },
        "response_marker": "$GPGGA",
    },
}
```

---

## 9. Error Codes Reference

### 9.1 Head Sensor / Tracker Error Codes

| Code | Message | Description |
|------|---------|-------------|
| 0 | OK | Success |
| 1 | Cannot read from head sensor microcontroller memory | Memory read error |
| 2 | Wrong tracker echo response | Tracker communication error |
| 3 | Cannot find filterwheel mirror | Filter wheel error |
| 4 | Cannot write to head sensor microcontroller memory | Memory write error |
| 5 | Cannot read from tracker driver register | Driver error |
| 6 | Cannot write to tracker driver register | Driver error |
| 7 | Cannot read sensor data | Sensor error |
| 8 | Cannot reset head sensor software | Reset failed |
| 9 | Tracker did not reset power | Power reset failed |
| 99 | Low level serial communication error | Communication failure |

### 9.2 LuftBlickTR1 Motor Alarm Codes

| Code | Message |
|------|---------|
| 0 | OK (No alarm) |
| 10 | Excessive position deviation |
| 26 | Motor overheating |
| 30 | Load exceeding maximum configured torque |
| 42 | Absolute position sensor error at power on |
| 72 | Wrap setting parameter error |
| 84 | RS-485 communication error |

### 9.3 Humidity Sensor Error Codes

| Code | Message |
|------|---------|
| 0 | OK |
| 1 | Wrong ID response |
| 2 | Could not initialize device |
| 3 | Could not understand humidity reading |
| 4 | Could not understand temperature reading |
| 99 | Low level serial communication error |

### 9.4 Error Code Implementation

```python
# Complete error code dictionary
ERROR_CODES = {
    "head_sensor": {
        0: "OK",
        1: "Cannot read from head sensor microcontroller memory",
        2: "Wrong tracker echo response",
        3: "Cannot find filterwheel mirror",
        4: "Cannot write to head sensor microcontroller memory",
        5: "Cannot read from tracker driver register",
        6: "Cannot write to tracker driver register",
        7: "Cannot read sensor data",
        8: "Cannot reset head sensor software",
        9: "Tracker did not reset power",
        99: "Low level serial communication error",
    },
    "motor_alarm": {
        0: "OK",
        10: "Excessive position deviation",
        26: "Motor overheating",
        30: "Load exceeding maximum configured torque",
        42: "Absolute position sensor error at power on",
        72: "Wrap setting parameter error",
        84: "RS-485 communication error",
    },
    "humidity_sensor": {
        0: "OK",
        1: "Wrong ID response",
        2: "Could not initialize device",
        3: "Could not understand humidity reading",
        4: "Could not understand temperature reading",
        99: "Low level serial communication error",
    },
}

def get_error_message(device: str, code: int) -> str:
    """Get human-readable error message."""
    if device in ERROR_CODES and code in ERROR_CODES[device]:
        return ERROR_CODES[device][code]
    return f"Unknown error code: {code}"
```

---

## 10. Response Parsing Patterns

### 10.1 Expected Answer Format Specification

The Blick system uses a sophisticated pattern matching system for response validation:

```python
# Pattern specification format:
# expans = [device_id, [valid_codes]]
#
# device_id: String that must be at the beginning of the response
# valid_codes: List of valid response patterns

# Pattern element types:
# - String: Exact match required
# - ["I", min, max, separator]: Integer number
# - ["F", min, max, separator]: Float number
# - ["H<n>", "", "", separator]: Hex string with n characters
# - ["S", match_string, match_type, ""]: String match
#   - match_type: "exact", "start", "end", "part", "undefined"
```

### 10.2 Common Response Patterns

```python
# Tracker position response: "TRh-1200,3100\n"
TRACKER_POSITION_PATTERN = [
    "TR",  # Device ID
    [
        ["0"],  # Simple success: "TR0"
        ["1"], ["2"], ["3"], ["4"], ["5"], ["6"], ["7"], ["8"], ["9"],  # Error codes
        ["h", ["I", "", "", ","], ["I", "", "", []]]  # Position: "TRh<azi>,<zen>"
    ]
]

# Sensor reading response: "HT!23456\n"
SENSOR_READING_PATTERN = [
    "HT",  # Device ID
    [
        ["0"], ["1"], ["2"], ["3"], ["4"], ["5"], ["6"], ["7"], ["8"], ["9"],  # Error codes
        ["!", ["F", "", "", []]]  # Reading: "HT!<value>"
    ]
]

# Filter wheel response: "F10\n"
FILTER_WHEEL_PATTERN = [
    "F1",  # Device ID (or "F2")
    [
        ["0"],  # Success
        ["1"], ["2"], ["3"], ["4"], ["5"], ["6"], ["7"], ["8"], ["9"]  # Error codes
    ]
]

# TETech response: "00FA3A^"
TETECH_PATTERN = [
    "",  # No device ID prefix
    [
        [["H6", "", "", []]],  # 6-char hex (4 data + 2 checksum)
        ["XXXX60"]  # Error response
    ]
]

# HDC2080EVM ID response
HDC2080_ID_PATTERN = [
    "",
    [
        [["S", "HDC2080EVM", "part", ""]],
        [["S", "9 : debug", "end", ""]]
    ]
]
```

### 10.3 Response Parsing Implementation

```python
def parse_response(raw_response: str, pattern: list, end_char: str = "\n") -> tuple:
    """
    Parse serial response against expected pattern.
    
    Returns:
        (success: bool, parsed_data: any, error: str)
    """
    # Split by end character
    parts = raw_response.split(end_char)
    if len(parts) < 2:
        return False, None, "No end character found"
    
    response = parts[0]
    device_id = pattern[0]
    
    # Check device ID prefix
    if not response.startswith(device_id):
        return False, None, f"Expected device ID '{device_id}'"
    
    # Extract code part
    code = response[len(device_id):]
    
    # Try each valid code pattern
    for valid_code in pattern[1]:
        success, data = try_match_pattern(code, valid_code)
        if success:
            return True, data, "OK"
    
    return False, None, "No matching pattern found"

def try_match_pattern(code: str, pattern: list) -> tuple:
    """Try to match code against a single pattern."""
    result = []
    pos = 0
    
    for element in pattern:
        if isinstance(element, str):
            # Exact string match
            if not code[pos:].startswith(element):
                return False, None
            pos += len(element)
            result.append(element)
        elif isinstance(element, list):
            # Typed value
            value_type = element[0]
            if value_type == "I":
                # Integer
                value, new_pos = parse_integer(code, pos, element[3])
                if value is None:
                    return False, None
                result.append(value)
                pos = new_pos
            elif value_type == "F":
                # Float
                value, new_pos = parse_float(code, pos, element[3])
                if value is None:
                    return False, None
                result.append(value)
                pos = new_pos
            elif value_type.startswith("H"):
                # Hex string
                n_chars = int(value_type[1:])
                hex_str = code[pos:pos + n_chars]
                if len(hex_str) != n_chars:
                    return False, None
                result.append(hex_str)
                pos += n_chars
            elif value_type == "S":
                # String match
                match_str = element[1]
                match_type = element[2]
                if match_type == "exact" and code[pos:] != match_str:
                    return False, None
                elif match_type == "start" and not code[pos:].startswith(match_str):
                    return False, None
                elif match_type == "end" and not code.endswith(match_str):
                    return False, None
                elif match_type == "part" and match_str not in code[pos:]:
                    return False, None
                result.append(code[pos:])
                pos = len(code)
    
    return True, result
```

---

## 11. Timing Parameters

### 11.1 Standard Timeouts

| Parameter | Value | Description |
|-----------|-------|-------------|
| Command timeout | 1.0s | Standard command response time |
| Movement timeout | 3.0s | Tracker movement commands |
| Reset timeout | 5.0s | Device reset commands |
| Power cycle timeout | 10.0s | Power reset commands |
| Sensor reading timeout | 2.0s | Sensor data acquisition |
| Buffer read timeout | 0.5s | Serial buffer operations |

### 11.2 Retry Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| Max unexpected answers | 3 | Retry count for unexpected responses |
| Max recovery level | 18 | Maximum recovery attempts |
| Inter-command delay | 0.1s | Delay between consecutive commands |

### 11.3 Timing Configuration

```python
TIMING_CONFIG = {
    "maxwaits": {
        0: 0.1,    # Inter-command delay
        1: 1.0,    # Standard command timeout
        2: 2.0,    # Position query timeout
        3: 3.0,    # Movement command timeout
        4: 5.0,    # Soft reset timeout
        5: 5.0,    # Movement completion wait
        6: 10.0,   # Data arrival margin
        9: 2.0,    # Port detection timeout
        13: 0.5,   # DTR toggle delay
        16: 2.0,   # Recovery wait
        17: 1.0,   # Temperature controller wait
        18: 10.0,  # Power reset wait (standard tracker)
        26: 30.0,  # Maximum measurement duration (simulation)
        27: 3.0,   # Sensor reading timeout
        28: 15.0,  # LuftBlickTR1 soft reset wait
        29: 30.0,  # LuftBlickTR1 power reset wait
        -1: 0.01,  # Minimum delay
    },
    "tperiods": {
        4: 100,    # Tracking update interval (ms)
        6: 100,    # Serial update timer (ms)
        -1: 50,    # Minimum timer period (ms)
    },
    "max_serial_iterations": 100,
    "max_serial_chars": 1024,
    "max_unexpected_answers": 3,
}
```

---

## 12. Code Examples

### 12.1 Complete Head Sensor Connection

```python
import serial
import time

class HeadSensorConnection:
    def __init__(self, port: str, baudrate: int = 9600):
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=0,
            writeTimeout=20
        )
        
    def send_command(self, command: str, end_char: str = '\r') -> str:
        """Send command and get response."""
        # Clear buffer
        self.ser.flushInput()
        
        # Send command
        self.ser.write((command + end_char).encode())
        
        # Wait for response
        time.sleep(0.5)
        response = ""
        while self.ser.in_waiting:
            response += self.ser.read(self.ser.in_waiting).decode()
            time.sleep(0.1)
        
        return response
    
    def get_id(self) -> str:
        """Get device identification."""
        response = self.send_command("?")
        return response.strip()
    
    def get_temperature(self) -> float:
        """Get head sensor temperature."""
        response = self.send_command("HTt?")
        # Parse response: "HT!NNNNN\n"
        if "!" in response:
            value_str = response.split("!")[1].strip()
            return float(value_str) / 100.0
        return -999.0
    
    def move_tracker(self, zenith_steps: int, azimuth_steps: int) -> bool:
        """Move tracker to position."""
        command = f"TRb{azimuth_steps},{zenith_steps}"
        response = self.send_command(command)
        return "TR0" in response
    
    def get_tracker_position(self) -> tuple:
        """Get current tracker position."""
        response = self.send_command("TRw")
        # Parse response: "TRh<azi>,<zen>\n"
        if "TRh" in response:
            parts = response.replace("TRh", "").strip().split(",")
            return int(parts[0]), int(parts[1])
        return None, None
    
    def set_filter(self, wheel: int, position: int) -> bool:
        """Set filter wheel position."""
        command = f"F{wheel}{position}"
        response = self.send_command(command)
        return f"F{wheel}0" in response
    
    def close(self):
        """Close connection."""
        self.ser.close()

# Usage example
if __name__ == "__main__":
    hs = HeadSensorConnection("COM3")
    
    print(f"Device ID: {hs.get_id()}")
    print(f"Temperature: {hs.get_temperature()}°C")
    
    # Move tracker
    hs.move_tracker(3000, -1200)
    time.sleep(5)
    
    zen, azi = hs.get_tracker_position()
    print(f"Position: zenith={zen}, azimuth={azi}")
    
    # Set filter
    hs.set_filter(1, 5)
    
    hs.close()
```

### 12.2 Temperature Controller Communication

```python
class TETechController:
    def __init__(self, port: str, controller_type: str = "TETech1"):
        self.ser = serial.Serial(
            port=port,
            baudrate=9600,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=0
        )
        self.type = controller_type
        self.nbits = 16 if controller_type == "TETech1" else 32
        self.factor = 10 if controller_type == "TETech1" else 100
    
    def _checksum(self, s: str) -> str:
        return format(sum(ord(c) for c in s) % 256, '02x')
    
    def _dec2hex(self, value: int) -> str:
        nchar = self.nbits // 4
        if value < 0:
            value = (2 ** self.nbits) + value
        return format(value, f'0{nchar}x')
    
    def _hex2dec(self, hex_str: str) -> float:
        value = int(hex_str, 16)
        if int(hex_str[0], 16) > 7:
            value = value - (2 ** self.nbits)
        return value / self.factor
    
    def send_command(self, command: str) -> str:
        self.ser.flushInput()
        self.ser.write((command + '\r').encode())
        time.sleep(0.5)
        response = ""
        while self.ser.in_waiting:
            response += self.ser.read(self.ser.in_waiting).decode()
            time.sleep(0.1)
        return response.rstrip('^')
    
    def set_temperature(self, temp: float) -> bool:
        value = int(temp * self.factor)
        hex_value = self._dec2hex(value)
        
        if self.type == "TETech1":
            cmd = f"1c{hex_value}"
        else:
            cmd = f"001c{hex_value}"
        
        checksum = self._checksum(cmd)
        response = self.send_command(f"*{cmd}{checksum}")
        
        return hex_value in response
    
    def get_temperature(self) -> float:
        if self.type == "TETech1":
            response = self.send_command("*0161")
        else:
            response = self.send_command("*00010000000041")
        
        # Extract hex value (remove checksum)
        hex_value = response[:-2] if len(response) > 2 else "0000"
        return self._hex2dec(hex_value)
    
    def close(self):
        self.ser.close()

# Usage
tc = TETechController("COM4", "TETech1")
tc.set_temperature(25.0)
print(f"Temperature: {tc.get_temperature()}°C")
tc.close()
```

### 12.3 GPS Position Reading

```python
class GlobalSatGPS:
    def __init__(self, port: str):
        self.ser = serial.Serial(
            port=port,
            baudrate=9600,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=1
        )
    
    def configure(self):
        """Disable automatic messages."""
        commands = [
            "$PSRF103,04,00,00,01*20",
            "$PSRF103,02,00,00,01*26",
            "$PSRF103,03,00,00,01*27",
            "$PSRF103,00,00,00,01*24",
        ]
        for cmd in commands:
            self.ser.write((cmd + '\r\n').encode())
            time.sleep(0.2)
    
    def _nmea_to_decimal(self, coord: str, direction: str) -> float:
        if not coord:
            return 0.0
        
        if direction in ['N', 'S']:
            degrees = float(coord[:2])
            minutes = float(coord[2:])
        else:
            degrees = float(coord[:3])
            minutes = float(coord[3:])
        
        decimal = degrees + minutes / 60.0
        if direction in ['S', 'W']:
            decimal = -decimal
        
        return decimal
    
    def get_position(self) -> dict:
        """Query GPS position."""
        self.ser.flushInput()
        self.ser.write(b"$PSRF103,00,01,00,01*25\r\n")
        
        time.sleep(1)
        response = self.ser.read(256).decode()
        
        if "$GPGGA" not in response:
            return {"error": "No GPS fix"}
        
        # Parse GPGGA
        gga = response.split("$GPGGA")[1].split(",")
        
        quality = int(gga[6]) if gga[6] else 0
        if quality == 0:
            return {"error": "No GPS fix", "quality": 0}
        
        return {
            "latitude": self._nmea_to_decimal(gga[2], gga[3]),
            "longitude": self._nmea_to_decimal(gga[4], gga[5]),
            "altitude": float(gga[9]) if gga[9] else 0.0,
            "satellites": int(gga[7]) if gga[7] else 0,
            "quality": quality,
        }
    
    def close(self):
        self.ser.close()

# Usage
gps = GlobalSatGPS("COM5")
gps.configure()
position = gps.get_position()
print(f"Lat: {position['latitude']}, Lon: {position['longitude']}")
gps.close()
```

---

## Appendix: Quick Command Reference Card

### Head Sensor
| Command | Action |
|---------|--------|
| `?` | Get ID |
| `HTt?` | Temperature |
| `HTh?` | Humidity |
| `HTp?` | Pressure |

### Tracker
| Command | Action |
|---------|--------|
| `TRp<N>` | Pan to N |
| `TRt<N>` | Tilt to N |
| `TRb<A>,<Z>` | Move both |
| `TRw` | Get position |
| `TRr` | Reset |
| `TRs` | Power reset |

### Filter Wheel
| Command | Action |
|---------|--------|
| `F1<1-9>` | Set FW1 |
| `F2<1-9>` | Set FW2 |
| `F1r` | Reset FW1 |
| `F2r` | Reset FW2 |

### Temperature Controller (TETech1)
| Command | Action |
|---------|--------|
| `*0060` | ID query |
| `*1c<hex>` | Set temp |
| `*0161` | Read temp |

### Humidity Sensor (HDC2080)
| Command | Action |
|---------|--------|
| `?` | Get ID |
| `4` | Initialize |
| `1` | Temperature |
| `2` | Humidity |

### GPS (GlobalSat)
| Command | Action |
|---------|--------|
| `$PSRF103,00,01,00,01*25` | Query GGA |

---

*This document provides the complete command reference for implementing the SciGlob Library. Use in conjunction with `SCIGLOB_LIBRARY_SPEC.md` for full implementation details.*

*Document Version: 1.0*
*Last Updated: 2024*

