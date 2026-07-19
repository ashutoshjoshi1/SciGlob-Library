"""Temperature Controller interface for TETech devices."""

import threading
from typing import TYPE_CHECKING, Any, Optional

from sciglob.core.base import BaseDevice

if TYPE_CHECKING:
    from sciglob.config import TemperatureControllerConfig
from sciglob.core.connection import SerialConnection
from sciglob.core.exceptions import CommunicationError, ConnectionError, DeviceError
from sciglob.core.help_mixin import HelpMixin
from sciglob.core.protocols import TETECH_PROTOCOL, TIMING_CONFIG, SerialConfig
from sciglob.core.utils import dec2hex, get_checksum, hex2dec
from sciglob.devices import _tetech1090


class TemperatureController(BaseDevice, HelpMixin):
    """
    Temperature Controller interface for TETech devices.

    Supports TETech1 (16-bit), TETech2 (32-bit) and TETech1090 controllers.

    Protocol (TETech1/2):
    - Commands: "*<cmd><hex_value><checksum>"
    - Response ends with "^"
    - Hex values are signed (two's complement)

    Protocol (TETech1090):
    - ``#``-framed: "#" + address "000000" + payload + CRC + CR
    - CRC-16/XMODEM over the frame body (spec §4)
    - Values are IEEE-754 float32 as 8 hex chars
    - Answers ("!"-framed) end with CR

    Example:
        >>> tc = TemperatureController(port="/dev/ttyUSB0", controller_type="TETech1")
        >>> tc.connect()
        >>> tc.set_temperature(25.0)
        >>> print(f"Current temp: {tc.get_temperature()}°C")
        >>> tc.disconnect()

    Help:
        >>> tc.help()              # Show full help
        >>> tc.list_methods()      # List all methods
    """

    # HelpMixin properties
    _device_name = "TemperatureController"
    _device_description = "TETech temperature controller interface"
    _supported_types = ["TETech1 (16-bit)", "TETech2 (32-bit)", "TETech1090 (#-framed float32)"]
    _default_config = {
        "baudrate": "9600 (TETech1/2) or 19200 (TETech1090)",
        "conversion_factor": "10 (TETech1) or 100 (TETech2); float32 (TETech1090)",
        "protocol": "Hex with checksum, ends with ^ (1/2); #-framed CRC-16/XMODEM (1090)",
    }
    _command_reference = {
        "1c": "Set temperature (TETech1/2)",
        "1d": "Set proportional bandwidth (TETech1/2)",
        "1e": "Set integral gain (TETech1/2)",
        "30/2d": "Enable output (TETech1/2)",
        "5065": "Read set temperature (TETech1/2)",
        "0161": "Read control sensor temp (TETech1/2)",
        "0261": "Read secondary sensor temp (TETech1/2)",
        "VS0BB801": "Set target temperature (TETech1090)",
        "VS07DA01": "Enable output (TETech1090)",
        "?VR03E801": "Read object temperature (TETech1090)",
        "?VR03E901": "Read sink temperature (TETech1090)",
    }

    # Controller families this class understands.
    _VALID_TYPES = ("TETech1", "TETech2", "TETech1090")

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 1.0,
        name: str = "TempController",
        controller_type: str = "TETech1",
        config: Optional["TemperatureControllerConfig"] = None,
        serial_config: Optional[SerialConfig] = None,
        connection: Optional[SerialConnection] = None,
    ):
        """
        Initialize the Temperature Controller.

        Args:
            port: Serial port path
            baudrate: Communication speed (default 9600; 19200 typical for TETech1090)
            timeout: Command timeout
            name: Device name for logging
            controller_type: "TETech1" (16-bit), "TETech2" (32-bit) or "TETech1090"
            config: TemperatureControllerConfig object
            serial_config: SerialConfig object for port settings
            connection: Pre-built SerialConnection-compatible transport to inject
                (e.g. a SimulatedTransport) so the controller runs hardware-free.
        """
        # Whether the caller supplied an explicit baud rate; TETech1090 defaults
        # to 19200 only when the caller left the shared 9600 default untouched.
        baud_given = baudrate != 9600

        # If config object provided, use its values
        if config is not None:
            port = config.serial.port or port
            baudrate = config.serial.baudrate
            timeout = config.serial.timeout or timeout
            controller_type = config.controller_type
            baud_given = True

        # If serial_config provided, use its values
        if serial_config is not None:
            port = serial_config.port or port
            baudrate = serial_config.baudrate
            timeout = serial_config.timeout or timeout
            baud_given = True

        if controller_type not in self._VALID_TYPES:
            raise ValueError("controller_type must be 'TETech1', 'TETech2' or 'TETech1090'")

        if controller_type == "TETech1090" and not baud_given:
            baudrate = _tetech1090.DEFAULT_BAUDRATE

        super().__init__(port=port, baudrate=baudrate, timeout=timeout, name=name)

        self._controller_type = controller_type
        self._injected_connection = connection
        # Per-device reentrant lock guarding transport / shared-state access.
        self._lock = threading.RLock()

        self._protocol: dict[str, Any]
        if controller_type == "TETech1090":
            # TETech1090 constants live in the _tetech1090 helper module; the
            # shared TETECH_PROTOCOL dict (core) is intentionally not touched.
            self._protocol = {
                "connection_test": _tetech1090.IDENTIFY_FRAME,
                "end_char": _tetech1090.END_CHAR,
                "nbits": 32,
            }
        else:
            self._protocol = TETECH_PROTOCOL[controller_type]
        self._nbits: int = self._protocol["nbits"]

    @property
    def controller_type(self) -> str:
        """Get the controller type."""
        return self._controller_type

    @property
    def nbits(self) -> int:
        """Get the bit width (16 or 32)."""
        return self._nbits

    def connect(self) -> None:
        """Connect to the temperature controller."""
        if self._connected:
            self.logger.warning("Already connected")
            return

        if self._injected_connection is None and self.port is None:
            raise ConnectionError("No port specified")

        try:
            if self._injected_connection is not None:
                self._connection = self._injected_connection
            else:
                config = SerialConfig(baudrate=self.baudrate)
                self._connection = SerialConnection(port=self.port, config=config)
            if not self._connection.is_open:
                self._connection.open()

            # Verify connection
            if not self._verify_connection():
                raise DeviceError("Failed to verify temperature controller connection")

            self._connected = True
            self.logger.info(f"Connected to {self._controller_type} on {self.port}")

        except Exception as e:
            self.disconnect()
            raise ConnectionError(f"Failed to connect: {e}") from e

    def _verify_connection(self) -> bool:
        """Verify connection by sending ID query."""
        try:
            test_cmd = self._protocol["connection_test"]
            response = self._query(test_cmd)
            return len(response) > 0
        except Exception:
            return False

    def disconnect(self) -> None:
        """Disconnect from the temperature controller."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
            finally:
                self._connection = None
                self._connected = False

    def _build_command(self, cmd: str, value: Optional[int] = None) -> str:
        """
        Build a TETech command string.

        Args:
            cmd: Command code
            value: Optional value (will be converted to hex)

        Returns:
            Complete command string with checksum
        """
        if value is not None:
            hex_value = dec2hex(value, self._nbits)
            if self._controller_type == "TETech1":
                cmd_str = f"{cmd}{hex_value}"
            else:
                # TETech2 uses longer format
                cmd_str = f"00{cmd}{hex_value}"
        else:
            cmd_str = cmd

        checksum = get_checksum(cmd_str)
        return f"*{cmd_str}{checksum}"

    def _query(self, command: str) -> str:
        """
        Send command and get response.

        Args:
            command: Command string

        Returns:
            Response string (without end character)
        """
        # Guard on the connection object only: connect() calls _verify_connection()
        # (which calls _query) before _connected is set to True, so checking
        # self._connected here would make every connection attempt fail.
        if self._connection is None:
            raise DeviceError("Not connected")

        end_char = self._protocol["end_char"]

        # Send command
        self._connection.send_command(command, end_char="\r")

        # Read until end character. TC SET/GET operations use the 12 s action
        # timeout (Blick maxwaits[3]); a 1 s default times out on real devices
        # whose float32 answers straggle just past a second (spec §5).
        response: bytes = self._connection.read_until(
            terminator=end_char.encode(),
            timeout=TIMING_CONFIG["device_action_timeout"],
        )

        return response.decode("latin-1").rstrip(end_char)

    def _parse_response(self, response: str, factor: float) -> float:
        """
        Parse hex response to float value.

        Args:
            response: Hex response string
            factor: Conversion factor

        Returns:
            Converted float value
        """
        # Check for error response
        if "XXXX" in response:
            raise CommunicationError("TETech error response")

        # Real TETech1/2 answers are framed "*<hex><checksum>^"; _query strips
        # the trailing "^" but the leading "*" control char remains. Strip it
        # (tolerantly — no-op when absent) before extracting the hex value,
        # otherwise int("*00c4", 16) raises ValueError on every real GET.
        text = response[1:] if response.startswith("*") else response

        # Extract hex value (remove checksum - last 2 chars)
        if len(text) > 2:
            hex_value = text[:-2]
            dec_value = hex2dec(hex_value, self._nbits)
            return dec_value / factor

        return 0.0

    def send_command(self, command: str) -> Optional[str]:
        """Send raw command."""
        return self._query(command)

    # -- TETech1090 (#-framed, CRC-16/XMODEM, float32) helpers --------------

    def _require_1090(self, method: str) -> None:
        """Raise unless this controller is a TETech1090."""
        if self._controller_type != "TETech1090":
            raise DeviceError(f"{method} is only supported on TETech1090 controllers")

    def _query_1090(self, payload: str) -> str:
        """Frame a TETech1090 payload, send it and return the raw answer.

        The complete question is ``#000000`` + payload + CRC + CR (spec §4.1).
        """
        frame = _tetech1090.build_frame(payload)
        with self._lock:
            return self._query(frame)

    def _set_1090(self, command: str, value_hex: str) -> bool:
        """Send a TETech1090 SET command and confirm the echoed CRC (spec §4.6).

        The device answers the exact string ``!000000`` + the question's CRC.
        """
        payload = command + value_hex
        answer = self._query_1090(payload)
        expected = _tetech1090.expected_set_answer(payload)
        if answer.strip("\r\n") != expected:
            self.logger.error(
                f"TETech1090 SET {command} failed: expected {expected!r}, got {answer!r}"
            )
            return False
        return True

    def _get_1090(self, command: str) -> float:
        """Send a TETech1090 GET command and decode the float32 answer (spec §4.6)."""
        answer = self._query_1090(command)
        return _tetech1090.parse_get_answer(answer)

    def set_temperature(self, temperature: float) -> bool:
        """
        Set target temperature.

        Args:
            temperature: Target temperature in °C

        Returns:
            True if successful
        """
        if self._controller_type == "TETech1090":
            self.logger.info(f"Setting temperature to {temperature} degC")
            # VS0BB801 + IEEE-754 float32 (spec §4.3/§4.4)
            return self._set_1090(_tetech1090.CMD_SET_TEMP, _tetech1090.float_to_hex8(temperature))

        write_cmds = self._protocol["write_commands"]
        cmd_info = write_cmds["ST"]

        value = int(temperature * cmd_info["factor"])
        command = self._build_command(cmd_info["cmd"], value)

        self.logger.info(f"Setting temperature to {temperature}°C")
        response = self._query(command)

        # Verify the response echoes the value
        return "XXXX" not in response

    def get_temperature(self) -> float:
        """
        Get control sensor temperature.

        Returns:
            Temperature in °C
        """
        read_cmds = self._protocol["read_commands"]
        cmd_info = read_cmds["T1"]

        command = f"*{cmd_info['cmd']}"
        response = self._query(command)

        return self._parse_response(response, cmd_info["factor"])

    def get_secondary_temperature(self) -> float:
        """
        Get secondary sensor temperature.

        Returns:
            Temperature in °C
        """
        read_cmds = self._protocol["read_commands"]
        cmd_info = read_cmds["T2"]

        command = f"*{cmd_info['cmd']}"
        response = self._query(command)

        return self._parse_response(response, cmd_info["factor"])

    def get_setpoint(self) -> float:
        """
        Get current temperature setpoint.

        Returns:
            Setpoint temperature in °C
        """
        if self._controller_type == "TETech1090":
            # ?VR0BB801 -> object-temperature setpoint (spec §4.3)
            return self._get_1090(_tetech1090.CMD_GET_SETPOINT)

        read_cmds = self._protocol["read_commands"]
        cmd_info = read_cmds["ST"]

        command = f"*{cmd_info['cmd']}"
        response = self._query(command)

        return self._parse_response(response, cmd_info["factor"])

    def set_bandwidth(self, bandwidth: float) -> bool:
        """
        Set proportional bandwidth (PID parameter).

        Args:
            bandwidth: Bandwidth value

        Returns:
            True if successful
        """
        write_cmds = self._protocol["write_commands"]
        cmd_info = write_cmds["BW"]

        value = int(bandwidth * cmd_info["factor"])
        command = self._build_command(cmd_info["cmd"], value)

        response = self._query(command)
        return "XXXX" not in response

    def set_integral_gain(self, gain: float) -> bool:
        """
        Set integral gain (PID parameter).

        Args:
            gain: Integral gain value

        Returns:
            True if successful
        """
        write_cmds = self._protocol["write_commands"]
        cmd_info = write_cmds["IG"]

        value = int(gain * cmd_info["factor"])
        command = self._build_command(cmd_info["cmd"], value)

        response = self._query(command)
        return "XXXX" not in response

    def enable_output(self) -> bool:
        """
        Enable temperature control output.

        Returns:
            True if successful
        """
        if self._controller_type == "TETech1090":
            # VS07DA01 + integer 1 (spec §4.3/§4.4)
            return self._set_1090(_tetech1090.CMD_ENABLE_OUTPUT, _tetech1090.int_hex(1))

        write_cmds = self._protocol["write_commands"]
        cmd_info = write_cmds["EO"]

        command = self._build_command(cmd_info["cmd"], 1)
        response = self._query(command)
        return "XXXX" not in response

    def disable_output(self) -> bool:
        """
        Disable temperature control output.

        Returns:
            True if successful
        """
        if self._controller_type == "TETech1090":
            # VS07DA01 + integer 0 (spec §4.3/§4.4)
            return self._set_1090(_tetech1090.CMD_ENABLE_OUTPUT, _tetech1090.int_hex(0))

        write_cmds = self._protocol["write_commands"]
        cmd_info = write_cmds["EO"]

        command = self._build_command(cmd_info["cmd"], 0)
        response = self._query(command)
        return "XXXX" not in response

    def get_object_temperature(self) -> float:
        """Get the object (control) temperature — TETech1090 only.

        Reads register ``?VR03E801`` (param 1000, spec §4.3).

        Returns:
            Object temperature in °C.
        """
        self._require_1090("get_object_temperature")
        return self._get_1090(_tetech1090.CMD_GET_OBJECT_TEMP)

    def get_sink_temperature(self) -> float:
        """Get the heat-sink (secondary) temperature — TETech1090 only.

        Reads register ``?VR03E901`` (param 1001, spec §4.3).

        Returns:
            Sink temperature in °C.
        """
        self._require_1090("get_sink_temperature")
        return self._get_1090(_tetech1090.CMD_GET_SINK_TEMP)

    def get_proportional_bandwidth(self) -> float:
        """Get the proportional bandwidth (PB) in user units.

        For TETech1090 the device stores proportional gain Kp; this reads
        ``?VR0BC201`` and converts PB = 1/Kp (spec §4.5). For TETech1/2 the
        bandwidth register is read directly.

        Returns:
            Proportional bandwidth (0 if the device reports Kp == 0).
        """
        if self._controller_type == "TETech1090":
            kp = self._get_1090(_tetech1090.CMD_GET_KP)
            return 1.0 / kp if kp != 0 else 0.0

        read_cmds = self._protocol["read_commands"]
        cmd_info = read_cmds["BW"]
        response = self._query(f"*{cmd_info['cmd']}")
        return self._parse_response(response, cmd_info["factor"])

    def get_integral_gain(self) -> float:
        """Get the integral gain (Ki) in user units.

        For TETech1090 the device stores proportional gain Kp and integral
        time Ti; this reads ``?VR0BC201`` and ``?VR0BC301`` and converts
        Ki = Kp/Ti (spec §4.5). For TETech1/2 the integral-gain register is
        read directly.

        Returns:
            Integral gain (0 if the device reports Ti == 0).
        """
        if self._controller_type == "TETech1090":
            kp = self._get_1090(_tetech1090.CMD_GET_KP)
            ti = self._get_1090(_tetech1090.CMD_GET_TI)
            return kp / ti if ti != 0 else 0.0

        read_cmds = self._protocol["read_commands"]
        cmd_info = read_cmds["IG"]
        response = self._query(f"*{cmd_info['cmd']}")
        return self._parse_response(response, cmd_info["factor"])

    def set_pid(
        self,
        bandwidth: float,
        integral_gain: float,
        derivative_gain: Optional[float] = None,
    ) -> bool:
        """Set the PID parameters in user units (proportional bandwidth + Ki).

        For TETech1090 the user units are converted to the device's native
        Kp/Ti representation (spec §4.5):

        * Kp = 1/PB (``VS0BC201``)
        * Ti = 1/(PB·Ki) (``VS0BC301``); Ti = 0 disables the integral term
        * optional Kd (``VS0BC401``) is sent verbatim when provided

        For TETech1/2 the bandwidth and integral gain are sent directly via
        the family's scaled-integer write commands.

        Args:
            bandwidth: Proportional bandwidth (PB) in °C.
            integral_gain: Integral gain (Ki).
            derivative_gain: Optional derivative gain (Kd); TETech1090 only.

        Returns:
            True if every write was acknowledged.
        """
        if self._controller_type == "TETech1090":
            kp = 1.0 / bandwidth if bandwidth != 0 else 0.0  # Kp = 1/PB (spec §4.5)
            ok = self._set_1090(_tetech1090.CMD_SET_KP, _tetech1090.float_to_hex8(kp))
            # Ti = Kp/Ki = 1/(PB*Ki); 0 disables the integral term (spec §4.5).
            ti = (
                1.0 / (bandwidth * integral_gain)
                if (bandwidth != 0 and integral_gain != 0)
                else 0.0
            )
            ok = self._set_1090(_tetech1090.CMD_SET_TI, _tetech1090.float_to_hex8(ti)) and ok
            if derivative_gain is not None:
                ok = (
                    self._set_1090(
                        _tetech1090.CMD_SET_KD, _tetech1090.float_to_hex8(derivative_gain)
                    )
                    and ok
                )
            return ok

        if derivative_gain is not None:
            raise DeviceError("derivative_gain is only supported on TETech1090 controllers")
        ok = self.set_bandwidth(bandwidth)
        ok = self.set_integral_gain(integral_gain) and ok
        return ok

    def get_status(self) -> dict[str, Any]:
        """Get temperature controller status."""
        status = {
            "connected": self._connected,
            "controller_type": self._controller_type,
            "port": self.port,
        }

        if self._connected:
            try:
                if self._controller_type == "TETech1090":
                    status["object_temperature"] = self.get_object_temperature()
                    status["sink_temperature"] = self.get_sink_temperature()
                    status["setpoint"] = self.get_setpoint()
                else:
                    status["temperature"] = self.get_temperature()
                    status["setpoint"] = self.get_setpoint()
                    status["secondary_temperature"] = self.get_secondary_temperature()
            except Exception as e:
                status["error"] = str(e)

        return status


class _Simulated1090Responder:
    """Stateful responder emulating a TETech1090 over a SimulatedTransport.

    Answers are built with the real framing/CRC helpers (spec §4), so the
    device object exercises its genuine encode/validate paths. Writes update
    an in-memory register bank that subsequent reads observe.
    """

    def __init__(
        self,
        setpoint: float = 20.0,
        object_temp: float = 19.6,
        sink_temp: float = 23.4,
        kp: float = 2.0,
        ti: float = 40.0,
        device_type: int = 1089,
    ):
        self._values: dict[str, float] = {
            _tetech1090.CMD_GET_SETPOINT: setpoint,
            _tetech1090.CMD_GET_OBJECT_TEMP: object_temp,
            _tetech1090.CMD_GET_SINK_TEMP: sink_temp,
            _tetech1090.CMD_GET_KP: kp,
            _tetech1090.CMD_GET_TI: ti,
        }
        self._device_type = device_type
        self.output_enabled = False

    def _frame(self, value_hex: str) -> str:
        body = _tetech1090.ANSWER_PREFIX + _tetech1090.ADDRESS + value_hex
        return body + _tetech1090.crc_hex(body) + _tetech1090.END_CHAR

    def __call__(self, data: bytes) -> Optional[str]:
        frame = data.decode(_tetech1090.WIRE_TEXT).rstrip(_tetech1090.END_CHAR)
        prefix = _tetech1090.CONTROL_CHAR + _tetech1090.ADDRESS
        if not frame.startswith(prefix) or len(frame) < len(prefix) + 4:
            return None
        q_crc = frame[-4:]
        payload = frame[len(prefix) : -4]

        # Identify / device-type query -> integer answer (spec §4.4).
        if payload == _tetech1090.CMD_QUERY_DEVICE_TYPE:
            return self._frame(_tetech1090.int_hex(self._device_type))

        # Writes: echo the question CRC after "!000000" (spec §4.6).
        if payload.startswith("VS"):
            command, value_hex = payload[:8], payload[8:]
            if command == _tetech1090.CMD_SET_TEMP:
                self._values[_tetech1090.CMD_GET_SETPOINT] = _tetech1090.hex8_to_float(value_hex)
            elif command == _tetech1090.CMD_SET_KP:
                self._values[_tetech1090.CMD_GET_KP] = _tetech1090.hex8_to_float(value_hex)
            elif command == _tetech1090.CMD_SET_TI:
                self._values[_tetech1090.CMD_GET_TI] = _tetech1090.hex8_to_float(value_hex)
            elif command == _tetech1090.CMD_ENABLE_OUTPUT:
                self.output_enabled = int(value_hex, 16) != 0
            return _tetech1090.ANSWER_PREFIX + _tetech1090.ADDRESS + q_crc + _tetech1090.END_CHAR

        # Reads: float32 answer (spec §4.4).
        if payload in self._values:
            return self._frame(_tetech1090.float_to_hex8(self._values[payload]))

        # Anything else -> device error frame (spec §4.6).
        body = _tetech1090.ANSWER_PREFIX + _tetech1090.ADDRESS + "+05"
        return body + _tetech1090.crc_hex(body) + _tetech1090.END_CHAR


def SimulatedTemperatureController1090(
    port: str = "SIM_TEC1090",
    name: str = "TempController1090",
    setpoint: float = 20.0,
    object_temp: float = 19.6,
    sink_temp: float = 23.4,
    kp: float = 2.0,
    ti: float = 40.0,
    connect: bool = True,
) -> TemperatureController:
    """Build a TETech1090 controller backed by an in-memory simulated transport.

    Runs the full question/answer/CRC code paths hardware-free.

    Args:
        port: Simulated port name (must be unique per open transport).
        name: Device / logger name.
        setpoint: Initial setpoint the sim reports (°C).
        object_temp: Initial object temperature (°C).
        sink_temp: Initial sink temperature (°C).
        kp: Initial proportional gain the device stores.
        ti: Initial integral time the device stores.
        connect: Open + identify immediately when True.

    Returns:
        A ready-to-use :class:`TemperatureController` in TETech1090 mode.
    """
    from sciglob.core.simulation import SimulatedTransport

    responder = _Simulated1090Responder(
        setpoint=setpoint,
        object_temp=object_temp,
        sink_temp=sink_temp,
        kp=kp,
        ti=ti,
    )
    transport = SimulatedTransport(responder=responder, port=port, owner=name)
    controller = TemperatureController(
        port=port,
        name=name,
        controller_type="TETech1090",
        connection=transport,
    )
    if connect:
        controller.connect()
    return controller
