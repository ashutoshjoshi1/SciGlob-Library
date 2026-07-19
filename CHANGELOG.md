# Changelog

All notable changes to the SciGlob Library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-18

Full Pandora-class hardware coverage. Every subsystem of a SciGlob / Pandora
instrument is now drivable through `sciglob` with a real driver **and** a
simulation twin, behind one `Instrument` facade. The 0.1.6 public API is
unchanged. Wire constants were distilled from the field-proven NewBlick/Blick
and Pandora2.0 codebases and verified against source.

### Added — new devices
- **SBHS** (`sciglob.devices.SBHS`) — ESP32 JSON Spec-Box Humidity Sensor.
- **ASB** (`sciglob.devices.ASB`) — ESP32 Air Sensors Box (dual BME280 + MPRLS
  ambient pressure).
- **SRB** (`sciglob.devices.SRB`) — SciGlobSRB1 sensors-reading board.
- **TETech1090** support in `TemperatureController` — `#`-framed protocol at
  19200 baud with CRC-16/XMODEM and IEEE-754 float32 values (TETech1/TETech2
  behavior unchanged).
- **RelayBoard** (`sciglob.devices.RelayBoard`) — Samirob 4-channel binary relay
  board.
- **RS485Tracker** (`sciglob.devices.RS485Tracker`) — direct-RS485 Oriental
  Motor AZ/AZD tracker (Modbus RTU), exposing the same `move_to`/`home`/
  `get_position`/`check_alarms` facade as the head-sensor `Tracker` so tracking
  backends are swappable via config.
- **Avantes spectrometer** (`sciglob.spectrometers`) — ctypes-over-`avaspecx64.dll`
  driver with a process-global session manager, the full recovery doctrine
  (Tier A device-drop / Tier B session-restart), dead-handle guards, and a
  `SimulatedSpectrometer` twin. Optional extra `[spectrometer]`.
- **Camera** (`sciglob.camera`) — OpenCV / simulated backends; accepts the first
  device that delivers a frame and stores the effective resolution. Extra
  `[camera]`.
- **IMU** (`sciglob.imu`) — xIMU3 push-based head IMU with per-message-type
  counters (the "connected but silent" diagnostic). Extra `[imu]`.

### Added — facade & core
- **`Instrument`** facade — `from_yaml` / `from_iof` / `from_dict` / programmatic
  construction; opens a full instrument, degrades gracefully (`strict` flag),
  reports a per-device `status()` map, and wires the relay↔spectrometer
  power-cycle coupling.
- **`Instrument.from_iof`** + `sciglob.config.config_from_iof` — build an
  instrument config from a Pandora Instrument Operation File.
- ESP32-safe serial profile, process-wide `PortRegistry` collision guard, a
  field-faithful `ask()` QA cycle (drain → poll → grace retries →
  unexpected-answer escalation), and binary-frame helpers (`write_frame`,
  `read_exact`) in `sciglob.core.connection`.
- `sciglob.core.simulation` — `SimulatedTransport` / `make_responder` shared
  simulation machinery (simulated devices run the real QA code paths).
- New exceptions: `PortCollisionError`, `DeviceIdentityError`, `RecoveryFailed`,
  `SessionRestartRequired`, `RelayBoardError`, `ImuError` (plus the existing
  `SpectrometerError`, `CameraError`).
- New optional extras: `[spectrometer]`, `[imu]`, `[camera]`, `[hardware]`.

### Added — head sensor hardening
- `HeadSensor.spec_power_cycle(1|2)` with a `set_spec_power_cycle_hook` that
  marks an attached spectrometer power-cycled **before** the USB relay fires
  (prevents the freed-handle access-violation crash class).
- `get_motor_alarms()`, `get_motor_temperatures()`, `get_motor_currents()`, and a
  documented `recover()` recovery ladder (re-ask ID → DTR pulse → reopen port →
  peripheral reset → power reset) with field-verified timings.

### Documentation
- New `docs/RELIABILITY.md` capturing the ESP32 and Avantes reliability doctrine
  (the *why* behind the field fixes).
- README device table, per-device quick-starts, and facade guide;
  `SCIGLOB_COMMAND_REFERENCE.md` wire tables for the new subsystems.
- New examples: `examples/full_instrument.py`, `examples/spectrometer_measurement.py`.

### Fixed
- **TETech1/2 temperature readback**: GET responses are now parsed with the
  leading `*` frame character stripped before hex decoding. Real devices frame
  answers as `*<hex><checksum>^`; the previous parser left the `*` in place and
  raised `ValueError` on every real GET. Also raised the TC serial timeout to
  the 12 s device-action window so slow float32 answers are not dropped.
- **RS485 tracker** (new in 0.2.0): added half-duplex TX-echo handling
  (`echo=` option), correct Modbus exception-frame decoding, a pre-move STOP
  pulse, and motion/home completion gating that waits for motion to actually
  start before reporting "settled".

