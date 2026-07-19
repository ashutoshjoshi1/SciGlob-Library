"""SBHS ESP32 JSON sensor box (SciGlob Spec-Box Humidity Sensor, Hardware type 3).

This module implements the ESP32/JSON generation of the SBHS box and provides the
shared machinery (JSON record parsing, the last-complete-record read loop, the
~10 s record cache and the ESP32 reset-pulse policy) that :mod:`sciglob.devices.asb`
reuses for the ASB box.

Wire protocol (spec-file "SBHS / ASB ESP32 JSON Sensor Protocol"):
    * §1  9600 8N1, non-blocking reads, latin-1 wire encoding, question
      terminator ``\\r``, answer terminator ``\\r\\n``.
    * §2  ESP32 open doctrine: ``esp32_safe=True`` -> ``dsrdtr=False`` with DTR/RTS
      held asserted; never pulse reset lines on a normal open.
    * §3  Commands ``v`` (identify), ``T``/``H``/``P`` (each returns the *full*
      JSON record); answers are ``\\r\\n``-terminated JSON lines.
    * §3.3  Parse the *last complete* JSON object in the buffer (stale fragments
      from timed-out earlier reads may precede it).
    * §4  Identification (v0.0.8.11 field lesson): match the hardware-type
      signature (``"Hardware":N``) FIRST, configured device_id substring SECOND;
      an empty/None configured id must still identify via ``Hardware":N``.
    * §5  Error 98 = wrong hardware type on port; 99 = low-level serial.

Example:
    >>> from sciglob.devices.sbhs import SimulatedSBHS
    >>> sbhs = SimulatedSBHS()
    >>> sbhs.connect()
    >>> round(sbhs.get_temperature(), 1)
    23.5
    >>> sbhs.disconnect()
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from sciglob.core.base import BaseDevice
from sciglob.core.connection import POLL_INTERVAL, WIRE_ENCODING, SerialConnection
from sciglob.core.exceptions import (
    CommunicationError,
    ConnectionError,
    DeviceIdentityError,
    SensorError,
)
from sciglob.core.help_mixin import HelpMixin
from sciglob.core.protocols import ESP32_SENSOR_ERROR_MESSAGES, TIMING_CONFIG, SerialConfig
from sciglob.core.simulation import SimulatedTransport, make_responder

# Wire terminators (spec §1): questions end with a bare CR, ESP32 answers with CRLF.
QUESTION_END_CHAR = "\r"
ANSWER_END = "\r\n"

# Error codes from ESP32_SENSOR_ERROR_MESSAGES (spec §5.1 / protocols.py:90-99).
ERR_WRONG_ID = 1
ERR_HUMIDITY_PARSE = 3
ERR_TEMPERATURE_PARSE = 4
ERR_PRESSURE_PARSE = 5
ERR_WRONG_HARDWARE = 98
ERR_LOW_LEVEL_SERIAL = 99

# Consecutive read failures before an automatic reset pulse is attempted
# (spec §8.1: "on a 3rd consecutive read failure").
MAX_CONSECUTIVE_FAILURES = 3


def _to_float(value: Any) -> Optional[float]:
    """Coerce a JSON scalar to float, or None when absent/unparseable."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    """Return every complete top-level JSON object found in ``text``, in order.

    Uses :meth:`json.JSONDecoder.raw_decode` scanning so that a leading stale
    fragment (an incomplete object from a timed-out earlier read) or arbitrary
    junk between records is skipped without discarding the valid records that
    follow it (spec §3.3).
    """
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    index = 0
    length = len(text)
    while index < length:
        brace = text.find("{", index)
        if brace < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, brace)
        except json.JSONDecodeError:
            index = brace + 1
            continue
        if isinstance(obj, dict):
            objects.append(obj)
        index = end
    return objects


def _is_sensor_record(obj: dict[str, Any]) -> bool:
    """True for a box JSON answer (spec §3.2).

    A normal record carries the ``Hardware`` type field; the ``Sensors`` array
    and ``UUID`` are also accepted so the configured-id fallback (spec §4, used
    when the hardware field is absent) still sees a complete object.
    """
    return "Hardware" in obj or "Sensors" in obj or "UUID" in obj


@dataclass(frozen=True)
class SensorEntry:
    """One entry of the JSON ``Sensors`` array (BME280 or MPRLS)."""

    id: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None


@dataclass(frozen=True)
class SensorRecord:
    """A parsed ESP32 JSON sensor record with the monotonic time it was read."""

    hardware: int
    firmware: int
    uuid: str
    sensors: tuple[SensorEntry, ...]
    acquired_monotonic: float
    raw: dict[str, Any] = field(default_factory=dict)

    def sensor(self, sensor_id: str) -> Optional[SensorEntry]:
        """Return the first sensor entry whose ID matches (case-insensitive)."""
        target = sensor_id.upper()
        for entry in self.sensors:
            if entry.id.upper() == target:
                return entry
        return None

    @property
    def bme280(self) -> Optional[SensorEntry]:
        """First BME280 entry (dual-BME280 ASB records expose two)."""
        for entry in self.sensors:
            if entry.id.upper().startswith("BME280"):
                return entry
        return None


class ESP32JsonSensor(BaseDevice, HelpMixin):
    """Shared base for the ESP32/JSON SBHS and ASB sensor boxes.

    Subclasses set :attr:`HARDWARE_TYPE` (3 = SBHS, 4 = ASB). All transport and
    shared-state access is guarded by the per-device reentrant lock inherited
    through the connection plus this class's own ``self._lock``.
    """

    HARDWARE_TYPE: int = -1

    _device_name = "ESP32JsonSensor"
    _device_description = "ESP32 JSON sensor box (SBHS/ASB)"
    _supported_types = ["SBHS", "ASB"]
    _default_config = {
        "baudrate": 9600,
        "framing": "8N1",
        "answer_terminator": "\\r\\n",
        "esp32_safe": True,
    }
    _command_reference = {
        "v": "Identify (returns JSON incl. 'Hardware' field)",
        "T": "Temperature (returns full JSON record)",
        "H": "Humidity (returns full JSON record)",
        "P": "Pressure (returns full JSON record)",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        device_id: Optional[str] = None,
        timeout: float = TIMING_CONFIG["esp32_answer_timeout"],
        cache_ttl: float = TIMING_CONFIG["esp32_record_cache"],
        name: str = "ESP32JsonSensor",
        config: Optional[Any] = None,
        serial_config: Optional[SerialConfig] = None,
        connection: Optional[SerialConnection] = None,
    ):
        """Initialize the sensor box.

        Args:
            port: Serial port path (e.g. ``COM7``).
            baudrate: Communication speed (spec §1: 9600).
            device_id: Optional configured id used only as an identification
                fallback when the ``Hardware`` field is absent (spec §4).
            timeout: Per-question answer window in seconds (spec §2/§6: ~8 s).
            cache_ttl: Seconds a JSON record is served for sibling quantities
                (spec §6: ~10 s).
            name: Device name for logging and the port registry.
            config: Optional device-config object exposing ``.serial`` /
                ``.device_id`` (duck-typed).
            serial_config: Explicit serial configuration.
            connection: Injected SerialConnection-compatible transport (e.g.
                :class:`~sciglob.core.simulation.SimulatedTransport`) so tests
                and the facade can run hardware-free.
        """
        if config is not None:
            ser = getattr(config, "serial", None)
            if ser is not None:
                port = getattr(ser, "port", None) or port
                baudrate = getattr(ser, "baudrate", baudrate)
                serial_config = serial_config or ser
            cfg_id = getattr(config, "device_id", None)
            if cfg_id and device_id is None:
                device_id = cfg_id

        if serial_config is not None:
            port = serial_config.port or port
            baudrate = serial_config.baudrate

        super().__init__(port=port, baudrate=baudrate, timeout=timeout, name=name)

        self._configured_id = device_id or ""
        self.cache_ttl = cache_ttl
        # Field-verified ESP32 doctrine values (spec §2/§6, protocols.py:308-309).
        self.reset_hold = TIMING_CONFIG["esp32_reset_hold"]
        self.reset_throttle = TIMING_CONFIG["esp32_reset_throttle"]

        self._serial_config = serial_config or SerialConfig(baudrate=baudrate)
        self._injected_connection = connection
        self._record: Optional[SensorRecord] = None
        self._consecutive_failures = 0
        self._last_auto_reset_monotonic: Optional[float] = None

    # -- connection management ------------------------------------------

    @property
    def connection(self) -> Optional[SerialConnection]:
        """The active (or injected) transport, or None before construction."""
        conn: Optional[SerialConnection] = self._connection
        return conn or self._injected_connection

    def connect(self) -> None:
        """Open the port (ESP32-safe) and identify the box.

        The port is opened with ``esp32_safe=True`` so DTR/RTS are held
        asserted and reset lines are never pulsed at open time (spec §2).
        Identification runs immediately; a wrong hardware type raises
        :class:`DeviceIdentityError` with error code 98.
        """
        if self._connected:
            self.logger.warning("Already connected")
            return

        conn = self._injected_connection
        if conn is None:
            if self.port is None:
                raise ConnectionError("No port specified")
            conn = SerialConnection(
                port=self.port,
                config=self._serial_config,
                owner=self.name,
                esp32_safe=True,  # spec §2: dsrdtr=False, DTR/RTS asserted
            )
        self._connection = conn

        try:
            if not conn.is_open:
                conn.open()
            self.identify()
            self._connected = True
            self.logger.info(f"Connected to {self.name} on {self.port}")
        except Exception:
            # Release the port so a retry (or a different device) can claim it.
            try:
                conn.close()
            except Exception:
                pass
            self._connection = None
            raise

    def disconnect(self) -> None:
        """Close the transport (safe to call when already disconnected)."""
        conn = self._connection
        if conn is not None:
            try:
                conn.close()
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.error(f"Error during disconnect: {exc}")
            finally:
                self._connection = None
                self._connected = False
                self._record = None

    def _require_open(self) -> SerialConnection:
        conn: Optional[SerialConnection] = self._connection
        if conn is None or not conn.is_open:
            raise ConnectionError(f"{self.name} is not connected")
        return conn

    # -- low-level read -------------------------------------------------

    def _query_last_record(self, command: str) -> dict[str, Any]:
        """Send ``command`` and return the last complete JSON record read.

        Reads within the ~8 s answer window (spec §2/§6) and returns as soon as
        at least one complete, structurally valid record is present, taking the
        *last* one so a leading stale fragment is ignored (spec §3.3). On
        failure the consecutive-failure counter is advanced and, at the 3rd
        strike, a throttled automatic reset pulse is attempted (spec §8.1).
        """
        conn = self._require_open()
        with self._lock_for(conn):
            conn.drain()
            conn.write((command + QUESTION_END_CHAR).encode(WIRE_ENCODING, errors="ignore"))

            deadline = time.monotonic() + self.timeout
            buffer = ""
            while True:
                chunk = conn.read_buffer()
                if chunk:
                    buffer += chunk.decode(WIRE_ENCODING, errors="ignore")
                    records = [
                        obj for obj in extract_json_objects(buffer) if _is_sensor_record(obj)
                    ]
                    if records:
                        self._consecutive_failures = 0
                        return records[-1]
                if time.monotonic() > deadline:
                    break
                time.sleep(POLL_INTERVAL)

            self._consecutive_failures += 1
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                self._maybe_auto_reset_pulse()
            raise CommunicationError(
                f"No valid JSON record from {self.port} within {self.timeout}s "
                f"(command {command!r}, buffer {buffer!r}): "
                f"{ESP32_SENSOR_ERROR_MESSAGES[ERR_LOW_LEVEL_SERIAL]}",
                error_code=ERR_LOW_LEVEL_SERIAL,
            )

    @staticmethod
    def _lock_for(conn: SerialConnection) -> Any:
        """Return the connection's reentrant lock (guards transport access)."""
        return conn._lock  # per-connection RLock (connection.py:135)

    def _build_record(self, raw: dict[str, Any]) -> SensorRecord:
        sensors: list[SensorEntry] = []
        for entry in raw.get("Sensors", []) or []:
            if not isinstance(entry, dict):
                continue
            sensors.append(
                SensorEntry(
                    id=str(entry.get("ID", "")),
                    temperature=_to_float(entry.get("Temperature")),
                    humidity=_to_float(entry.get("Humidity")),
                    pressure=_to_float(entry.get("Pressure")),
                )
            )
        try:
            hardware = int(raw.get("Hardware", -1))
        except (TypeError, ValueError):
            hardware = -1
        try:
            firmware = int(raw.get("Firmware", -1))
        except (TypeError, ValueError):
            firmware = -1
        return SensorRecord(
            hardware=hardware,
            firmware=firmware,
            uuid=str(raw.get("UUID", "")),
            sensors=tuple(sensors),
            acquired_monotonic=time.monotonic(),
            raw=raw,
        )

    # -- identification -------------------------------------------------

    def identify(self) -> dict[str, Any]:
        """Send ``v`` and validate the answering box.

        Order (v0.0.8.11 field lesson, spec §4):
            1. hardware-type signature ``"Hardware":N`` first;
            2. configured device_id substring second (only when the hardware
               field is absent).

        Returns:
            The raw identify record.

        Raises:
            DeviceIdentityError: wrong hardware type (code 98) or unidentifiable
                answer (code 1).
        """
        raw = self._query_last_record("v")
        hardware = raw.get("Hardware")

        # 1) Hardware-type signature first (works even with an empty configured id).
        if hardware == self.HARDWARE_TYPE:
            record = self._build_record(raw)
            if record.bme280 is not None:
                self._record = record
            return raw

        # A hardware field is present but is the wrong type -> code 98.
        if hardware is not None:
            raise DeviceIdentityError(
                f"Wrong hardware type on {self.port}: expected {self.HARDWARE_TYPE}, "
                f"got {hardware} ({ESP32_SENSOR_ERROR_MESSAGES[ERR_WRONG_HARDWARE]})",
                answer=json.dumps(raw),
                error_code=ERR_WRONG_HARDWARE,
            )

        # 2) Configured-id fallback only when the hardware type cannot be read.
        if self._configured_id and self._configured_id in json.dumps(raw):
            return raw

        raise DeviceIdentityError(
            f"{ESP32_SENSOR_ERROR_MESSAGES[ERR_WRONG_ID]} on {self.port}",
            answer=json.dumps(raw),
            error_code=ERR_WRONG_ID,
        )

    # -- readings -------------------------------------------------------

    def get_record(self, force: bool = False, command: str = "T") -> SensorRecord:
        """Return the current sensor record, served from the ~10 s cache.

        Args:
            force: Bypass the cache and query the box.
            command: Command to send when a fresh read is needed (any of
                ``T``/``H``/``P`` returns the full record; spec §3.3.6).
        """
        conn = self._require_open()
        with self._lock_for(conn):
            cached = self._record
            if (
                not force
                and cached is not None
                and (time.monotonic() - cached.acquired_monotonic) < self.cache_ttl
            ):
                return cached
            record = self._build_record(self._query_last_record(command))
            self._record = record
            return record

    def _bme280_or_raise(self) -> SensorEntry:
        entry = self.get_record().bme280
        if entry is None:
            raise SensorError(
                f"No BME280 entry in record from {self.port}",
                error_code=ERR_WRONG_ID,
            )
        return entry

    def get_temperature(self) -> float:
        """Temperature in degrees C from the cached BME280 record."""
        value = self._bme280_or_raise().temperature
        if value is None:
            raise SensorError(
                ESP32_SENSOR_ERROR_MESSAGES[ERR_TEMPERATURE_PARSE],
                error_code=ERR_TEMPERATURE_PARSE,
            )
        return value

    def get_humidity(self) -> float:
        """Relative humidity in % from the cached BME280 record."""
        value = self._bme280_or_raise().humidity
        if value is None:
            raise SensorError(
                ESP32_SENSOR_ERROR_MESSAGES[ERR_HUMIDITY_PARSE],
                error_code=ERR_HUMIDITY_PARSE,
            )
        return value

    def get_pressure(self) -> float:
        """Barometric pressure in hPa from the cached BME280 record."""
        value = self._bme280_or_raise().pressure
        if value is None:
            raise SensorError(
                ESP32_SENSOR_ERROR_MESSAGES[ERR_PRESSURE_PARSE],
                error_code=ERR_PRESSURE_PARSE,
            )
        return value

    def send_command(self, command: str) -> Optional[str]:
        """Send a raw command and return the last JSON record as a string."""
        return json.dumps(self._query_last_record(command))

    # -- ESP32 reset pulse (explicit recovery only) ---------------------

    def reset_pulse(self) -> None:
        """Fire an explicit ESP32 reset pulse (recovery action, spec §2/§8.1).

        Drops DTR (EN low, IO0 high) for 0.5 s then re-asserts, booting the
        module into its application firmware. This is an *explicit* recovery
        action and is not throttled; automatic firings go through
        :meth:`_maybe_auto_reset_pulse` and are throttled to >= 600 s apart.
        """
        conn = self._require_open()
        with self._lock_for(conn):
            conn.reset_pulse(hold=self.reset_hold)

    def _maybe_auto_reset_pulse(self) -> bool:
        """Fire an automatic reset pulse if the >= 600 s throttle allows it.

        Returns:
            True if a pulse was fired, False if throttled or not open.
        """
        conn = self._connection
        if conn is None or not conn.is_open:
            return False
        now = time.monotonic()
        last = self._last_auto_reset_monotonic
        if last is not None and (now - last) < self.reset_throttle:
            self.logger.warning(
                "Automatic reset pulse suppressed (throttled to "
                f">= {self.reset_throttle}s between firings)"
            )
            return False
        with self._lock_for(conn):
            conn.reset_pulse(hold=self.reset_hold)
        self._last_auto_reset_monotonic = now
        return True


