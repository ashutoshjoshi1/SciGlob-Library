# SciGlob Library Architecture

## Overview

SciGlob is a Python library for controlling scientific instrumentation including sensor heads with filter wheels and Oriental Motors for precise angular positioning (azimuth and zenith).

---

## 📦 Project Structure

```
sciglob/
├── __init__.py                 # Package initialization, version, public API
├── core/
│   ├── __init__.py
│   ├── base.py                 # Abstract base classes for all devices
│   ├── connection.py           # Serial/communication utilities
│   ├── exceptions.py           # Custom exceptions
│   └── utils.py                # Common utilities
│
├── sensor_head/
│   ├── __init__.py
│   ├── sensor.py               # Main SensorHead class
│   └── filter_wheel/
│       ├── __init__.py
│       ├── wheel.py            # FilterWheel controller
│       └── filters.py          # Filter definitions and configurations
│
├── motors/
│   ├── __init__.py
│   ├── base_motor.py           # Abstract motor class
│   ├── oriental_motor.py       # Oriental Motors specific implementation
│   ├── azimuth.py              # Azimuth angle controller
│   ├── zenith.py               # Zenith angle controller
│   └── multi_axis.py           # Coordinated multi-motor control
│
└── config/
    ├── __init__.py
    ├── settings.py             # Configuration management
    └── defaults.yaml           # Default configuration values

tests/
├── __init__.py
├── conftest.py                 # Pytest fixtures
├── test_sensor_head.py
├── test_filter_wheel.py
├── test_oriental_motor.py
├── test_azimuth.py
├── test_zenith.py
└── mocks/                      # Hardware mocks for testing
    ├── __init__.py
    └── mock_serial.py

examples/
├── basic_usage.py              # Simple getting started example
├── filter_wheel_demo.py        # Filter wheel operations
├── motor_control.py            # Motor positioning examples
└── full_system.py              # Complete system integration

docs/
├── index.md
├── installation.md
├── quickstart.md
├── api/
│   ├── sensor_head.md
│   ├── filter_wheel.md
│   └── motors.md
└── hardware_setup.md
```

---

## 🏗️ Component Architecture

### 1. Sensor Head Module

```
┌─────────────────────────────────────────┐
│              SensorHead                  │
│  ┌───────────────────────────────────┐  │
│  │         Filter Wheel(s)           │  │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ │  │
│  │  │ F1  │ │ F2  │ │ F3  │ │ ... │ │  │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ │  │
│  └───────────────────────────────────┘  │
│                                          │
│  • Select filter by name/position        │
│  • Query current filter                  │
│  • Rotate to specific position           │
│  • Filter configuration management       │
└─────────────────────────────────────────┘
```

**Key Classes:**
- `SensorHead` - Main controller for the sensor head unit
- `FilterWheel` - Individual filter wheel control
- `Filter` - Filter definition (name, position, properties)

### 2. Oriental Motors Module

```
┌─────────────────────────────────────────┐
│           Motor Controller               │
│                                          │
│  ┌─────────────────┐ ┌────────────────┐ │
│  │  Azimuth Motor  │ │  Zenith Motor  │ │
│  │   (Horizontal)  │ │   (Vertical)   │ │
│  │                 │ │                │ │
│  │  Range: 0-360°  │ │  Range: 0-90°  │ │
│  │  ↻ Clockwise    │ │  ↑ Elevation   │ │
│  │  ↺ Counter-CW   │ │  ↓ Depression  │ │
│  └─────────────────┘ └────────────────┘ │
│                                          │
│  • Absolute positioning                  │
│  • Relative movement                     │
│  • Speed control                         │
│  • Home/reference positioning            │
│  • Multi-motor coordination              │
└─────────────────────────────────────────┘
```

**Key Classes:**
- `OrientalMotor` - Base class for Oriental Motors communication
- `AzimuthController` - Horizontal angle control (0-360°)
- `ZenithController` - Vertical angle control (typically 0-90°)
- `MultiAxisController` - Coordinated movement of multiple motors

---

## 🔌 Communication Layer