### Tests
- 250+ new tests, all hardware-free via simulated transports, including the
  field-incident regressions (`test_sbhs_identify_without_configured_id`,
  `test_esp32_open_never_pulses_reset`, `test_reset_pulse_line_sequence`,
  `test_last_complete_json_record_parsing`, `test_port_collision_refused`,
  `test_avantes_dead_handle_guards`, `test_tier_a_never_calls_done`,
  `test_tier_b_sentinel_escalation`, `test_rapid_refail_gated_on_no_data`,
  `test_camera_accepts_first_working_frame_any_resolution`,
  `test_imu_counts_messages_per_type`).

## [0.1.6] - 2026-06-18

### Fixed
- **Temperature controller**: `TemperatureController.connect()` no longer fails
  unconditionally. The connection guard checked `_connected` before verification
  set it, so every connection attempt raised — the controller was unusable.
- **Solar timing**: corrected solar noon / sunrise / sunset, which were offset by
  ~6 hours due to a wrong equation-of-time term. These now derive from the
  verified solar-position routine (sun's hour angle driven to zero).
- **Lunar phase**: fixed illuminated fraction and phase. The previous formula
  depended on sidereal time and oscillated 0→1 within a single day; it now uses
  the geocentric solar elongation.
- **Moonrise / moonset**: now computed and populated in `AstronomicalEvents`
  (previously always `None`, silently disabling every moon-anchored schedule
  entry). Added `MOON_RISE` / `MOON_SET` handling in the schedule executor.
- **Tracker alarms**: `check_alarms()` no longer reports a serial read failure
  (sentinel code `-1`) as a motor alarm; only positive alarm codes raise.
- **GlobalSat GPS**: `send_command()` now appends the protocol terminator
  (`\r\n`) instead of sending the command with no line ending.
- **Head sensor**: an explicit `timeout=0` is now honoured instead of being
  replaced by the default timeout.
- **Shadowband**: guarded the angle/position conversions against
  `ZeroDivisionError` and `math` domain errors at extreme `ratio` values.

### Security
- Removed `exec()` of `COMMAND` values and replaced `eval()` of loop (`XIJ`)
  values with `ast.literal_eval()` in the routine executor, eliminating arbitrary
  code execution from `.rout` files.
- Added a CPU-spin guard to the schedule entry loop (unlimited repetitions with
  unknown routine codes previously busy-looped a core).

### Changed
- Package version is now single-sourced from `sciglob.__version__` and read
  dynamically by the build backend. This resolves the previous mismatch between
  `pyproject.toml` (0.1.5) and `sciglob/__init__.py` (0.1.4).
- Declared the license with the PEP 639 SPDX expression (`license = "MIT"`,
  `license-files = ["LICENSE"]`); the build now requires `setuptools>=77`.

### Tests
- Added `tests/test_regression_fixes.py` covering each fix above.

## [0.1.5] - 2025-12-17

### Added
- `CommandBuilder` class for constructing device commands programmatically
- Complete command set for all supported devices
- Real-Time Platform Architecture documentation (`docs/PLATFORM_ARCHITECTURE.md`)
- Comprehensive 1,700+ line technical specification for distributed monitoring system
- Command validation and formatting utilities

### Changed
- Improved filter wheel command handling
- Enhanced device protocol implementations

### Documentation
- Added detailed architecture for 300+ station real-time platform
- Database schemas for TimescaleDB and PostgreSQL
- Kubernetes deployment specifications
- Security architecture with RBAC implementation
- 10-week development roadmap

## [0.1.4] - 2025-12-03

### Added
- Help system for all device classes (`.help()`, `.list_methods()`, `.list_properties()`)
- Library-level help functions (`sciglob.help()`, `sciglob.help_config()`)
- Hardware configuration classes (`SerialConfig`, `HeadSensorConfig`, etc.)
- YAML configuration load/save support (`HardwareConfig.from_yaml()`, `.to_yaml()`)
- `config` and `serial_config` parameters for all device constructors
- Command reference in help output for each device

### Changed
- All devices now inherit from `HelpMixin` for consistent help functionality
- Configuration can now be passed via config objects or individual parameters

## [0.1.3] - 2025-12-03

### Changed
- Updated README with correct GitHub repository URL
- Fixed author and maintainer information

## [0.1.2] - 2025-12-03

### Changed
- Updated author email and GitHub URLs

## [0.1.1] - 2025-12-03

### Changed
- Fixed PyPI metadata

## [0.1.0] - 2025-12-03

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
| 0.1.6 | 2026-06-18 | Bug fixes: solar/lunar timing, temperature controller, GPS, tracker alarms; removed code execution from routines |
| 0.1.5 | 2025-12-17 | Added CommandBuilder, real-time platform architecture docs |
| 0.1.4 | 2025-12-03 | Added help system and configuration classes |
| 0.1.3 | 2025-12-03 | Updated README URLs |
| 0.1.2 | 2025-12-03 | Updated author info |
| 0.1.1 | 2025-12-03 | Fixed PyPI metadata |
| 0.1.0 | 2025-12-03 | Initial release |

---

## Upgrade Guide

### From 0.0.x to 0.1.0

This is the initial public release. No migration required.

---

## Links

- [GitHub Repository](https://github.com/ashutoshjoshi1/SciGlob-Library)
- [Documentation](https://github.com/ashutoshjoshi1/SciGlob-Library/blob/main/docs/API_REFERENCE.md)
- [Issue Tracker](https://github.com/ashutoshjoshi1/SciGlob-Library/issues)

