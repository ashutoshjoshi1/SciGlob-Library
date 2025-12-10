"""Help mixin for all SciGlob device classes.

This module provides a mixin class that adds help() functionality
to all device classes in the library.
"""

import inspect
from typing import Any, Optional


class HelpMixin:
    """Mixin class that provides help functionality for devices.

    Add this mixin to any device class to enable:
    - device.help() - Show comprehensive help
    - device.help('method_name') - Show help for specific method
    - device.list_methods() - List all available methods
    - device.list_properties() - List all properties
    """

    # Override these in subclasses
    _device_name: str = "Device"
    _device_description: str = "A SciGlob device"
    _supported_types: list[str] = []
    _default_config: dict[str, Any] = {}
    _command_reference: dict[str, str] = {}

    def help(self, method: Optional[str] = None) -> None:
        """Display help information.

        Args:
            method: Optional method name to get specific help for
        """
        if method:
            self._help_method(method)
        else:
            self._help_full()

    def _help_full(self) -> None:
        """Display full help for the device."""
        lines = []
        lines.append("=" * 70)
        lines.append(f"{self._device_name} - Help")
        lines.append("=" * 70)
        lines.append("")
        lines.append("DESCRIPTION:")
        lines.append(f"  {self._device_description}")
        lines.append("")

        if self._supported_types:
            lines.append("SUPPORTED TYPES:")
            for t in self._supported_types:
                lines.append(f"  - {t}")
            lines.append("")

        if self._default_config:
            lines.append("DEFAULT CONFIGURATION:")
            for key, value in self._default_config.items():
                lines.append(f"  {key}: {value}")
            lines.append("")

        # List properties
        props = self.list_properties()
        if props:
            lines.append("PROPERTIES:")
            for prop in props:
                lines.append(f"  .{prop}")
            lines.append("")

        # List methods
        methods = self.list_methods()
        if methods:
            lines.append("METHODS:")
            for m in methods:
                lines.append(f"  .{m}()")
            lines.append("")

        if self._command_reference:
            lines.append("COMMANDS:")
            for cmd, desc in self._command_reference.items():
                lines.append(f"  {cmd}: {desc}")
            lines.append("")

        lines.append("Use .help('method_name') for detailed method help")
        lines.append("=" * 70)

        print("\n".join(lines))

    def _help_method(self, method_name: str) -> None:
        """Display help for a specific method."""
        if hasattr(self, method_name):
            attr = getattr(self, method_name)
            if callable(attr):
                print(f"\n{self._device_name}.{method_name}()")
                print("-" * 50)

                # Get signature
                try:
                    sig = inspect.signature(attr)
                    print(f"Signature: {method_name}{sig}")
                except (ValueError, TypeError):
                    pass

                # Get docstring
                if attr.__doc__:
                    print(f"\n{attr.__doc__}")
                else:
                    print("\nNo documentation available.")
            else:
                print(f"{method_name} is a property, not a method")
                if hasattr(type(self), method_name):
                    prop = getattr(type(self), method_name)
                    if prop.__doc__:
                        print(f"\n{prop.__doc__}")
        else:
            print(f"Method '{method_name}' not found")
            print(f"Available methods: {', '.join(self.list_methods())}")

    def list_methods(self) -> list[str]:
        """List all public methods of the device.

        Returns:
            List of method names
        """
        methods = []
        for name in dir(self):
            if not name.startswith('_'):
                attr = getattr(self, name)
                if callable(attr) and not isinstance(attr, type):
                    methods.append(name)
        return sorted(methods)

    def list_properties(self) -> list[str]:
        """List all public properties of the device.

        Returns:
            List of property names
        """
        props = []
        for name in dir(type(self)):
            if not name.startswith('_'):
                attr = getattr(type(self), name, None)
                if isinstance(attr, property):
                    props.append(name)
        return sorted(props)

    @classmethod
    def class_help(cls) -> None:
        """Display class-level help."""
        lines = []
        lines.append("=" * 70)
        lines.append(f"{cls._device_name}")
        lines.append("=" * 70)
        lines.append("")
        lines.append(cls._device_description)
        lines.append("")

        if cls._supported_types:
            lines.append("Supported Types:")
            for t in cls._supported_types:
                lines.append(f"  - {t}")

        if cls._default_config:
            lines.append("\nDefault Configuration:")
            for key, value in cls._default_config.items():
                lines.append(f"  {key}: {value}")

        lines.append("")
        lines.append("=" * 70)
        print("\n".join(lines))


