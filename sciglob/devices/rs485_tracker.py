"""Direct RS-485 Oriental Motor AZ / AZD Modbus RTU tracker backend.

This module talks to two Oriental Motor AZ/AZD stepper drivers over a single
half-duplex RS-485 bus using Modbus RTU. Wire constants are mined from the
field-proven ``oriental_motor_modbus.py`` driver family; every non-obvious
value cites the section of the RS-485 tracker spec it comes from.

Bus topology (spec section 3):
    * slave 1 -> Zenith (elevation axis)
    * slave 2 -> Azimuth

The public :class:`RS485Tracker` mirrors the head-sensor ``Tracker`` facade
(``move_to`` / ``move_to_steps`` / ``home`` / ``get_position`` /
``check_alarms`` / ``get_status``) so callers can swap backends. Unlike the
head-sensor tracker, the RS-485 methods return typed result objects and never
raise on a *device-reported* failure (alarm active, home not reached, ...).
Exceptions are reserved for *transport* failures (no reply, bad CRC, Modbus
exception frame).

Example:
    >>> from sciglob.devices.rs485_tracker import SimulatedRS485Tracker
    >>> trk = SimulatedRS485Tracker()
    >>> trk.connect()
    >>> trk.get_position()
    (0.0, 0.0)
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

from sciglob.core.connection import SerialConnection
from sciglob.core.exceptions import CommunicationError, ConnectionError, TrackerError
from sciglob.core.protocols import MOTOR_ALARM_MESSAGES, SerialConfig

# --------------------------------------------------------------------------
# Modbus function codes (spec section 2.2)
# --------------------------------------------------------------------------
FC_READ_HOLDING = 0x03  # Read Holding Registers
FC_WRITE_SINGLE = 0x06  # Write Single Register
FC_WRITE_MULTIPLE = 0x10  # Write Multiple Registers

# --------------------------------------------------------------------------
# Register map (spec section 4) -- addresses are 16-bit register indices.
# 32-bit values span a big-endian pair: addr = high word, addr+1 = low word.
# --------------------------------------------------------------------------
REG_SOFTWARE_VERSION = 0x0058  # 4.1: SW version (R) / direct-data block start (W)
REG_COMMAND_WORD = 0x007D  # 4.2: remote I/O input command word (16-bit RW)
REG_STATUS_WORD = 0x007F  # 4.3: remote I/O output status word (16-bit R)
REG_ALARM = 0x0080  # 4.4: present alarm code (32-bit R, use low byte)
REG_FEEDBACK_POSITION = 0x00CC  # 4.5: feedback position (32-bit R, signed, negated)
REG_DRIVER_TEMP = 0x00F8  # 4.5: driver temperature (x0.1 C)
REG_MOTOR_TEMP = 0x00FA  # 4.5: motor temperature (x0.1 C)
REG_VOLTAGE = 0x00FC  # 4.5: DC supply voltage (x0.1 V)

# Command word 0x007D bit map (spec section 4.2)
CMD_START = 0x0008  # begin positioning
CMD_HOME = 0x0010  # return to home / ZHOME
CMD_STOP = 0x0020  # immediate stop
CMD_FREE = 0x0040  # motor de-energised
CMD_ALM_RST = 0x0080  # alarm reset

# Status word 0x007F bit map (spec section 4.3)
ST_HOME_END = 0x0010  # homing complete
ST_READY = 0x0020  # driver ready
ST_ALM_A = 0x0080  # alarm active
ST_MOVE = 0x0800  # motor moving

# Direct-data operation block (spec sections 4.10 / 6.3)
OP_TYPE_ABSOLUTE = 1  # type 1 = absolute positioning
DIRECT_TRIGGER_REFLECT_ALL = 1  # trigger 1 = reflect-all, start without START pulse
DIRECT_DATA_REG_COUNT = 16  # 8 x 32-bit fields written collectively at 0x0058

# Motion defaults (spec section 5)
DEFAULT_SPEED_HZ = 3000
DEFAULT_ACCEL = 1000  # ms/kHz
DEFAULT_DECEL = 1000  # ms/kHz
DEFAULT_CURRENT_PCT = 50.0  # operating current, encoded x10, clamped 0..1000

# Temperature monitor sanity ceiling (spec 4.5): raw > 2000 (i.e. > 200.0 C)
# is treated as an invalid read -> None.
_TEMP_INVALID_RAW = 2000

# Steps per degree default (spec section 5 / open question Q5): configurable
# per axis, depends on electronic-gear settings.
DEFAULT_STEPS_PER_DEG = 100.0

# --------------------------------------------------------------------------
# Alarm-code table (spec section 7.1) -- authoritative for the direct-RS485
# backend. Codes are the low byte of the 0x0080 register. Note: the core
# ``MOTOR_ALARM_MESSAGES`` table is the *decimal* LuftBlick numbering for the
# head-sensor-mediated legacy path (spec 7.2) and uses a different meaning per
# code, so it is only consulted as a last-resort fallback for codes absent
# from this table.
# --------------------------------------------------------------------------
RS485_ALARM_MESSAGES: dict[int, str] = {
    0x00: "No alarm",
    0x21: "Heat sink overheat (driver)",
    0x22: "Motor overheat / sensor error",
    0x23: "Main circuit overheat",
    0x25: "Over temperature warning",
    0x28: "Overvoltage",
    0x2A: "Main power off",
    0x30: "Overcurrent",
    0x31: "Overload",
    0x33: "Overspeed",
    0x34: "Deviation counter overflow",
    0x35: "Pulse input overflow",
    0x36: "Positioning error",
    0x37: "Position range exceeded",
    0x40: "EEPROM error",
    0x41: "Sensor error",
    0x42: "Return-to-home incomplete",
    0x43: "Motor connection error",
    0x44: "Sensor disconnection",
    0x45: "Motor combination error",
    0x46: "ABZO sensor error",
    0x47: "ABZO multi-turn error",
    0x48: "ABZO sensor communication error",
    0x4A: "Electromagnetic brake error",
    0x50: "External stop input",
    0x51: "Network communication error",
    0x52: "RS-485 communication error",
    0x53: "RS-485 communication timeout",
    0x60: "Operation data error",
    0x61: "Parameter setting error",
    0x62: "System error",
    0x63: "Command error",
    0x81: "Network watchdog timer error",
    0xF0: "CPU peripheral circuit error",
}


def alarm_message(code: int) -> str:
    """Return the human-readable text for an AZ/AZD alarm code (spec 7.1)."""
    if code in RS485_ALARM_MESSAGES:
        return RS485_ALARM_MESSAGES[code]
    if code in MOTOR_ALARM_MESSAGES:  # fallback (different numbering, spec 7.2)
        return MOTOR_ALARM_MESSAGES[code]
    return f"Unknown (0x{code:02X})"


# --------------------------------------------------------------------------
# CRC-16/Modbus (spec section 2.1) -- poly 0xA001, init 0xFFFF, LSB-first,
# appended little-endian (lo, hi).
# --------------------------------------------------------------------------
def modbus_crc16(data: bytes) -> int:
    """Compute the CRC-16/Modbus of ``data``.

    Args:
        data: Bytes to checksum.

    Returns:
        The 16-bit CRC as an integer (append little-endian on the wire).
    """
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc


def append_crc(payload: bytes) -> bytes:
    """Append the little-endian CRC-16/Modbus to ``payload`` (spec 1.4 step 1)."""
    return payload + modbus_crc16(payload).to_bytes(2, "little")


def check_crc(frame: bytes) -> bool:
    """Return True if the trailing 2 bytes are a valid CRC for ``frame``."""
    if len(frame) < 3:
        return False
    body, crc = frame[:-2], frame[-2:]
    return modbus_crc16(body).to_bytes(2, "little") == crc


# --------------------------------------------------------------------------
# Frame builders (spec section 2.3)
# --------------------------------------------------------------------------
def _u16(value: int) -> tuple[int, int]:
    """Split a 16-bit value into (high, low) bytes."""
    value &= 0xFFFF
    return (value >> 8) & 0xFF, value & 0xFF


def _u32_words(value: int) -> tuple[int, int]:
    """Split a 32-bit value into big-endian (high word, low word).

    Negative values are encoded two's-complement (spec 2.4).
    """
    value &= 0xFFFFFFFF
    return (value >> 16) & 0xFFFF, value & 0xFFFF


def build_read_frame(slave: int, addr: int, count: int) -> bytes:
    """Build an FC 0x03 read-holding-registers request (spec 2.3)."""
    ah, al = _u16(addr)
    ch, cl = _u16(count)
    return append_crc(bytes([slave, FC_READ_HOLDING, ah, al, ch, cl]))


def build_write_single_frame(slave: int, addr: int, value: int) -> bytes:
    """Build an FC 0x06 write-single-register request (spec 2.3)."""
    ah, al = _u16(addr)
    vh, vl = _u16(value)
    return append_crc(bytes([slave, FC_WRITE_SINGLE, ah, al, vh, vl]))


def build_write_multiple_frame(slave: int, addr: int, values: list[int]) -> bytes:
    """Build an FC 0x10 write-multiple-registers request (spec 2.3)."""
    count = len(values)
    ah, al = _u16(addr)
    ch, cl = _u16(count)
    body = bytearray([slave, FC_WRITE_MULTIPLE, ah, al, ch, cl, count * 2])
    for v in values:
        vh, vl = _u16(v)
        body += bytes([vh, vl])
    return append_crc(bytes(body))


def _to_signed32(value: int) -> int:
    """Interpret a 32-bit unsigned value as signed two's-complement."""
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