```
┌──────────────────────────────────────────────────────┐
│                   Application Layer                   │
│  (SensorHead, FilterWheel, AzimuthController, etc.)  │
└──────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────┐
│                   Protocol Layer                      │
│     (Device-specific command encoding/decoding)      │
└──────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────┐
│                  Connection Layer                     │
│        (Serial, USB, Ethernet abstraction)           │
└──────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────┐
│                    Hardware                           │
│   (Sensor Head, Filter Wheels, Oriental Motors)      │
└──────────────────────────────────────────────────────┘
```

---

## 📋 Implementation Plan

### Phase 1: Foundation (Core Module)
- [ ] Set up package structure with `pyproject.toml`
- [ ] Implement `BaseDevice` abstract class
- [ ] Create connection utilities (serial port handling)
- [ ] Define custom exceptions
- [ ] Set up logging infrastructure

### Phase 2: Sensor Head & Filter Wheel
- [ ] Implement `FilterWheel` class with basic operations
- [ ] Create `Filter` configuration system
- [ ] Implement `SensorHead` wrapper class
- [ ] Add filter wheel homing and calibration
- [ ] Write unit tests with mocked hardware

### Phase 3: Oriental Motors Integration
- [ ] Implement `OrientalMotor` base communication
- [ ] Create `AzimuthController` for horizontal positioning
- [ ] Create `ZenithController` for vertical positioning
- [ ] Implement `MultiAxisController` for coordinated movement
- [ ] Add position feedback and error handling

### Phase 4: Integration & Polish
- [ ] System integration tests
- [ ] Create comprehensive examples
- [ ] Write documentation
- [ ] Performance optimization
- [ ] Add configuration file support (YAML/JSON)

---

## 🎯 Design Principles

1. **Abstraction**: Common interface for all devices via base classes
2. **Modularity**: Each component can be used independently
3. **Safety**: Built-in limits, validation, and error recovery
4. **Testability**: Mock hardware support for unit testing
5. **Configuration**: Flexible configuration via files or code
6. **Logging**: Comprehensive logging for debugging
7. **Type Hints**: Full type annotation for IDE support

---

## 📝 API Design Preview

```python
from sciglob import SensorHead, AzimuthController, ZenithController

# Initialize components
sensor = SensorHead(port="/dev/ttyUSB0")
azimuth = AzimuthController(port="/dev/ttyUSB1")
zenith = ZenithController(port="/dev/ttyUSB2")

# Filter wheel operations
sensor.filter_wheel.select("UV_340nm")
current_filter = sensor.filter_wheel.current
sensor.filter_wheel.rotate_to_position(3)

# Motor positioning
azimuth.move_to(180.0)        # Move to 180° absolute
zenith.move_to(45.0)          # Move to 45° elevation
azimuth.move_relative(10.0)   # Move 10° clockwise

# Coordinated movement
from sciglob.motors import MultiAxisController
axes = MultiAxisController(azimuth=azimuth, zenith=zenith)
axes.move_to(azimuth=90.0, zenith=30.0)  # Simultaneous movement

# Context manager support
with SensorHead(port="/dev/ttyUSB0") as sensor:
    sensor.filter_wheel.select("Red_630nm")
    # Auto-cleanup on exit
```

---

## ⚙️ Configuration Example

```yaml
# config/defaults.yaml
sensor_head:
  port: "/dev/ttyUSB0"
  baudrate: 9600
  timeout: 1.0
  
  filter_wheel:
    positions: 6
    filters:
      - position: 1
        name: "UV_340nm"
        wavelength: 340
      - position: 2
        name: "Blue_450nm"
        wavelength: 450
      # ...

motors:
  azimuth:
    port: "/dev/ttyUSB1"
    baudrate: 115200
    min_angle: 0.0
    max_angle: 360.0
    home_position: 0.0
    
  zenith:
    port: "/dev/ttyUSB2"
    baudrate: 115200
    min_angle: 0.0
    max_angle: 90.0
    home_position: 0.0
```

---

## 🔧 Dependencies

```
pyserial>=3.5       # Serial communication
pyyaml>=6.0         # Configuration files
typing-extensions   # Enhanced type hints
pydantic>=2.0       # Data validation (optional)
```

---

## Next Steps

1. **You provide**: The existing control code for each component
2. **I will**: Integrate it into this structure, maintaining your protocol logic
3. **Together**: Refine the API based on your usage patterns

Please share the code for:
- Sensor head / filter wheel communication protocol
- Oriental Motors communication protocol
- Any existing configuration or calibration routines