# Help text for the library itself
LIBRARY_HELP = """
================================================================================
                          SciGlob Library - Help
================================================================================

OVERVIEW:
  SciGlob Library provides a unified Python interface for controlling
  scientific instruments used in atmospheric monitoring systems.

SUPPORTED DEVICES:
  ┌─────────────────────┬─────────────────────────────────────┬────────────┐
  │ Device              │ Types                               │ Connection │
  ├─────────────────────┼─────────────────────────────────────┼────────────┤
  │ HeadSensor          │ SciGlobHSN1, SciGlobHSN2            │ RS-232     │
  │ Tracker             │ Directed Perceptions, LuftBlickTR1  │ via HS     │
  │ FilterWheel         │ FW1, FW2 (9 positions each)         │ via HS     │
  │ Shadowband          │ SB                                  │ via HS     │
  │ TemperatureController│ TETech1, TETech2                   │ RS-232     │
  │ HumiditySensor      │ HDC2080EVM                          │ RS-232     │
  │ GlobalSatGPS        │ GlobalSat (GPS only)                │ RS-232     │
  │ NovatelGPS          │ Novatel (GPS+Gyro)                  │ RS-232     │
  └─────────────────────┴─────────────────────────────────────┴────────────┘

QUICK START:
  from sciglob import HeadSensor

  # Connect with default settings
  with HeadSensor(port='/dev/ttyUSB0') as hs:
      hs.tracker.move_to(zenith=45.0, azimuth=180.0)
      hs.filter_wheel_1.set_filter('U340')
      print(hs.get_all_sensors())

CONFIGURATION:
  from sciglob.config import HeadSensorConfig, SerialConfig

  config = HeadSensorConfig(
      serial=SerialConfig(port='COM3', baudrate=9600),
      tracker_type='LuftBlickTR1',
      motion_limits=[0, 85, 0, 360],
  )

  hs = HeadSensor(config=config)

GETTING HELP:
  # Library help
  import sciglob
  sciglob.help()

  # Device help
  hs = HeadSensor()
  hs.help()              # Full help
  hs.help('move_to')     # Method help
  hs.list_methods()      # List all methods
  hs.list_properties()   # List all properties

  # Config help
  from sciglob.config import HeadSensorConfig
  print(HeadSensorConfig.help())

SERIAL PORT CONFIGURATION:
  Default RS-232 Settings:
    baudrate    : 9600
    bytesize    : 8
    parity      : 'N' (None)
    stopbits    : 1
    timeout     : 0 (non-blocking)
    write_timeout: 20.0 seconds

DOCUMENTATION:
  Full API Reference: https://github.com/ashutoshjoshi1/SciGlob-Library/docs/API_REFERENCE.md

================================================================================
"""


def show_library_help() -> None:
    """Display library-level help."""
    print(LIBRARY_HELP)


def show_config_help() -> None:
    """Display configuration help."""
    print("""
================================================================================
                     SciGlob Configuration Help
================================================================================

CONFIGURATION CLASSES:
  SerialConfig            - Serial port settings (port, baudrate, etc.)
  HeadSensorConfig        - Head sensor + tracker + filter wheels
  TemperatureControllerConfig - TETech temperature controllers
  HumiditySensorConfig    - HDC2080EVM humidity sensor
  GPSConfig               - GPS/Positioning systems
  HardwareConfig          - Complete system configuration

SETTING COM PORT:
  from sciglob import HeadSensor

  # Simple way
  hs = HeadSensor(port='COM3', baudrate=9600)

  # Using config object
  from sciglob.config import SerialConfig
  hs = HeadSensor(serial_config=SerialConfig(port='COM3', baudrate=9600))

LOADING FROM YAML:
  from sciglob.config import HardwareConfig

  config = HardwareConfig.from_yaml('my_config.yaml')

SAVING TO YAML:
  config = HardwareConfig()
  config.head_sensor.serial.port = 'COM3'
  config.to_yaml('my_config.yaml')

EXAMPLE YAML:
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
      baudrate: 9600
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

================================================================================
""")

