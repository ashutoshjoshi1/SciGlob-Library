# SciGlob Library

**Python library for controlling SciGlob scientific instrumentation**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

SciGlob Library provides a unified Python interface for controlling scientific instruments used in atmospheric monitoring systems, including:

| Component | Description | Protocol |
|-----------|-------------|----------|
| **Head Sensor** | Main communication hub (SciGlobHSN1, SciGlobHSN2) | RS-232 |
| **Tracker** | Azimuth/Zenith motor control (Directed Perceptions, LuftBlickTR1) | via Head Sensor |
| **Filter Wheels** | FW1, FW2 with 9 positions each | via Head Sensor |
| **Shadowband** | Shadowband arm positioning | via Head Sensor |
| **Temperature Controller** | TETech1 (16-bit), TETech2 (32-bit) | RS-232 |
| **Humidity Sensor** | HDC2080EVM | RS-232 |
| **GPS/Positioning** | GlobalSat (GPS), Novatel (GPS+Gyro) | RS-232 |

---

## Installation

### From Source

```bash
git clone https://github.com/SciGlob/SciGlob-Library.git
cd SciGlob-Library
pip install -e .
```

### With Development Dependencies

```bash
pip install -e ".[dev]"
```

---

## Quick Start

### Head Sensor with Tracker & Filter Wheels

```python
from sciglob import HeadSensor

with HeadSensor(port="/dev/ttyUSB0") as hs:
    # Get device info
    print(f"Device: {hs.device_id}")
    print(f"Type: {hs.sensor_type}")
    
    # Read internal sensors (SciGlobHSN2 only)
    if hs.sensor_type == "SciGlobHSN2":
        print(f"Temperature: {hs.get_temperature()}°C")
        print(f"Humidity: {hs.get_humidity()}%")
        print(f"Pressure: {hs.get_pressure()} mbar")
    
    # Control tracker (azimuth/zenith motors)
    tracker = hs.tracker
    tracker.move_to(zenith=45.0, azimuth=180.0)
    print(f"Position: {tracker.get_position()}")
    
    # Control filter wheel
    fw1 = hs.filter_wheel_1
    fw1.set_filter("OPEN")
    print(f"Current filter: {fw1.current_filter}")
```

### Tracker Commands

```python
# Movement in degrees
tracker.move_to(zenith=45.0, azimuth=180.0)  # Absolute position
tracker.move_relative(delta_zenith=10.0, delta_azimuth=-20.0)  # Relative
tracker.pan(azimuth=90.0)   # Azimuth only
tracker.tilt(zenith=30.0)   # Zenith only

# Movement in steps
tracker.move_to_steps(zenith_steps=4500, azimuth_steps=-1200)

# Get position
zenith, azimuth = tracker.get_position()       # In degrees
azi_steps, zen_steps = tracker.get_position_steps()  # In steps

# Special commands
tracker.home()          # Go to home position
tracker.park()          # Go to parking position
tracker.reset()         # Soft reset
tracker.power_reset()   # Power cycle

# LuftBlickTR1 specific
if tracker.is_luftblick:
    temps = tracker.get_motor_temperatures()
    alarms = tracker.get_motor_alarms()
    tracker.check_alarms()  # Raises exception if alarm present
```

### Filter Wheel Commands

```python
# Select by position (1-9)
fw1.set_position(5)

# Select by filter name
fw1.set_filter("U340")

# Get current state
print(fw1.position)       # Current position number
print(fw1.current_filter) # Current filter name

# Get filter configuration
print(fw1.get_filter_map())        # {1: "OPEN", 2: "U340", ...}
print(fw1.get_available_filters()) # ["OPEN", "U340", ...]

# Reset to home
fw1.reset()
```

### Temperature Controller

```python
from sciglob import TemperatureController

with TemperatureController(port="/dev/ttyUSB1", controller_type="TETech1") as tc:
    # Read temperature
    print(f"Current: {tc.get_temperature()}°C")
    print(f"Setpoint: {tc.get_setpoint()}°C")
    
    # Set temperature
    tc.set_temperature(25.0)
    
    # Control output
    tc.enable_output()
    tc.disable_output()
```

### Humidity Sensor

```python
from sciglob import HumiditySensor

with HumiditySensor(port="/dev/ttyUSB2") as hs:
    print(f"Temperature: {hs.get_temperature()}°C")
    print(f"Humidity: {hs.get_humidity()}%")
```

### GPS Positioning

