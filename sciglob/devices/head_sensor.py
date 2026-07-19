"""Head Sensor interface for SciGlob instruments."""

import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Optional

from sciglob.core.base import BaseDevice

if TYPE_CHECKING:
    from sciglob.config import HeadSensorConfig
    from sciglob.devices.filter_wheel import FilterWheel
    from sciglob.devices.shadowband import Shadowband
    from sciglob.devices.tracker import Tracker
from sciglob.core.connection import SerialConnection, parse_sensor_value
from sciglob.core.exceptions import (
    CommunicationError,
    ConnectionError,
    DeviceError,
    RecoveryFailed,
    SensorError,
)
from sciglob.core.help_mixin import HelpMixin
from sciglob.core.protocols import (
    HEAD_SENSOR_COMMANDS,
    SENSOR_CONVERSIONS,
    TIMING_CONFIG,
    DeviceType,
    SerialConfig,
    get_error_message,
    get_motor_alarm_message,
)


class HeadSensor(BaseDevice, HelpMixin):
    """
    Head Sensor interface for SciGlob instruments.

    The Head Sensor is the main communication hub that connects to:
    - Tracker (motor controller for azimuth/zenith)
    - Filter Wheels (FW1, FW2)
    - Shadowband
    - Internal sensors (temperature, humidity, pressure)

    Supported types:
    - SciGlobHSN1: Basic head sensor
    - SciGlobHSN2: Extended sensors (temp, humidity, pressure)

    Example:
        >>> hs = HeadSensor(port="/dev/ttyUSB0")
        >>> hs.connect()
        >>> print(f"Device: {hs.device_id}")
        >>> if hs.sensor_type == "SciGlobHSN2":
        ...     print(f"Temperature: {hs.get_temperature()}°C")
        >>> hs.disconnect()

    Using context manager:
        >>> with HeadSensor(port="/dev/ttyUSB0") as hs:
        ...     print(hs.get_status())

    Help:
        >>> hs.help()              # Show full help
        >>> hs.help('move_to')     # Help for specific method
        >>> hs.list_methods()      # List all methods
    """

    # HelpMixin properties
    _device_name = "HeadSensor"
    _device_description = "Main communication hub for SciGlob instruments"
    _supported_types = ["SciGlobHSN1", "SciGlobHSN2"]
    _default_config = {
        "baudrate": 9600,
        "bytesize": 8,
        "parity": "N",
        "stopbits": 1,
        "timeout": 1.0,
        "tracker_type": "Directed Perceptions",
        "degrees_per_step": 0.01,
        "motion_limits": "[0, 90, 0, 360]",
        "home_position": "[0.0, 180.0]",
    }
    _command_reference = {
        "?": "Get device ID",
        "TRw": "Get tracker position",
        "TRb<az>,<zen>": "Move tracker (both axes)",
        "TRt<steps>": "Move zenith (tilt)",
        "TRp<steps>": "Move azimuth (pan)",
        "TRr": "Reset tracker",
        "TRY": "Power cycle tracker",
        "F1<1-9>": "Set filter wheel 1 position",
        "F2<1-9>": "Set filter wheel 2 position",
        "SB<pos>": "Set shadowband position",
        "HTt?": "Read temperature (HSN2)",
        "HTh?": "Read humidity (HSN2)",
        "HTp?": "Read pressure (HSN2)",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 1.0,
        name: str = "HeadSensor",
        sensor_type: Optional[str] = None,
        fw1_filters: Optional[list[str]] = None,
        fw2_filters: Optional[list[str]] = None,
        tracker_type: str = "Directed Perceptions",
        degrees_per_step: float = 0.01,
        motion_limits: Optional[list[float]] = None,
        home_position: Optional[list[float]] = None,
        config: Optional["HeadSensorConfig"] = None,
        serial_config: Optional[SerialConfig] = None,
        connection: Optional[Any] = None,
    ):
        """
        Initialize the Head Sensor.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0' or 'COM3')
            baudrate: Communication speed (default 9600)
            timeout: Command timeout in seconds
            name: Device name for logging
            sensor_type: Expected sensor type ('SciGlobHSN1' or 'SciGlobHSN2')
            fw1_filters: List of 9 filter names for Filter Wheel 1
            fw2_filters: List of 9 filter names for Filter Wheel 2
            tracker_type: Tracker type ('Directed Perceptions' or 'LuftBlickTR1')
            degrees_per_step: Tracker resolution (typically 0.01°/step)
            motion_limits: [zenith_min, zenith_max, azimuth_min, azimuth_max]
            home_position: [zenith_home, azimuth_home] in degrees
            config: HeadSensorConfig object (overrides other parameters)
            serial_config: SerialConfig object for port settings
            connection: Optional SerialConnection-compatible transport to inject
                (e.g. sciglob.core.simulation.SimulatedTransport). When given,
                :meth:`connect` uses it instead of opening a real serial port,
                so tests and the Instrument facade run hardware-free.
        """
        # If config object provided, use its values
        if config is not None:
            port = config.serial.port or port
            baudrate = config.serial.baudrate
            timeout = config.serial.timeout or timeout
            sensor_type = config.sensor_type or sensor_type
            fw1_filters = config.fw1_filters
            fw2_filters = config.fw2_filters
            tracker_type = config.tracker_type
            degrees_per_step = config.degrees_per_step
            motion_limits = config.motion_limits
            home_position = config.home_position

        # If serial_config provided, use its values
        if serial_config is not None:
            port = serial_config.port or port
            baudrate = serial_config.baudrate
            timeout = serial_config.timeout or timeout

        super().__init__(port=port, baudrate=baudrate, timeout=timeout, name=name)

        self._expected_sensor_type = sensor_type
        self._sensor_type: Optional[str] = None
        self._device_id: Optional[str] = None

        # Filter wheel configuration
        self._fw1_filters = fw1_filters or ["OPEN"] * 9
        self._fw2_filters = fw2_filters or ["OPEN"] * 9

        # Tracker configuration
        self._tracker_type = tracker_type
        self._degrees_per_step = degrees_per_step
        self._motion_limits = motion_limits or [
            0,
            90,
            0,
            360,
        ]  # [zen_min, zen_max, azi_min, azi_max]
        self._home_position = home_position or [0.0, 180.0]  # [zenith_home, azimuth_home]

        # Child device references (lazy initialization)
        self._tracker: Optional[Tracker] = None
        self._filter_wheel_1: Optional[FilterWheel] = None
        self._filter_wheel_2: Optional[FilterWheel] = None
        self._shadowband: Optional[Shadowband] = None

        # Injected transport for hardware-free operation (simulation/tests).
        self._injected_connection = connection

        # Per-device reentrant lock guarding transport/shared-state operations
        # (brief §3: thread safety is API contract). RLock so the recovery
        # ladder can re-enter send_command while holding the lock.
        self._lock = threading.RLock()

        # Spectrometer power-cycle safety hook. Registered by an attached
        # Spectrometer so it can mark its USB/AVS handle dead *before* the
        # relay drops power (the v0.0.8.7 crash class: a stale handle used
        # across a USB power drop segfaults the vendor driver). Default None
        # (no-op). See :meth:`spec_power_cycle`.
        self._spec_power_cycle_hook: Optional[Callable[[int], None]] = None

    @property
    def device_id(self) -> Optional[str]:
        """Get the device identification string."""
        return self._device_id

    @property
    def sensor_type(self) -> Optional[str]:
        """Get the detected sensor type."""
        return self._sensor_type

    @property
    def tracker_type(self) -> str:
        """Get the tracker type."""
        return self._tracker_type

    @property
    def degrees_per_step(self) -> float:
        """Get the tracker resolution."""
        return self._degrees_per_step

    @property
    def motion_limits(self) -> list[float]:
        """Get motion limits [zen_min, zen_max, azi_min, azi_max]."""
        return self._motion_limits.copy()

    @property
    def home_position(self) -> list[float]:
        """Get home position [zenith_home, azimuth_home]."""
        return self._home_position.copy()

    @property
    def fw1_filters(self) -> list[str]:
        """Get Filter Wheel 1 filter names."""
        return self._fw1_filters.copy()

    @property
    def fw2_filters(self) -> list[str]:
        """Get Filter Wheel 2 filter names."""
        return self._fw2_filters.copy()

    @property
    def tracker(self):
        """
        Get the Tracker interface.

        Lazy initialization - creates Tracker on first access.
        """
        if self._tracker is None:
            from sciglob.devices.tracker import Tracker

            self._tracker = Tracker(self)
        return self._tracker

    @property
    def filter_wheel_1(self):
        """Get Filter Wheel 1 interface."""
        if self._filter_wheel_1 is None:
            from sciglob.devices.filter_wheel import FilterWheel

            self._filter_wheel_1 = FilterWheel(self, wheel_id=1)
        return self._filter_wheel_1

    @property
    def filter_wheel_2(self):
        """Get Filter Wheel 2 interface."""
        if self._filter_wheel_2 is None:
            from sciglob.devices.filter_wheel import FilterWheel

            self._filter_wheel_2 = FilterWheel(self, wheel_id=2)
        return self._filter_wheel_2

    @property
    def shadowband(self):
        """Get Shadowband interface."""
        if self._shadowband is None:
            from sciglob.devices.shadowband import Shadowband

            self._shadowband = Shadowband(self)
        return self._shadowband

    def connect(self) -> None:
        """
        Connect to the Head Sensor.

        Establishes serial connection and queries device identification.

        Raises:
            ConnectionError: If connection fails
            DeviceError: If device identification fails
        """
        if self._connected:
            self.logger.warning("Already connected to head sensor")
            return

        # Injected transport (simulation/tests): use it verbatim, skip scanning
        # and skip opening a real serial port.
        if self._injected_connection is not None:
            try:
                self._connection = self._injected_connection
                if not self._connection.is_open:
                    self._connection.open()
                self._query_device_id()
                self._connected = True
                self.logger.info(f"Connected to {self._sensor_type} (injected transport)")
                return
            except Exception as e:
                self.disconnect()
                raise ConnectionError(f"Failed to connect to head sensor: {e}") from e

        if self.port is None:
            # Try to auto-detect port
            self.port = self._scan_for_head_sensor()
            if self.port is None:
                raise ConnectionError("No head sensor found on any port")

        try:
            config = SerialConfig(baudrate=self.baudrate)
            self._connection = SerialConnection(port=self.port, config=config)
            self._connection.open()

            # Query device identification
            self._query_device_id()

            self._connected = True
            self.logger.info(f"Connected to {self._sensor_type} on {self.port}")

        except Exception as e:
            self.disconnect()
            raise ConnectionError(f"Failed to connect to head sensor: {e}") from e

    def _scan_for_head_sensor(self) -> Optional[str]:
        """Scan ports for a head sensor device."""
        self.logger.info("Scanning for head sensor...")
        return SerialConnection.scan_for_device(
            id_command="?",
            expected_response="SciGlob",
            baudrate=self.baudrate,
            timeout=TIMING_CONFIG["standard_timeout"],
        )

    def _query_device_id(self) -> None:
        """Query and parse device identification."""
        protocol = HEAD_SENSOR_COMMANDS["id"]

        response = self._connection.query(
            command=protocol.command,
            end_char=protocol.end_char,
            response_end_char=protocol.response_end_char,
            timeout=protocol.timeout,
        )

        if not response:
            raise DeviceError("No response to ID query")

        self._device_id = response.strip()

        # Determine sensor type
        if "SciGlobHSN2" in self._device_id:
            self._sensor_type = DeviceType.SCIGLOB_HSN2.value
        elif "SciGlobHSN1" in self._device_id or "SciGlob" in self._device_id:
            self._sensor_type = DeviceType.SCIGLOB_HSN1.value
        else:
            self._sensor_type = self._device_id

        # Validate against expected type if specified
        if self._expected_sensor_type:
            if self._expected_sensor_type not in self._sensor_type:
                raise DeviceError(f"Expected {self._expected_sensor_type}, got {self._sensor_type}")

    def disconnect(self) -> None:
        """Disconnect from the Head Sensor."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
            finally:
                self._connection = None
                self._connected = False
                self._tracker = None
                self._filter_wheel_1 = None
                self._filter_wheel_2 = None
                self._shadowband = None
                self.logger.info("Disconnected from head sensor")

    def send_command(self, command: str, timeout: Optional[float] = None) -> str:
        """
        Send a command to the Head Sensor.

        Args:
            command: Command string (without end character)
            timeout: Response timeout (uses default if None)

        Returns:
            Response string

        Raises:
            DeviceError: If not connected
            CommunicationError: If command fails
        """
        if not self._connected or self._connection is None:
            raise DeviceError("Not connected to head sensor")

        timeout = timeout if timeout is not None else self.timeout

        try:
            response: str = self._connection.query(
                command=command,
                end_char="\r",
                response_end_char="\n",
                timeout=timeout,
            )
            return response
        except Exception as e:
            raise CommunicationError(f"Command '{command}' failed: {e}") from e

    def get_id(self) -> str:
        """
        Get device identification string.

        Returns:
            Device ID string
        """
        if not self._connected:
            raise DeviceError("Not connected")

        response = self.send_command("?")
        return response.strip()

    def get_temperature(self) -> float:
        """
        Read head sensor temperature (SciGlobHSN2 only).

        Returns:
            Temperature in °C

        Raises:
            SensorError: If sensor type doesn't support temperature
        """
        if self._sensor_type != DeviceType.SCIGLOB_HSN2.value:
            raise SensorError(f"Temperature reading not supported on {self._sensor_type}")

        protocol = HEAD_SENSOR_COMMANDS["temperature"]
        response = self.send_command(protocol.command)

        value = parse_sensor_value(
            response,
            protocol.expected_prefix,
            SENSOR_CONVERSIONS["temperature"]["factor"],
        )

        if value is None:
            return float(SENSOR_CONVERSIONS["temperature"]["error_value"])
        return value

    def get_humidity(self) -> float:
        """
        Read head sensor humidity (SciGlobHSN2 only).

        Returns:
            Relative humidity in %

        Raises:
            SensorError: If sensor type doesn't support humidity
        """
        if self._sensor_type != DeviceType.SCIGLOB_HSN2.value:
            raise SensorError(f"Humidity reading not supported on {self._sensor_type}")

        protocol = HEAD_SENSOR_COMMANDS["humidity"]
        response = self.send_command(protocol.command)

        value = parse_sensor_value(
            response,
            protocol.expected_prefix,
            SENSOR_CONVERSIONS["humidity"]["factor"],
        )

        if value is None:
            return float(SENSOR_CONVERSIONS["humidity"]["error_value"])
        return value

    def get_pressure(self) -> float:
        """
        Read head sensor pressure (SciGlobHSN2 only).

        Returns:
            Pressure in mbar

        Raises:
            SensorError: If sensor type doesn't support pressure
        """
        if self._sensor_type != DeviceType.SCIGLOB_HSN2.value:
            raise SensorError(f"Pressure reading not supported on {self._sensor_type}")

        protocol = HEAD_SENSOR_COMMANDS["pressure"]
        response = self.send_command(protocol.command)

        value = parse_sensor_value(
            response,
            protocol.expected_prefix,
            SENSOR_CONVERSIONS["pressure"]["factor"],
        )

        if value is None:
            return float(SENSOR_CONVERSIONS["pressure"]["error_value"])
        return value

    def get_all_sensors(self) -> dict[str, float]:
        """
        Read all available sensor values.

        Returns:
            Dictionary with sensor readings
        """
        readings = {}

        if self._sensor_type == DeviceType.SCIGLOB_HSN2.value:
            try:
                readings["temperature"] = self.get_temperature()
            except Exception as e:
                self.logger.error(f"Temperature read failed: {e}")
                readings["temperature"] = SENSOR_CONVERSIONS["temperature"]["error_value"]

            try:
                readings["humidity"] = self.get_humidity()
            except Exception as e:
                self.logger.error(f"Humidity read failed: {e}")
                readings["humidity"] = SENSOR_CONVERSIONS["humidity"]["error_value"]

            try:
                readings["pressure"] = self.get_pressure()
            except Exception as e:
                self.logger.error(f"Pressure read failed: {e}")
                readings["pressure"] = SENSOR_CONVERSIONS["pressure"]["error_value"]

        return readings

    def get_version(self) -> str:
        """
        Get firmware version string.

        Returns:
            Version string (e.g., 'V4_C96')
        """
        response = self.send_command("HTv?")
        # Response format: V4_C96 or similar
        return response.strip()

    def get_head_id_number(self) -> int:
        """
        Get head sensor ID number only.

        Returns:
            Head sensor ID as integer
        """
        response = self.send_command("HTI?")
        # Parse HT!<number> response
        if "!" in response:
            try:
                return int(response.split("!")[1].strip())
            except (ValueError, IndexError):
                pass
        return 0

    def set_head_id(self, id_number: int) -> bool:
        """
        Set head sensor ID number.

        The ID will be stored as 'Pan{id_number}HST'.

        Args:
            id_number: New ID number

        Returns:
            True if successful
        """
        response = self.send_command(f"HTI{id_number}")
        return "HT0" in response

    def reset_head_sensor(self) -> bool:
        """
        Reset head sensor (restarts the firmware).

        Returns:
            True if successful
        """
        self.logger.info("Resetting head sensor...")
        response = self.send_command("HTr", timeout=5.0)
        return "HT0" in response

    # =========================================================================
    # Baud Rate Commands
    # =========================================================================

    def get_baudrate(self) -> dict[str, str]:
        """
        Get current baud rate settings.

        Returns:
            Dictionary with baud rate information for different ports
        """
        result = {}

        try:
            response = self.send_command("HTbs?")
            result["computer_to_sensor"] = response.strip()
        except Exception as e:
            result["computer_to_sensor"] = f"Error: {e}"

        try:
            response = self.send_command("HTbt?")
            result["sensor_to_tracker"] = response.strip()
        except Exception as e:
            result["sensor_to_tracker"] = f"Error: {e}"

        return result

    def find_tracker_baudrate(self) -> str:
        """
        Automatically find and match tracker baud rate.

        This command finds the tracker's baud rate and sets the sensor head
        to match it.

        Returns:
            Response string with detected baud rate
        """
        response = self.send_command("HTbm", timeout=5.0)
        return response.strip()

    # =========================================================================
    # Filter Wheel Common Commands
    # =========================================================================

    def get_filterwheel_steps_per_position(self) -> int:
        """
        Get number of steps between filter wheel positions.

        Returns:
            Steps per position (typically 142 for 1S, 150 for 2S, 70 for new driver)
        """
        response = self.send_command("FWn?")
        if "!" in response:
            try:
                return int(response.split("!")[1].strip())
            except (ValueError, IndexError):
                pass
        return 0

    def set_filterwheel_steps_per_position(self, steps: int) -> bool:
        """
        Set number of steps between filter wheel positions.

        Args:
            steps: Steps per position (142 for 1S, 150 for 2S, 70 for new driver)

        Returns:
            True if successful
        """
        response = self.send_command(f"FWn{steps}")
        return "FW0" in response

    def get_filterwheel_speed(self) -> int:
        """
        Get filter wheel motor speed setting.

        Returns:
            Speed value (larger = slower)
        """
        response = self.send_command("FWs?")
        if "!" in response:
            try:
                return int(response.split("!")[1].strip())
            except (ValueError, IndexError):
                pass
        return 0

    def set_filterwheel_speed(self, speed: int) -> bool:
        """
        Set filter wheel motor speed.

        Args:
            speed: Speed value (200 for new board, 100 for old board, 170 for new driver)
                   Larger value = slower speed

        Returns:
            True if successful
        """
        response = self.send_command(f"FWs{speed}")
        return "FW0" in response or "F2m" in response

    # =========================================================================
    # Power Control Commands
    # =========================================================================

    def power_reset(self, device: str) -> bool:
        """
        Power reset a connected device.

        Args:
            device: Device identifier:
                - 'TR' or 'tracker': Tracker
                - 'S1' or 'spectrometer1': Spectrometer 1
                - 'S2' or 'spectrometer2': Spectrometer 2

        Returns:
            True if successful
        """
        # Map device names
        device_map = {
            "tracker": "TR",
            "TR": "TR",
            "spectrometer1": "S1",
            "S1": "S1",
            "spectrometer2": "S2",
            "S2": "S2",
        }

        device_id = device_map.get(device, device)

        # Send power reset command
        if device_id == "TR":
            response = self.send_command("TRs", timeout=TIMING_CONFIG["power_reset_timeout"])
            return "TR0" in response
        else:
            # Generic power reset command format
            response = self.send_command(f"{device_id}s")
            return f"{device_id}0" in response

    def tracker_power_on(self) -> bool:
        """
        Turn on the tracker.

        Returns:
            True if successful
        """
        response = self.send_command("TR1")
        return "TR0" in response

    def tracker_power_off(self) -> bool:
        """
        Turn off the tracker.

        Returns:
            True if successful
        """
        response = self.send_command("TR0")
        return "TR0" in response

    def spectrometer1_power_cycle(self) -> bool:
        """
        Power cycle spectrometer 1.

        Returns:
            True if successful
        """
        response = self.send_command("S1s", timeout=10.0)
        return "S10" in response

    def spectrometer2_power_cycle(self) -> bool:
        """
        Power cycle spectrometer 2.

        Returns:
            True if successful
        """
        response = self.send_command("S2s", timeout=10.0)
        return "S20" in response

    # =========================================================================
    # Spectrometer power-cycle safety hook (v0.0.8.7 crash-class mitigation)
    # =========================================================================

    def set_spec_power_cycle_hook(self, callback: Optional[Callable[[int], None]]) -> None:
        """Register a callback fired *before* a spectrometer relay is cycled.

        The head sensor multiplexes the spectrometer power relays (spec §4.7,
        ``S1s``/``S2s``). Dropping USB power while an attached
        :class:`Spectrometer` still holds a live AVS/USB handle segfaults the
        vendor driver (field incident v0.0.8.7). The coordinator wires the
        Spectrometer's "mark handle dead" routine here so it runs *first*, then
        :meth:`spec_power_cycle` fires the relay.

        Args:
            callback: Callable invoked as ``callback(spec)`` with the 1-based
                spectrometer number just before the ``S<n>s`` relay command is
                written. Pass ``None`` to clear (restores the no-op default).
        """
        with self._lock:
            self._spec_power_cycle_hook = callback

    # Alias per the coordinator's naming convention.
    def register_spec_power_hook(self, callback: Optional[Callable[[int], None]]) -> None:
        """Alias for :meth:`set_spec_power_cycle_hook`."""
        self.set_spec_power_cycle_hook(callback)

    @property
    def spec_power_cycle_hook(self) -> Optional[Callable[[int], None]]:
        """The registered pre-power-cycle callback (``None`` if unset)."""
        return self._spec_power_cycle_hook

    @spec_power_cycle_hook.setter
    def spec_power_cycle_hook(self, callback: Optional[Callable[[int], None]]) -> None:
        with self._lock:
            self._spec_power_cycle_hook = callback

    def spec_power_cycle(self, spec: int) -> bool:
        """Power-cycle a spectrometer relay (``S1s``/``S2s``), safely.

        CRITICAL ordering: if a hook was registered via
        :meth:`set_spec_power_cycle_hook`, it is invoked with ``spec`` **first**
        (so an attached Spectrometer marks its handle dead before USB power
        drops), and only then is the relay command written by delegating to
        :meth:`spectrometer1_power_cycle` / :meth:`spectrometer2_power_cycle`.

        Args:
            spec: Spectrometer number, ``1`` or ``2``.

        Returns:
            True if the relay reported success (``S<n>0``).

        Raises:
            ValueError: If ``spec`` is not 1 or 2.
        """
        if spec not in (1, 2):
            raise ValueError(f"spec must be 1 or 2, got {spec!r}")

        with self._lock:
            # Fire the safety hook BEFORE any relay byte is written. If the hook
            # raises, the exception propagates and the relay is NOT cycled -
            # failing loud is safer than dropping power on a live handle.
            hook = self._spec_power_cycle_hook
            if hook is not None:
                self.logger.info(f"Invoking spectrometer {spec} power-cycle hook before relay")
                hook(spec)

            if spec == 1:
                return self.spectrometer1_power_cycle()
            return self.spectrometer2_power_cycle()

    # =========================================================================
    # Motor diagnostics (HSN2 + LuftBlickTR1; spec §4.5 / §4.6)
    # =========================================================================

    def _parse_alarm(self, response: str, prefix: str) -> tuple[int, str]:
        """Decode an ``MZa?``/``MAa?`` answer into ``(code, message)``.

        Two answer shapes exist (spec §4.5): ``Alarm Code = <N>\\n`` (LuftBlick
        motor-driver alarm, table §6.2) or ``<prefix><code>\\n`` (a head-sensor
        echo code, table §6.1 - e.g. ``MZ5`` = cannot read the tracker driver
        register, the cabling-fault signature).
        """
        raw = response.strip()
        if "=" in raw:
            # "Alarm Code = N" -> split on " = " (spec §4.5 parsing).
            try:
                code = int(raw.split("=")[-1].strip())
            except ValueError:
                return 99, get_error_message(99)
            return code, get_motor_alarm_message(code)
        if raw.startswith(prefix):
            tail = raw[len(prefix) :].strip()
            try:
                code = int(tail)
            except ValueError:
                return 99, get_error_message(99)
            # Head-sensor echo code (table §6.1), not a LuftBlick alarm.
            return code, get_error_message(code)
        return 99, get_error_message(99)

    def get_motor_alarms(self) -> dict[str, tuple[int, str]]:
        """Query zenith and azimuth motor-driver alarms (spec §4.5).

        Sends ``MZa?`` then ``MAa?`` (timeout ``fast_answer_timeout`` = 2 s).
        Nonzero alarms are decoded but never raise here - per field doctrine
        (``blick_serial.py:1040`` "In whatever case, ignore reading result")
        the values are reported for the caller to log/act on.

        Returns:
            ``{'zenith': (code, message), 'azimuth': (code, message)}``.
        """
        timeout = TIMING_CONFIG["fast_answer_timeout"]
        with self._lock:
            zenith = self._parse_alarm(self.send_command("MZa?", timeout=timeout), "MZ")
            azimuth = self._parse_alarm(self.send_command("MAa?", timeout=timeout), "MA")
        return {"zenith": zenith, "azimuth": azimuth}

    def _read_motor_scalar(self, command: str, prefix: str, factor: float) -> float:
        """Read one ``<HW>!<int>\\n`` diagnostic, converting ``int / factor``.

        On any error answer (``<prefix><code>``) the motor error sentinel
        999. is returned (spec §4.6 error values), never an exception - these
        reads are best-effort and must not trigger recovery.
        """
        response = self.send_command(command, timeout=TIMING_CONFIG["sensor_read_timeout"])
        value = parse_sensor_value(response, prefix, factor)
        if value is None:
            return float(SENSOR_CONVERSIONS["motor_temp"]["error_value"])
        return value

    def get_motor_temperatures(self) -> dict[str, float]:
        """Read the four motor/driver temperatures (spec §4.6).

        Commands ``MZd?``/``MZm?``/``MAd?``/``MAm?`` return ``<HW>!<int>\\n``;
        the value is ``int / 10.`` degrees C (timeout ``sensor_read_timeout``
        = 4 s, raised from 2 s in the field because answers straggle). A failed
        read yields the sentinel 999.

        Returns:
            ``{'zenith_driver', 'zenith_motor', 'azimuth_driver',
            'azimuth_motor'}`` -> temperature in degrees C.
        """
        factor = float(SENSOR_CONVERSIONS["motor_temp"]["factor"])  # 10.
        with self._lock:
            return {
                "zenith_driver": self._read_motor_scalar("MZd?", "MZ", factor),
                "zenith_motor": self._read_motor_scalar("MZm?", "MZ", factor),
                "azimuth_driver": self._read_motor_scalar("MAd?", "MA", factor),
                "azimuth_motor": self._read_motor_scalar("MAm?", "MA", factor),
            }

    def get_motor_currents(self) -> dict[str, float]:
        """Read zenith and azimuth motor currents.

        Uses the spec §4.6 tracker-driver-register read grammar
        (``<HW-prefix><read-cmd>?`` -> ``<HW>!<int>\\n``, value = ``int /
        factor``). The field spec enumerates only the temperature read letters
        (``d?`` driver, ``m?`` motor); the current-register read letter ``c?``
        (``MZc?``/``MAc?``) follows the same grammar but is **inferred** and not
        yet hardware-confirmed - it is decoded with the same ``/10.`` scale and
        the same 999. error sentinel as the other driver-register reads. A
        failed read yields the sentinel 999.

        Returns:
            ``{'zenith': current, 'azimuth': current}``.
        """
        factor = float(SENSOR_CONVERSIONS["motor_temp"]["factor"])  # /10. per §4.6 grammar
        with self._lock:
            return {
                "zenith": self._read_motor_scalar("MZc?", "MZ", factor),
                "azimuth": self._read_motor_scalar("MAc?", "MA", factor),
            }

    # =========================================================================
    # Recovery ladder (mirrors the set_tracker escalation; spec §7 / §8)
    # =========================================================================

    def _sleep(self, seconds: float) -> None:
        """Sleep through the transport's hook so simulated holds are scaled.

        SimulatedTransport records the hold as a ``("sleep", seconds)``
        line-event and scales the real delay by ``time_scale`` (0 = instant),
        so time-bounded recovery steps stay testable.
        """
        sleep_fn = getattr(self._connection, "_sleep", time.sleep)
        sleep_fn(seconds)

    def _require_connection(self) -> Any:
        """Return the live transport or raise if disconnected."""
        if not self._connected or self._connection is None:
            raise DeviceError("Not connected to head sensor")
        return self._connection

    def _recover_check_id(self, timeout: Optional[float] = None) -> bool:
        """Recovery step: re-ask ``?`` and confirm the expected ID answers.

        This is both the cheapest recovery step and the verification used after
        every heavier step. Timeout defaults to ``fast_answer_timeout`` (2 s,
        Blick recovery step 1 / ``maxwaits[1]``).

        Returns:
            True if a matching (or plausible SciGlob) ID answered.
        """
        if timeout is None:
            timeout = TIMING_CONFIG["fast_answer_timeout"]
        try:
            answer = self.send_command("?", timeout=timeout).strip()
        except Exception as exc:  # comm loss during recovery is expected
            self.logger.debug(f"recover: check-id failed: {exc}")
            return False
        if not answer:
            return False
        expected = self._device_id or self._expected_sensor_type
        if expected:
            return expected in answer or answer in expected
        return "SciGlob" in answer

    def _recover_reset_pulse(self, hold: Optional[float] = None) -> bool:
        """Recovery step: brief DTR reset pulse (~0.5 s).

        Delegates to the transport's :meth:`reset_pulse` (default hold
        ``esp32_reset_hold`` = 0.5 s). Available as an explicit, individually
        testable last-resort line pulse.
        """
        conn = self._require_connection()
        if hold is None:
            hold = TIMING_CONFIG["esp32_reset_hold"]
        conn.reset_pulse(hold=hold)
        return True

    def _recover_dtr_cycle(self, hold: Optional[float] = None) -> bool:
        """Recovery step: full DTR power cycle (Blick step -1, spec §7).

        Drops DTR, holds ``dtr_cycle_hold`` (3 s, field-verified -
        ``maxwaits[13]``; the Pandora2.0 port's 1 s value is wrong per §11),
        re-asserts, and settles the same 3 s, via the transport's
        :meth:`dtr_cycle`.
        """
        conn = self._require_connection()
        if hold is None:
            hold = TIMING_CONFIG["dtr_cycle_hold"]
        conn.dtr_cycle(hold=hold)
        return True

    def _recover_reopen_port(self, settle: Optional[float] = None) -> bool:
        """Recovery step: close and reopen the port (Blick step -2, spec §7).

        Waits ``port_reopen_settle`` (3 s, ``maxwaits[13]``) between close and
        reopen, via the transport's :meth:`reopen`.
        """
        conn = self._require_connection()
        if settle is None:
            settle = TIMING_CONFIG["port_reopen_settle"]
        conn.reopen(settle=settle)
        return True

    def _recover_peripheral_reset(self) -> bool:
        """Recovery step: tracker soft reset ``TRr`` (spec §4.4 / §7 step -3..-5).

        Timeout ``device_action_timeout`` (12 s, ``maxwaits[3]``). Success is
        the head-sensor OK echo ``TR0``.
        """
        response = self.send_command("TRr", timeout=TIMING_CONFIG["device_action_timeout"])
        return "TR0" in response

    def _recover_power_reset(self) -> bool:
        """Recovery step: tracker power-relay cycle ``TRs`` (spec §4.4 / §7 step 2).

        Timeout ``device_action_timeout`` (12 s, ``maxwaits[3]`` - not the 30 s
        the Pandora2.0 port claims; see §11). Success is ``TR0``.
        """
        response = self.send_command("TRs", timeout=TIMING_CONFIG["device_action_timeout"])
        return "TR0" in response

    def recover(
        self,
        *,
        verify_timeout: Optional[float] = None,
        include_reset_pulse: bool = True,
        wait_retries: int = 1,
    ) -> dict[str, Any]:
        """Run the head-sensor recovery ladder, mirroring set_tracker escalation.

        Escalation order (each heavier step is followed by a ``?`` re-check;
        the ladder stops the moment communication is restored):

        1. re-ask ID (``?``, 2 s)
        2. brief DTR reset pulse (~0.5 s) - only if ``include_reset_pulse``
        3. full DTR power cycle (3 s hold, Blick step -1)
        4. close / reopen port (3 s settle, Blick step -2)
        5. peripheral reset (``TRr``, 12 s)
        6. tracker power reset (``TRs``, 12 s)
        7. wait ``wait_level_delay`` (60 s) and re-check, up to ``wait_retries``
           times (Blick level 4/13/18)

        All sleeps are the field-verified values from ``TIMING_CONFIG``
        (``dtr_cycle_hold`` 3 s, ``port_reopen_settle`` 3 s, ``wait_level_delay``
        60 s) and flow through the transport's sleep hook so simulated runs are
        instantaneous yet recorded.

        Args:
            verify_timeout: Timeout for the ``?`` verification (default 2 s).
            include_reset_pulse: Include the brief DTR reset-pulse step.
            wait_retries: Number of 60 s wait-and-recheck attempts at the end.

        Returns:
            A structured result dict::

                {"recovered": bool, "final_step": Optional[str],
                 "device": str, "steps": [{"step", "action_ok", "verified",
                 "error"}, ...]}

        Raises:
            RecoveryFailed: Only when the entire ladder is exhausted without
                restoring communication.
        """
        with self._lock:
            self._require_connection()
            result: dict[str, Any] = {
                "recovered": False,
                "final_step": None,
                "device": self.name,
                "steps": [],
            }

            def run_step(name: str, action: Callable[[], bool], verify: bool = True) -> bool:
                record: dict[str, Any] = {
                    "step": name,
                    "action_ok": False,
                    "verified": False,
                    "error": None,
                }
                try:
                    record["action_ok"] = bool(action())
                    if verify:
                        record["verified"] = self._recover_check_id(timeout=verify_timeout)
                    else:
                        record["verified"] = bool(record["action_ok"])
                except Exception as exc:
                    record["error"] = str(exc)
                    self.logger.warning(f"recover: step '{name}' raised: {exc}")
                result["steps"].append(record)
                if record["verified"]:
                    result["recovered"] = True
                    result["final_step"] = name
                return bool(record["verified"])

            self.logger.info("Starting head-sensor recovery ladder")

            # Step 1: cheapest - is it already answering?
            if run_step("check_id", lambda: True, verify=True):
                return result
            # Step 2: brief DTR reset pulse (~0.5 s).
            if include_reset_pulse and run_step("reset_pulse", self._recover_reset_pulse):
                return result
            # Step 3: full DTR power cycle (3 s hold).
            if run_step("dtr_cycle", self._recover_dtr_cycle):
                return result
            # Step 4: close / reopen the port (3 s settle).
            if run_step("reopen_port", self._recover_reopen_port):
                return result
            # Step 5: peripheral (tracker) reset.
            if run_step("peripheral_reset", self._recover_peripheral_reset):
                return result
            # Step 6: tracker power-relay cycle.
            if run_step("power_reset", self._recover_power_reset):
                return result
            # Step 7: wait 60 s and re-check, up to wait_retries times.
            def _wait_action() -> bool:
                self._sleep(TIMING_CONFIG["wait_level_delay"])
                return True

            for _ in range(max(0, wait_retries)):
                if run_step("wait_and_retry", _wait_action):
                    return result

            raise RecoveryFailed(
                f"Head-sensor recovery ladder exhausted after "
                f"{len(result['steps'])} steps without restoring communication",
                recovery_level=len(result["steps"]),
                device=self.name,
            )

    def get_status(self) -> dict[str, Any]:
        """
        Get comprehensive status of the Head Sensor.

        Returns:
            Dictionary with status information
        """
        status: dict[str, Any] = {
            "connected": self._connected,
            "port": self.port,
            "device_id": self._device_id,
            "sensor_type": self._sensor_type,
            "tracker_type": self._tracker_type,
        }

        if self._connected and self._sensor_type == DeviceType.SCIGLOB_HSN2.value:
            status["sensors"] = self.get_all_sensors()

        return status


# Realistic canned answers for a SciGlobHSN2 + LuftBlickTR1 head sensor,
# used by the simulation twin. Values mirror the wire grammar in the spec:
# echo codes "<prefix>0" for OK, "<HW>!<int>" for scaled readings.
_SIMULATED_HEAD_SENSOR_ANSWERS: dict[str, str] = {
    "?": "SciGlobHSN2\n",
    "S1s": "S10\n",  # spectrometer 1 relay OK (§4.7)
    "S2s": "S20\n",  # spectrometer 2 relay OK (§4.7)
    "TRr": "TR0\n",  # tracker soft reset OK (§4.4)
    "TRs": "TR0\n",  # tracker power-relay cycle OK (§4.4)
    "MZa?": "Alarm Code = 0\n",  # zenith alarm: none (§4.5 / §6.2)
    "MAa?": "Alarm Code = 0\n",  # azimuth alarm: none
    "MZd?": "MZ!235\n",  # zenith driver temp 23.5 C (§4.6, /10)
    "MZm?": "MZ!247\n",  # zenith motor temp 24.7 C
    "MAd?": "MA!212\n",  # azimuth driver temp 21.2 C
    "MAm?": "MA!229\n",  # azimuth motor temp 22.9 C
    "MZc?": "MZ!158\n",  # zenith motor current (inferred grammar, /10)
    "MAc?": "MA!163\n",  # azimuth motor current
    "HTt?": "HT!2500\n",  # head temp 25.00 C (§4.6, /100)
    "HTh?": "HT!51200\n",  # head humidity 50.0 (/1024)
    "HTp?": "HT!101325\n",  # head pressure 1013.25 hPa (/100)
}


def SimulatedHeadSensor(
    sensor_type: str = "SciGlobHSN2",
    *,
    tracker_type: str = "LuftBlickTR1",
    answers: Optional[dict[str, str]] = None,
    port: str = "SIM_HST",
    connect: bool = True,
    **kwargs: Any,
) -> HeadSensor:
    """Build a hardware-free :class:`HeadSensor` over a SimulatedTransport.

    Wires a :class:`~sciglob.core.simulation.SimulatedTransport` with realistic
    canned answers (:data:`_SIMULATED_HEAD_SENSOR_ANSWERS`) into a real
    ``HeadSensor`` so the full QA/recovery code paths run byte-for-byte without
    a serial port.

    Args:
        sensor_type: Expected sensor type used for the ``?`` answer/validation.
        tracker_type: Tracker type reported by the head sensor.
        answers: Optional command->answer overrides merged over the defaults.
        port: Simulated port name.
        connect: If True, open the transport and connect before returning.
        **kwargs: Forwarded to the :class:`HeadSensor` constructor.

    Returns:
        A ``HeadSensor`` bound to the simulated transport.
    """
    from sciglob.core.simulation import SimulatedTransport

    mapping: dict[str, Any] = dict(_SIMULATED_HEAD_SENSOR_ANSWERS)
    mapping["?"] = f"{sensor_type}\n"
    if answers:
        mapping.update(answers)

    # Stateful responder: fixed answers first, then the variable-argument
    # command families (moves, filter wheels, shadowband) with position
    # readback for TRw/TRm. Field wire order is azimuth-first (az,ze).
    state = {"az": 0, "ze": 0}

    def responder(data: bytes) -> str:
        text = data.decode("latin-1", errors="ignore")
        cmd = text[:-1] if text.endswith("\r") else text
        if cmd in mapping:
            answer = mapping[cmd]
            return str(answer() if callable(answer) else answer)
        if cmd.startswith("TRb"):
            try:
                az, ze = cmd[3:].split(",")
                state["az"], state["ze"] = int(az), int(ze)
            except (ValueError, IndexError):
                pass
            return "TR0\n"
        if cmd.startswith("TRp"):
            try:
                state["az"] = int(cmd[3:])
            except ValueError:
                pass
            return "TR0\n"
        if cmd.startswith("TRt"):
            try:
                state["ze"] = int(cmd[3:])
            except ValueError:
                pass
            return "TR0\n"
        if cmd in ("TRw", "TRm"):
            return f"TRh{state['az']},{state['ze']}\n"
        if cmd.startswith("F1"):
            return "F10\n"
        if cmd.startswith("F2"):
            return "F20\n"
        if cmd.startswith("SB"):
            return "SB0\n"
        if cmd.startswith("MB"):
            return "MB0\n"
        if cmd.startswith("MA"):
            return "MA0\n"
        if cmd.startswith("MZ"):
            return "MZ0\n"
        if cmd.startswith("TR"):
            return "TR0\n"
        if cmd.startswith("HT"):
            return "HT0\n"
        return "\n"

    transport = SimulatedTransport(
        responder=responder,
        port=port,
        owner="SimulatedHeadSensor",
    )
    hs = HeadSensor(
        sensor_type=sensor_type,
        tracker_type=tracker_type,
        connection=transport,
        **kwargs,
    )
    if connect:
        hs.connect()
    return hs