# --------------------------------------------------------------------------
# Typed result objects (public methods return these; they never raise on a
# device-reported failure).
# --------------------------------------------------------------------------
@dataclass
class AlarmStatus:
    """A single axis alarm reading."""

    axis: str
    slave_id: int
    code: int
    active: bool
    message: str


@dataclass
class MoveResult:
    """Outcome of a move command."""

    ok: bool
    zenith_steps: Optional[int] = None
    azimuth_steps: Optional[int] = None
    message: str = ""


@dataclass
class HomeResult:
    """Outcome of a homing command."""

    ok: bool
    zenith_home_end: bool = False
    azimuth_home_end: bool = False
    message: str = ""


@dataclass
class AxisStatus:
    """Full status snapshot for one axis."""

    axis: str
    slave_id: int
    status_word: int
    ready: bool
    moving: bool
    home_end: bool
    alarm_active: bool
    alarm_code: int
    alarm_message: str
    position_steps: int
    driver_temp_c: Optional[float]
    motor_temp_c: Optional[float]
    voltage_v: Optional[float]


@dataclass
class _AxisConfig:
    """Per-axis wiring (slave id + steps/degree)."""

    name: str
    slave_id: int
    steps_per_deg: float = DEFAULT_STEPS_PER_DEG


# --------------------------------------------------------------------------
# The tracker
# --------------------------------------------------------------------------
class RS485Tracker:
    """Two-axis Oriental Motor AZ/AZD tracker over direct RS-485 Modbus RTU.

    Both axes share one serial handle and therefore one lock (spec section 9):
    all Modbus transactions serialize on ``self._lock`` so interleaved
    zenith/azimuth traffic never corrupts the half-duplex bus.

    Args:
        port: Serial port name (ignored when ``connection`` is injected).
        baudrate: Bus baud rate (spec 1.1 field value: 9600).
        timeout: Per-transaction read timeout in seconds (spec 1.1: 0.5 s).
        name: Logger/device name.
        zenith_slave: Modbus slave id of the zenith axis (spec 3: default 1).
        azimuth_slave: Modbus slave id of the azimuth axis (spec 3: default 2).
        zenith_steps_per_deg: Steps per degree for zenith (spec 5, configurable).
        azimuth_steps_per_deg: Steps per degree for azimuth.
        serial_config: Optional SerialConfig overriding the derived one.
        connection: Injected SerialConnection-compatible transport (simulation).
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 0.5,
        name: str = "RS485Tracker",
        zenith_slave: int = 1,
        azimuth_slave: int = 2,
        zenith_steps_per_deg: float = DEFAULT_STEPS_PER_DEG,
        azimuth_steps_per_deg: float = DEFAULT_STEPS_PER_DEG,
        serial_config: Optional[SerialConfig] = None,
        connection: Optional[SerialConnection] = None,
        echo: bool = False,
        motion_start_grace: float = 1.0,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.name = name
        # Half-duplex 2-wire adapters echo the transmitted frame back before the
        # response (spec 8.4). Whether an adapter echoes is adapter-dependent;
        # set echo=True for a bus that echoes so the echo is read and discarded.
        self.echo = echo
        # How long to wait for a move/home to visibly start (MOVE set / READY
        # drop) before treating a still-READY axis as already-at-target. Keeps
        # a genuinely instantaneous move from waiting the whole timeout.
        self._motion_start_grace = motion_start_grace
        self.logger = logging.getLogger(f"sciglob.{name}")

        # Modbus RTU link parameters (spec 1.1): EVEN parity, 1 stop bit.
        self._serial_config = serial_config or SerialConfig(
            port=port, baudrate=baudrate, parity="E", stopbits=1, timeout=timeout
        )

        self.zenith = _AxisConfig("zenith", zenith_slave, zenith_steps_per_deg)
        self.azimuth = _AxisConfig("azimuth", azimuth_slave, azimuth_steps_per_deg)

        # One bus-wide lock for both axes (spec section 9).
        self._lock = threading.RLock()
        self._injected_connection = connection
        self._connection: Optional[SerialConnection] = None
        self._connected = False

    # -- connection lifecycle ------------------------------------------

    @property
    def is_connected(self) -> bool:
        """True when the bus transport is open."""
        return self._connected

    def connect(self) -> None:
        """Open the RS-485 bus (or use the injected transport)."""
        with self._lock:
            if self._connected:
                self.logger.warning("Already connected")
                return
            conn = self._injected_connection
            if conn is None:
                if self.port is None:
                    raise ConnectionError("No port specified")
                conn = SerialConnection(
                    port=self.port, config=self._serial_config, owner=self.name
                )
            if not conn.is_open:
                conn.open()
            self._connection = conn
            self._connected = True
            self.logger.info(f"RS-485 tracker connected on {self.port or 'injected transport'}")

    def disconnect(self) -> None:
        """Close the transport."""
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception as exc:  # pragma: no cover - defensive
                    self.logger.error(f"Error during disconnect: {exc}")
                finally:
                    self._connection = None
                    self._connected = False

    def __enter__(self) -> "RS485Tracker":
        self.connect()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.disconnect()

    # -- low-level Modbus transactions ---------------------------------

    def _transact(self, request: bytes, response_len: int) -> bytes:
        """Send a framed request and read one CRC-checked response frame.

        The response is read incrementally (slave + function code first) so a
        short Modbus exception frame is decoded correctly instead of blocking
        for the longer normal-response length (which the old fixed-length read
        did — the exception branch was unreachable). When ``self.echo`` is set,
        the half-duplex echo of the request is read and discarded first
        (spec 8.4).

        Raises:
            CommunicationError: On transport failure (no reply, bad CRC) or a
                device Modbus exception frame -- never on a device-reported
                motion/alarm state (those are returned by higher-level methods).
        """
        if self._connection is None:
            raise ConnectionError("Not connected")
        with self._lock:
            self._connection.write_frame(request)
            if self.echo:
                echo = self._connection.read_exact(len(request), timeout=self.timeout)
                if echo != request:
                    self.logger.warning(
                        "RS-485 echo mismatch on slave %d: sent %r, echoed %r",
                        request[0],
                        request,
                        echo,
                    )
            # Read the frame header: slave address + function code.
            head = self._connection.read_exact(2, timeout=self.timeout)
            if head[1] & 0x80:
                # Modbus exception frame: fc|0x80, 1-byte exception code, CRC16.
                frame = head + self._connection.read_exact(3, timeout=self.timeout)
                if not check_crc(frame):
                    raise CommunicationError(f"Bad exception-frame CRC: {frame!r}")
                exc_code = frame[2]
                raise CommunicationError(
                    f"Modbus exception on slave {request[0]}: code 0x{exc_code:02X}",
                    error_code=exc_code,
                )
            frame = head + self._connection.read_exact(
                response_len - 2, timeout=self.timeout
            )
        if not check_crc(frame):
            raise CommunicationError(f"Bad response CRC: {frame!r}")
        return frame

    def read_regs(self, slave: int, addr: int, count: int) -> list[int]:
        """FC 0x03: read ``count`` holding registers, CRC-verified (spec 2.3)."""
        request = build_read_frame(slave, addr, count)
        # response = slave + fc + byte_count + 2*count data + 2 CRC
        resp = self._transact(request, 5 + 2 * count)
        if resp[0] != slave or resp[1] != FC_READ_HOLDING or resp[2] != count * 2:
            raise CommunicationError(f"Malformed FC03 response: {resp!r}")
        regs = []
        for i in range(count):
            hi = resp[3 + i * 2]
            lo = resp[4 + i * 2]
            regs.append((hi << 8) | lo)
        return regs

    def write_reg(self, slave: int, addr: int, value: int) -> None:
        """FC 0x06: write a single register, verifying the echo (spec 2.3)."""
        request = build_write_single_frame(slave, addr, value)
        resp = self._transact(request, 8)
        if resp[0] != slave or resp[1] != FC_WRITE_SINGLE:
            raise CommunicationError(f"No ACK for FC06 write: {resp!r}")

    def write_regs(self, slave: int, addr: int, values: list[int]) -> None:
        """FC 0x10: write multiple registers (spec 2.3)."""
        request = build_write_multiple_frame(slave, addr, values)
        resp = self._transact(request, 8)
        if resp[0] != slave or resp[1] != FC_WRITE_MULTIPLE:
            raise CommunicationError(f"No ACK for FC10 write: {resp!r}")

    def read_u32(self, slave: int, addr: int, signed: bool = False) -> int:
        """Read a 32-bit big-endian value across a register pair (spec 2.4)."""
        regs = self.read_regs(slave, addr, 2)
        value = (regs[0] << 16) | regs[1]
        return _to_signed32(value) if signed else value

    def write_u32(self, slave: int, addr: int, value: int) -> None:
        """Write a 32-bit big-endian value across a register pair (spec 2.4)."""
        hi, lo = _u32_words(value)
        self.write_regs(slave, addr, [hi, lo])

    # -- axis primitives -----------------------------------------------

    def _status_word(self, slave: int) -> int:
        """Read the 16-bit status word 0x007F (spec 4.3)."""
        return self.read_regs(slave, REG_STATUS_WORD, 1)[0]

    def _alarm_code(self, slave: int) -> int:
        """Read the present alarm code (low byte of 0x0080, spec 4.4)."""
        return self.read_u32(slave, REG_ALARM) & 0xFF

    def _feedback_steps(self, slave: int) -> int:
        """Read the feedback position in user steps (spec 4.5 / 5).

        The wire value is signed and negated on read: user-facing positive
        equals the negated wire value.
        """
        return -self.read_u32(slave, REG_FEEDBACK_POSITION, signed=True)

    def _direct_move_block(
        self, position_steps: int, speed: int, accel: int, decel: int, current_pct: float
    ) -> list[int]:
        """Build the 16-register direct-data block (spec 6.3).

        Layout at 0x0058: data_no=0, op_type=1 (absolute), position (signed,
        negated for motor convention), speed, accel, decel, current x10,
        trigger=1.
        """
        wire_pos = -position_steps  # negate for motor convention (spec 5)
        current_raw = max(0, min(1000, int(round(current_pct * 10))))  # x10, clamp 0..1000
        pos_hi, pos_lo = _u32_words(wire_pos)
        spd_hi, spd_lo = _u32_words(speed)
        acc_hi, acc_lo = _u32_words(accel)
        dec_hi, dec_lo = _u32_words(decel)
        cur_hi, cur_lo = _u32_words(current_raw)
        return [
            0,
            0,  # data_no
            0,
            OP_TYPE_ABSOLUTE,  # op type = 1 (absolute)
            pos_hi,
            pos_lo,  # position
            spd_hi,
            spd_lo,  # speed (Hz)
            acc_hi,
            acc_lo,  # accel (ms/kHz)
            dec_hi,
            dec_lo,  # decel (ms/kHz)
            cur_hi,
            cur_lo,  # operating current (x0.1 %)
            0,
            DIRECT_TRIGGER_REFLECT_ALL,  # trigger = 1
        ]

    def _move_axis_steps(
        self,
        slave: int,
        steps: int,
        speed: int,
        accel: int,
        decel: int,
        current_pct: float,
    ) -> None:
        """Command an absolute move on one axis via the direct-data block."""
        # Pre-move safety (spec 6.1 / 8.4): pulse STOP to abort any in-progress
        # motion, then clear the command word, before writing new motion data.
        self.write_reg(slave, REG_COMMAND_WORD, CMD_STOP)
        self.write_reg(slave, REG_COMMAND_WORD, 0x0000)
        block = self._direct_move_block(steps, speed, accel, decel, current_pct)
        self.write_regs(slave, REG_SOFTWARE_VERSION, block)

    def _start_home_axis(self, slave: int) -> None:
        """Pulse the HOME command bit on one axis (spec 6.5 / 4.2)."""
        self.write_reg(slave, REG_COMMAND_WORD, CMD_HOME)
        self.write_reg(slave, REG_COMMAND_WORD, 0x0000)

    def _stop_axis(self, slave: int) -> None:
        """Pulse the STOP command bit then clear (spec 6.1)."""
        self.write_reg(slave, REG_COMMAND_WORD, CMD_STOP)
        self.write_reg(slave, REG_COMMAND_WORD, 0x0000)

    def _reset_alarm_axis(self, slave: int) -> None:
        """Pulse the ALM-RST command bit then clear (spec 6.1 / 8.1)."""
        self.write_reg(slave, REG_COMMAND_WORD, CMD_ALM_RST)
        self.write_reg(slave, REG_COMMAND_WORD, 0x0000)

    def _wait_motion_complete(self, slave: int, timeout: float, poll: float = 0.05) -> bool:
        """Poll 0x007F until the move starts and then settles (spec 6.6).

        Guards against the "settled on the first poll" bug: a freshly commanded
        axis is still READY with MOVE clear for a moment before it starts. We
        wait to observe motion (MOVE set) before accepting READY-and-not-MOVE as
        completion. If motion is never observed within ``motion_start_grace``
        (a genuinely instantaneous move, or an already-at-target command), we
        accept the settled state rather than block for the whole timeout.

        Returns:
            True if motion settled cleanly; False on timeout or active alarm.
        """
        deadline = time.monotonic() + timeout
        grace_deadline = time.monotonic() + min(timeout, self._motion_start_grace)
        started = False
        while time.monotonic() < deadline:
            status = self._status_word(slave)
            if status & ST_ALM_A:
                return False
            moving = bool(status & ST_MOVE)
            settled = bool(status & ST_READY) and not moving
            if moving:
                started = True
            if started and settled:
                return True
            if not started and settled and time.monotonic() > grace_deadline:
                # Never saw motion start within the grace window: treat as
                # already at target (fast/no-op move).
                return True
            time.sleep(poll)
        return False

    def _wait_home_complete(self, slave: int, timeout: float, poll: float = 0.05) -> bool:
        """Poll 0x007F until homing starts and then completes (spec 6.5 / 6.6).

        Guards against a stale HOME-END bit from a previous homing: we wait for
        the drive to first leave READY (homing motion started) before accepting
        READY-and-HOME-END as completion, with the same grace fallback as
        :meth:`_wait_motion_complete` for an instantaneous simulator/device.
        """
        deadline = time.monotonic() + timeout
        grace_deadline = time.monotonic() + min(timeout, self._motion_start_grace)
        saw_busy = False
        while time.monotonic() < deadline:
            status = self._status_word(slave)
            if status & ST_ALM_A:
                return False
            ready = bool(status & ST_READY)
            home_end = bool(status & ST_HOME_END)
            if not ready:
                saw_busy = True
            if (saw_busy or time.monotonic() > grace_deadline) and ready and home_end:
                return True
            time.sleep(poll)
        return False

    # -- public facade (matches head-sensor Tracker) -------------------

    def get_position_steps(self) -> tuple[int, int]:
        """Get current feedback position in steps.

        Returns:
            (zenith_steps, azimuth_steps)
        """
        with self._lock:
            zen = self._feedback_steps(self.zenith.slave_id)
            azi = self._feedback_steps(self.azimuth.slave_id)
        return zen, azi

    def get_position(self) -> tuple[float, float]:
        """Get current position in degrees.

        Returns:
            (zenith_degrees, azimuth_degrees)
        """
        zen_steps, azi_steps = self.get_position_steps()
        return (
            zen_steps / self.zenith.steps_per_deg,
            azi_steps / self.azimuth.steps_per_deg,
        )

    def move_to_steps(
        self,
        zenith_steps: Optional[int] = None,
        azimuth_steps: Optional[int] = None,
        wait: bool = True,
        speed: int = DEFAULT_SPEED_HZ,
        accel: int = DEFAULT_ACCEL,
        decel: int = DEFAULT_DECEL,
        current_pct: float = DEFAULT_CURRENT_PCT,
        timeout: float = 120.0,
    ) -> MoveResult:
        """Move one or both axes to absolute positions in steps.

        Device-reported failures (alarm, timeout waiting for settle) are
        returned in the :class:`MoveResult`, never raised.
        """
        if zenith_steps is None and azimuth_steps is None:
            return MoveResult(ok=False, message="No target specified")

        with self._lock:
            if zenith_steps is not None:
                self._move_axis_steps(
                    self.zenith.slave_id, zenith_steps, speed, accel, decel, current_pct
                )
            if azimuth_steps is not None:
                self._move_axis_steps(
                    self.azimuth.slave_id, azimuth_steps, speed, accel, decel, current_pct
                )

            ok = True
            message = ""
            if wait:
                if zenith_steps is not None and not self._wait_motion_complete(
                    self.zenith.slave_id, timeout
                ):
                    ok = False
                    message = "zenith did not settle"
                if azimuth_steps is not None and not self._wait_motion_complete(
                    self.azimuth.slave_id, timeout
                ):
                    ok = False
                    message = (message + "; " if message else "") + "azimuth did not settle"

        return MoveResult(
            ok=ok,
            zenith_steps=zenith_steps,
            azimuth_steps=azimuth_steps,
            message=message,
        )

    def move_to(
        self,
        zenith: Optional[float] = None,
        azimuth: Optional[float] = None,
        wait: bool = True,
        speed: int = DEFAULT_SPEED_HZ,
        accel: int = DEFAULT_ACCEL,
        decel: int = DEFAULT_DECEL,
        current_pct: float = DEFAULT_CURRENT_PCT,
        timeout: float = 120.0,
    ) -> MoveResult:
        """Move one or both axes to absolute positions in degrees."""
        zenith_steps = (
            int(round(zenith * self.zenith.steps_per_deg)) if zenith is not None else None
        )
        azimuth_steps = (
            int(round(azimuth * self.azimuth.steps_per_deg)) if azimuth is not None else None
        )
        return self.move_to_steps(
            zenith_steps=zenith_steps,
            azimuth_steps=azimuth_steps,
            wait=wait,
            speed=speed,
            accel=accel,
            decel=decel,
            current_pct=current_pct,
            timeout=timeout,
        )

    def home(self, wait: bool = True, timeout: float = 180.0) -> HomeResult:
        """Home both axes: pulse HOME per axis, then poll HOME-END + READY.

        Device-reported failures are returned in the :class:`HomeResult`.
        """
        with self._lock:
            self._start_home_axis(self.zenith.slave_id)
            self._start_home_axis(self.azimuth.slave_id)

            if not wait:
                return HomeResult(ok=True, message="homing started")

            zen_ok = self._wait_home_complete(self.zenith.slave_id, timeout)
            azi_ok = self._wait_home_complete(self.azimuth.slave_id, timeout)

        ok = zen_ok and azi_ok
        message = "" if ok else "home did not complete"
        return HomeResult(
            ok=ok, zenith_home_end=zen_ok, azimuth_home_end=azi_ok, message=message
        )

    def stop(self) -> None:
        """Immediately stop both axes (spec 6.1)."""
        with self._lock:
            self._stop_axis(self.zenith.slave_id)
            self._stop_axis(self.azimuth.slave_id)

    def reset_alarms(self) -> list[AlarmStatus]:
        """Pulse ALM-RST on both axes and return the resulting alarm state."""
        with self._lock:
            self._reset_alarm_axis(self.zenith.slave_id)
            self._reset_alarm_axis(self.azimuth.slave_id)
        return self.check_alarms()

    def check_alarms(self) -> list[AlarmStatus]:
        """Return the active alarms across both axes (empty when healthy).

        A device-reported alarm is *returned*, not raised (transport errors
        still raise).
        """
        alarms: list[AlarmStatus] = []
        with self._lock:
            for axis in (self.zenith, self.azimuth):
                code = self._alarm_code(axis.slave_id)
                if code != 0:
                    alarms.append(
                        AlarmStatus(
                            axis=axis.name,
                            slave_id=axis.slave_id,
                            code=code,
                            active=True,
                            message=alarm_message(code),
                        )
                    )
        return alarms

    def _axis_status(self, axis: _AxisConfig) -> AxisStatus:
        status = self._status_word(axis.slave_id)
        code = self._alarm_code(axis.slave_id)
        pos = self._feedback_steps(axis.slave_id)
        driver_t = self._read_temp(axis.slave_id, REG_DRIVER_TEMP)
        motor_t = self._read_temp(axis.slave_id, REG_MOTOR_TEMP)
        voltage_raw = self.read_u32(axis.slave_id, REG_VOLTAGE)
        return AxisStatus(
            axis=axis.name,
            slave_id=axis.slave_id,
            status_word=status,
            ready=bool(status & ST_READY),
            moving=bool(status & ST_MOVE),
            home_end=bool(status & ST_HOME_END),
            alarm_active=bool(status & ST_ALM_A) or code != 0,
            alarm_code=code,
            alarm_message=alarm_message(code),
            position_steps=pos,
            driver_temp_c=driver_t,
            motor_temp_c=motor_t,
            voltage_v=voltage_raw / 10.0,
        )

    def _read_temp(self, slave: int, addr: int) -> Optional[float]:
        """Read a temperature monitor (x0.1 C); raw > 2000 -> None (spec 4.5)."""
        raw = self.read_u32(slave, addr, signed=True)
        if raw > _TEMP_INVALID_RAW:
            return None
        return raw / 10.0

    def get_status(self) -> dict[str, Any]:
        """Return a full status dict for both axes plus connection state."""
        status: dict[str, Any] = {
            "connected": self._connected,
            "port": self.port,
        }
        if not self._connected:
            return status
        with self._lock:
            zen = self._axis_status(self.zenith)
            azi = self._axis_status(self.azimuth)
        status["zenith"] = zen
        status["azimuth"] = azi
        return status


# --------------------------------------------------------------------------
# Simulated twin (stateful responder over SimulatedTransport)
# --------------------------------------------------------------------------
class _AzdSimResponder:
    """Stateful in-memory responder for two AZ/AZD slaves.

    Answers FC03 reads with plausible register values and echoes FC06/FC10
    writes with a valid CRC. Tracks per-slave command/status/position so the
    tracker's wait predicates terminate and moves round-trip.
    """

    def __init__(
        self,
        slave_ids: tuple[int, int],
        alarms: Optional[dict[int, int]] = None,
    ):
        alarms = alarms or {}
        self.state: dict[int, dict[str, int]] = {}
        for sid in slave_ids:
            self.state[sid] = {
                "command": 0,
                "status": ST_READY,  # ready by default so waits pass
                "home_end": 0,
                "alarm": alarms.get(sid, 0),
                "wire_pos": 0,  # signed 32-bit feedback (wire convention)
                "sw_version": 0x00000105,
                "driver_temp": 350,  # 35.0 C
                "motor_temp": 320,  # 32.0 C
                "voltage": 240,  # 24.0 V
                # Transient-motion model: while >0, each status read reports the
                # axis moving (READY clear, MOVE set); the read that decrements
                # it to 0 settles the axis to READY. This makes the tracker's
                # "wait for motion to start, then settle" gates observe a real
                # MOVE->READY transition instead of an instant settle. Position
                # and HOME-END effects are applied at write time but stay hidden
                # by _status_value until the axis settles.
                "moving": 0,
            }

    # -- register views -------------------------------------------------

    def _status_value(self, sid: int) -> int:
        st = self.state[sid]
        # An active alarm dominates and stops motion.
        if st["alarm"]:
            return (ST_ALM_A | (ST_HOME_END if st["home_end"] else 0)) & 0xFFFF
        if st["moving"] > 0:
            st["moving"] -= 1
            if st["moving"] > 0:
                # Still moving: READY clear, MOVE set.
                return ST_MOVE & 0xFFFF
            # This read settles the axis.
            st["status"] = ST_READY
        value = st["status"]
        if st["home_end"]:
            value |= ST_HOME_END
        return value & 0xFFFF

    def _read_reg(self, sid: int, addr: int) -> int:
        st = self.state[sid]
        if addr == REG_SOFTWARE_VERSION:
            return (st["sw_version"] >> 16) & 0xFFFF
        if addr == REG_SOFTWARE_VERSION + 1:
            return st["sw_version"] & 0xFFFF
        if addr == REG_COMMAND_WORD:
            return st["command"] & 0xFFFF
        if addr == REG_STATUS_WORD:
            return self._status_value(sid)
        if addr == REG_ALARM:
            return 0
        if addr == REG_ALARM + 1:
            return st["alarm"] & 0xFFFF
        if addr == REG_FEEDBACK_POSITION:
            return (st["wire_pos"] & 0xFFFFFFFF) >> 16
        if addr == REG_FEEDBACK_POSITION + 1:
            return st["wire_pos"] & 0xFFFF
        if addr in (REG_DRIVER_TEMP, REG_MOTOR_TEMP, REG_VOLTAGE):
            return 0
        if addr == REG_DRIVER_TEMP + 1:
            return st["driver_temp"] & 0xFFFF
        if addr == REG_MOTOR_TEMP + 1:
            return st["motor_temp"] & 0xFFFF
        if addr == REG_VOLTAGE + 1:
            return st["voltage"] & 0xFFFF
        return 0

    def _write_single(self, sid: int, addr: int, value: int) -> None:
        st = self.state[sid]
        if addr == REG_COMMAND_WORD:
            st["command"] = value
            if value & CMD_HOME:
                # Homing starts: go busy for a read, then settle to READY with
                # HOME-END set and position zeroed. HOME-END stays hidden by
                # _status_value until the axis settles.
                st["home_end"] = 1
                st["wire_pos"] = 0
                st["status"] = ST_MOVE
                st["moving"] = 2
            if value & CMD_ALM_RST:
                st["alarm"] = 0
            # STOP/FREE leave the axis ready in the simulation.

    def _write_multiple(self, sid: int, addr: int, regs: list[int]) -> None:
        if addr == REG_SOFTWARE_VERSION and len(regs) >= DIRECT_DATA_REG_COUNT:
            trigger = (regs[14] << 16) | regs[15]
            if trigger == DIRECT_TRIGGER_REFLECT_ALL:
                position = _to_signed32((regs[4] << 16) | regs[5])
                st = self.state[sid]
                # Move starts: go busy for a read, then settle to the target,
                # so the tracker observes a MOVE->READY transition.
                st["wire_pos"] = position
                st["status"] = ST_MOVE
                st["moving"] = 2

    # -- responder entry point -----------------------------------------

    def __call__(self, frame: bytes) -> Optional[bytes]:
        if len(frame) < 4 or not check_crc(frame):
            return None
        sid = frame[0]
        fc = frame[1]
        if sid not in self.state:
            return None
        if fc == FC_READ_HOLDING:
            addr = (frame[2] << 8) | frame[3]
            count = (frame[4] << 8) | frame[5]
            body = bytearray([sid, FC_READ_HOLDING, count * 2])
            for i in range(count):
                reg = self._read_reg(sid, addr + i)
                body += bytes([(reg >> 8) & 0xFF, reg & 0xFF])
            return append_crc(bytes(body))
        if fc == FC_WRITE_SINGLE:
            addr = (frame[2] << 8) | frame[3]
            value = (frame[4] << 8) | frame[5]
            self._write_single(sid, addr, value)
            return append_crc(frame[:6])  # echo with valid CRC
        if fc == FC_WRITE_MULTIPLE:
            addr = (frame[2] << 8) | frame[3]
            count = (frame[4] << 8) | frame[5]
            byte_count = frame[6]
            payload = frame[7 : 7 + byte_count]
            regs = [(payload[i] << 8) | payload[i + 1] for i in range(0, byte_count, 2)]
            self._write_multiple(sid, addr, regs)
            return append_crc(frame[:6])
        return None


def SimulatedRS485Tracker(
    zenith_slave: int = 1,
    azimuth_slave: int = 2,
    zenith_steps_per_deg: float = DEFAULT_STEPS_PER_DEG,
    azimuth_steps_per_deg: float = DEFAULT_STEPS_PER_DEG,
    alarms: Optional[dict[int, int]] = None,
    time_scale: float = 0.0,
) -> RS485Tracker:
    """Build an :class:`RS485Tracker` over a stateful simulated bus.

    Args:
        zenith_slave: Zenith slave id.
        azimuth_slave: Azimuth slave id.
        zenith_steps_per_deg: Steps per degree for zenith.
        azimuth_steps_per_deg: Steps per degree for azimuth.
        alarms: Optional {slave_id: alarm_code} to preset device alarms.
        time_scale: SimulatedTransport time scale (0 = instantaneous holds).

    Returns:
        A ready-to-``connect()`` RS485Tracker backed by a fake bus.
    """
    from sciglob.core.simulation import SimulatedTransport

    responder = _AzdSimResponder((zenith_slave, azimuth_slave), alarms=alarms)
    transport = SimulatedTransport(
        responder=responder,
        port="SIM_RS485",
        config=SerialConfig(baudrate=9600, parity="E", stopbits=1, timeout=0.5),
        owner="RS485Tracker",
        time_scale=time_scale,
    )
    return RS485Tracker(
        zenith_slave=zenith_slave,
        azimuth_slave=azimuth_slave,
        zenith_steps_per_deg=zenith_steps_per_deg,
        azimuth_steps_per_deg=azimuth_steps_per_deg,
        connection=transport,
    )