```python
from sciglob import GlobalSatGPS, NovatelGPS

# Simple GPS
with GlobalSatGPS(port="/dev/ttyUSB3") as gps:
    pos = gps.get_position()
    print(f"Lat: {pos['latitude']}, Lon: {pos['longitude']}")

# GPS + Gyroscope
with NovatelGPS(port="/dev/ttyUSB4") as gps:
    pos = gps.get_position()
    orient = gps.get_orientation()
    print(f"Yaw: {orient['yaw']}°, Pitch: {orient['pitch']}°")
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Application                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SciGlob Library API                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │  Head   │ │ Tracker │ │ Filter  │ │  Temp   │ │  GPS    │   │
│  │ Sensor  │ │         │ │  Wheel  │ │ Control │ │         │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
│       │          │          │          │          │            │
│       └──────────┴──────────┘          │          │            │
│                  │                      │          │            │
└──────────────────┼──────────────────────┼──────────┼────────────┘
                   │                      │          │
                   ▼                      ▼          ▼
           ┌────────────┐          ┌────────────────────────┐
           │ Head Sensor│          │   Independent Devices  │
           │   RS-232   │          │       RS-232           │
           │  (9600 bd) │          │      (9600 bd)         │
           └────────────┘          └────────────────────────┘
```

---

## Device Commands Quick Reference

### Head Sensor
| Command | Response | Description |
|---------|----------|-------------|
| `?` | Device ID | Query identification |
| `HTt?` | `HT!<value>` | Temperature (÷100 = °C) |
| `HTh?` | `HT!<value>` | Humidity (÷1024 = %) |
| `HTp?` | `HT!<value>` | Pressure (÷100 = mbar) |

### Tracker
| Command | Response | Description |
|---------|----------|-------------|
| `TRp<steps>` | `TR0` | Pan (azimuth only) |
| `TRt<steps>` | `TR0` | Tilt (zenith only) |
| `TRb<azi>,<zen>` | `TR0` | Move both axes |
| `TRw` | `TRh<azi>,<zen>` | Query position |
| `TRr` | `TR0` | Soft reset |
| `TRs` | `TR0` | Power reset |

### Filter Wheel
| Command | Response | Description |
|---------|----------|-------------|
| `F1<1-9>` | `F10` | Set FW1 position |
| `F2<1-9>` | `F20` | Set FW2 position |
| `F1r` | `F10` | Reset FW1 |
| `F2r` | `F20` | Reset FW2 |

---

## Error Handling

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
    with HeadSensor(port="/dev/ttyUSB0") as hs:
        # This will raise PositionError if out of limits
        hs.tracker.move_to(zenith=100.0, azimuth=180.0)
        
except ConnectionError as e:
    print(f"Connection failed: {e}")
except PositionError as e:
    print(f"Position out of range: {e.position} not in [{e.min_pos}, {e.max_pos}]")
except MotorAlarmError as e:
    print(f"Motor alarm on {e.axis}: code {e.alarm_code}")
except TrackerError as e:
    print(f"Tracker error: {e}")
```

---

## Configuration

### Head Sensor Configuration

```python
hs = HeadSensor(
    port="/dev/ttyUSB0",
    baudrate=9600,
    tracker_type="LuftBlickTR1",     # or "Directed Perceptions"
    degrees_per_step=0.01,           # 100 steps per degree
    motion_limits=[0, 90, 0, 360],   # [zen_min, zen_max, azi_min, azi_max]
    home_position=[0.0, 180.0],      # [zenith_home, azimuth_home]
    fw1_filters=["OPEN", "U340", "BP300", "LPNIR", "ND1", "ND2", "ND3", "ND4", "OPAQUE"],
    fw2_filters=["OPEN", "DIFF", "U340+DIFF", ...],
)
```

---

## Logging

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("sciglob").setLevel(logging.DEBUG)

# Or for specific components
logging.getLogger("sciglob.Tracker").setLevel(logging.DEBUG)
logging.getLogger("sciglob.serial").setLevel(logging.DEBUG)
```

---

## Requirements

- Python 3.9+
- pyserial >= 3.5
- pyyaml >= 6.0

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Documentation

- [Architecture](ARCHITECTURE.md) - Detailed system architecture
- [Command Reference](SCIGLOB_COMMAND_REFERENCE.md) - Complete protocol documentation
- [Library Specification](SCIGLOB_LIBRARY_SPEC.md) - Full implementation specification

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest`
5. Submit a pull request