class SBHS(ESP32JsonSensor):
    """SciGlob Spec-Box Humidity Sensor (ESP32/JSON, Hardware type 3).

    Example:
        >>> sbhs = SBHS(port="COM7")           # doctest: +SKIP
        >>> sbhs.connect()                     # doctest: +SKIP
        >>> sbhs.get_temperature()             # doctest: +SKIP
    """

    HARDWARE_TYPE = 3

    _device_name = "SBHS"
    _device_description = "SciGlob Spec-Box Humidity Sensor (ESP32 JSON, Hardware type 3)"
    _supported_types = ["SBHS"]

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        device_id: Optional[str] = None,
        timeout: float = TIMING_CONFIG["esp32_answer_timeout"],
        cache_ttl: float = TIMING_CONFIG["esp32_record_cache"],
        name: str = "SBHS",
        config: Optional[Any] = None,
        serial_config: Optional[SerialConfig] = None,
        connection: Optional[SerialConnection] = None,
    ):
        super().__init__(
            port=port,
            baudrate=baudrate,
            device_id=device_id,
            timeout=timeout,
            cache_ttl=cache_ttl,
            name=name,
            config=config,
            serial_config=serial_config,
            connection=connection,
        )


# -- simulation helpers -------------------------------------------------


def make_sbhs_responder(
    temperature: float = 23.5,
    humidity: float = 45.2,
    pressure: float = 1013.2,
    firmware: int = 3,
    uuid: str = "SBHS-SIM-0001",
    hardware: int = 3,
) -> Any:
    """Build a responder emitting a realistic SBHS JSON record for v/T/H/P.

    The record is a single ``\\r\\n``-terminated JSON line matching the spec §3.2
    example (one BME280 entry).
    """
    record = {
        "Hardware": hardware,
        "Firmware": firmware,
        "UUID": uuid,
        "Sensors": [
            {
                "ID": "BME280",
                "Temperature": temperature,
                "Humidity": humidity,
                "Pressure": pressure,
            }
        ],
    }
    line = json.dumps(record) + ANSWER_END
    mapping: dict[str, Any] = {"v": line, "T": line, "H": line, "P": line}
    return make_responder(mapping, end_char=QUESTION_END_CHAR)


def SimulatedSBHS(
    port: str = "SIM_SBHS",
    device_id: Optional[str] = None,
    temperature: float = 23.5,
    humidity: float = 45.2,
    pressure: float = 1013.2,
    firmware: int = 3,
    uuid: str = "SBHS-SIM-0001",
    time_scale: float = 0.0,
) -> SBHS:
    """Return an :class:`SBHS` wired to a scripted :class:`SimulatedTransport`.

    The returned device is not yet connected; call ``connect()``.
    """
    transport = SimulatedTransport(
        responder=make_sbhs_responder(
            temperature=temperature,
            humidity=humidity,
            pressure=pressure,
            firmware=firmware,
            uuid=uuid,
        ),
        port=port,
        owner="SBHS",
        esp32_safe=True,
        time_scale=time_scale,
    )
    return SBHS(port=port, device_id=device_id, connection=transport)
