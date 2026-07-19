# SciGlob Library

**Python library for controlling SciGlob scientific instrumentation**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

SciGlob Library provides a single, unified Python interface to **every** piece
of hardware in a SciGlob / Pandora-class instrument — talk to the instrument in
a few lines of code, without knowing wire protocols. Every device has a real
driver **and** a simulation twin, so tests and development run with no hardware.

| # | Subsystem | Class | Protocol | Extra |
|---|-----------|-------|----------|-------|
| 1 | **Head Sensor** (SciGlobHSN1/HSN2) | `HeadSensor` | RS-232 | — |
| 2 | **Tracker** via head sensor (Directed Perceptions, LuftBlickTR1) | `Tracker` | via Head Sensor | — |
| 3 | **Filter Wheels** FW1/FW2 + Shadowband | `FilterWheel`, `Shadowband` | via Head Sensor | — |
| 4 | **Temperature Controllers** TETech1/TETech2/**TETech1090** | `TemperatureController` | RS-232 | — |
| 5 | **Humidity Sensor** HDC2080EVM | `HumiditySensor` | RS-232 | — |
| 6 | **GPS/Positioning** GlobalSat, Novatel (GPS+gyro) | `GlobalSatGPS`, `NovatelGPS` | RS-232 | — |
| 7 | **SBHS** — Spec-Box Humidity Sensor (ESP32, JSON) | `SBHS` | RS-232 (JSON) | — |
| 8 | **ASB** — Air Sensors Box (ESP32, dual BME280 + MPRLS) | `ASB` | RS-232 (JSON) | — |
| 9 | **SRB** — SciGlobSRB1 sensors-reading board | `SRB` | RS-232 | — |
| 10 | **Direct-RS485 tracker** (Oriental Motor AZ/AZD, Modbus RTU) | `RS485Tracker` | RS-485 Modbus | — |
| 11 | **Relay board** (Samirob 4-channel) | `RelayBoard` | RS-232 (binary) | — |
| 12 | **Avantes spectrometer** (AvaSpec DLL) | `AvantesSpectrometer` | ctypes/USB | `[spectrometer]` |
| 13 | **Camera** (OpenCV / simulation) | `Camera` | OpenCV | `[camera]` |
| 14 | **Head-mounted IMU** (xIMU3) | `IMU` | xIMU3 SDK | `[imu]` |

The top-level **`Instrument`** facade opens an entire instrument from one YAML
(or IOF) file, degrades gracefully when a device is unplugged, and reports a
per-device status map.

---

## Installation

```bash
pip install sciglob
```

The core install depends only on `pyserial` + `pyyaml`. Vendor-heavy subsystems
are isolated behind extras:

```bash
pip install "sciglob[spectrometer]"   # Avantes (numpy for spectra; DLL ships with the instrument)
pip install "sciglob[imu]"            # xIMU3 head IMU
pip install "sciglob[camera]"         # OpenCV camera
pip install "sciglob[hardware]"       # all three hardware extras
```

### From Source

```bash
git clone https://github.com/ashutoshjoshi1/SciGlob-Library.git
cd SciGlob-Library
pip install -e ".[dev]"
```

---

## The Instrument facade — talk to all hardware at once

```python
from sciglob import Instrument

# Open a whole instrument from one config; missing devices degrade gracefully.
inst = Instrument.from_yaml("pandora101.yaml")   # or Instrument.from_iof("Pandora101_OF.txt")
with inst:
    inst.tracker.move_to(zenith=45.0, azimuth=180.0)
    inst.filter_wheel_1.set_filter("U340")

    inst.spectrometer.set_integration_time(200)   # ms
    spectrum = inst.spectrometer.measure(10)       # 10 accumulated cycles

    rh = inst.sbhs.get_humidity()
    inst.head_sensor.spec_power_cycle(1)           # auto-marks the spectrometer first

    print(inst.status())                           # {'head_sensor': {'state': 'connected'}, ...}
```

Run it entirely in software (no hardware attached) with `simulated=True`:

```python
inst = Instrument.from_yaml("pandora101.yaml", simulated=True)
```

### New device quick-starts

```python
from sciglob import SBHS, ASB, SRB, RelayBoard, RS485Tracker

# ESP32 JSON sensor boxes
with SBHS(port="COM8") as sbhs:
    print(sbhs.get_temperature(), sbhs.get_humidity(), sbhs.get_pressure())
with ASB(port="COM9") as asb:
    print(asb.get_ambient_pressure())     # MPRLS

# SciGlobSRB1 board
with SRB(port="COM11") as srb:
    print(srb.get_all_sensors())

# Samirob relay board
board = RelayBoard(port="COM12", nrelays=4)
board.connect(); board.on(1); print(board.state(1)); board.off(1)

# Direct-RS485 tracker (Oriental Motor AZ/AZD) — same facade as the head-sensor Tracker
trk = RS485Tracker(port="COM10", zenith_slave=1, azimuth_slave=2)
trk.connect(); trk.home(); trk.move_to(zenith=30.0, azimuth=120.0)

# Avantes spectrometer  (pip install "sciglob[spectrometer]")
from sciglob.spectrometers import AvantesSpectrometer, get_session
session = get_session(); session.init()
spec = AvantesSpectrometer(serial="1234", session=session)
spec.connect(); spec.set_integration_time(200); spectrum = spec.measure(10)

# Camera  (pip install "sciglob[camera]")
from sciglob.camera import Camera
with Camera(backend="opencv") as cam:
    frame = cam.capture()

# xIMU3 head IMU  (pip install "sciglob[imu]")
from sciglob.imu import IMU
with IMU(port="COM13") as imu:
    print(imu.get_readings())             # Roll/Pitch/Yaw/Temp/Battery
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
│                        Application                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SciGlob Library API                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │  Head   │ │ Tracker │ │ Filter  │ │  Temp   │ │  GPS    │   │
│  │ Sensor  │ │         │ │  Wheel  │ │ Control │ │         │   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
│       │           │          │          │          │            │
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

- [API Reference](docs/API_REFERENCE.md) - Full API documentation
- [Architecture](docs/PLATFORM_ARCHITECTURE.md) - Detailed system architecture
- [Command Reference](SCIGLOB_COMMAND_REFERENCE.md) - Complete protocol documentation
- [Library Specification](SCIGLOB_LIBRARY_SPEC.md) - Full implementation specification

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest`
5. Submit a pull request


