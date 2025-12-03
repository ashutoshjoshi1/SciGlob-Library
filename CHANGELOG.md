# Changelog

All notable changes to the SciGlob Library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet

## [0.1.0] - 2024-01-15
## [0.1.1] - 2025-11-10
## [0.1.2] - 2025-12-03

### Added

#### Core
- Serial communication base layer with question-answer protocol
- Custom exception hierarchy for error handling
- Protocol definitions for all supported devices
- Utility functions for position conversion, angle calculations
- Configuration management with YAML support

#### Head Sensor Module
- Support for SciGlobHSN1 and SciGlobHSN2 head sensors
- Auto-detection of sensor type
- Internal sensor readings (temperature, humidity, pressure)
- Access to sub-devices (tracker, filter wheels, shadowband)
- Power reset commands

#### Tracker Module
- Azimuth (pan) and zenith (tilt) motor control
- Support for Directed Perceptions and LuftBlickTR1 trackers
- Position control in degrees or steps
- Relative and absolute movement commands
- Motor temperature monitoring (LuftBlickTR1)
- Motor alarm detection and reporting (LuftBlickTR1)
- Home and park positions

#### Filter Wheel Module
- Support for FW1 and FW2 (9 positions each)
- Set position by number or filter name
- Filter mapping and configuration
- Reset functionality

#### Shadowband Module
- Step-based and angle-based positioning
- Relative movement support
- Reset functionality

#### Temperature Controller Module
- Support for TETech1 (16-bit) and TETech2 (32-bit) controllers
- Temperature setpoint control
- PID parameter configuration
- Temperature reading from control and secondary sensors

#### Humidity Sensor Module
- Support for HDC2080EVM sensor
- Temperature and humidity readings
- Little-endian hex parsing

#### GPS/Positioning Module
- GlobalSat GPS support with NMEA parsing
- Novatel GPS+Gyroscope support with INSPVA parsing
- Position (latitude, longitude, altitude) readings
- Orientation (roll, pitch, yaw) readings (Novatel)

#### Documentation
- Comprehensive API reference manual
- Command reference documentation
- Library specification document
- Usage examples

#### Testing
- Unit tests for all core modules
- Device tests with mocked hardware
- ~80% code coverage

### Changed
- Nothing (initial release)

### Deprecated
- Nothing (initial release)

### Removed
- Nothing (initial release)

### Fixed
- Nothing (initial release)

### Security
- Nothing (initial release)

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| 0.1.0 | 2024-01-15 | Initial release |

---

## Upgrade Guide

### From 0.0.x to 0.1.0

This is the initial public release. No migration required.

---

## Links

- [GitHub Repository](https://github.com/SciGlob/SciGlob-Library)
- [Documentation](https://github.com/SciGlob/SciGlob-Library/blob/main/docs/API_REFERENCE.md)
- [Issue Tracker](https://github.com/SciGlob/SciGlob-Library/issues)

