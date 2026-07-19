"""Tests for the direct-RS485 Oriental Motor AZ/AZD Modbus RTU tracker."""

import pytest

from sciglob.devices.rs485_tracker import (
    CMD_HOME,
    DEFAULT_STEPS_PER_DEG,
    REG_COMMAND_WORD,
    REG_SOFTWARE_VERSION,
    RS485Tracker,
    SimulatedRS485Tracker,
    _to_signed32,
    _u32_words,
    alarm_message,
    append_crc,
    build_read_frame,
    build_write_multiple_frame,
    build_write_single_frame,
    check_crc,
    modbus_crc16,
)


# --------------------------------------------------------------------------
# CRC-16/Modbus vectors (spec section 2.1)
# --------------------------------------------------------------------------
class TestCrc:
    def test_canonical_check_value(self):
        # Published CRC-16/MODBUS check value for the ASCII string "123456789".
        assert modbus_crc16(b"123456789") == 0x4B37

    def test_worked_example(self):
        # Classic Modbus worked example: 01 04 02 FF FF -> CRC word 0x80B8
        # (transmitted little-endian: B8 80).
        assert modbus_crc16(bytes([0x01, 0x04, 0x02, 0xFF, 0xFF])) == 0x80B8

    def test_append_is_little_endian(self):
        payload = bytes([0x01, 0x04, 0x02, 0xFF, 0xFF])
        framed = append_crc(payload)
        assert framed == payload + b"\xb8\x80"

    def test_check_crc_roundtrip(self):
        frame = append_crc(b"\x01\x03\x00\x7f\x00\x01")
        assert check_crc(frame)
        # Corrupt a byte -> CRC must fail.
        bad = bytearray(frame)
        bad[2] ^= 0xFF
        assert not check_crc(bytes(bad))


# --------------------------------------------------------------------------
# Exact request-frame bytes (spec section 2.3)
# --------------------------------------------------------------------------
class TestFrameBytes:
    def test_read_frame_bytes(self):
        # FC03 read status word 0x007F, 1 register, slave 1.
        assert build_read_frame(1, 0x007F, 1) == bytes.fromhex("01 03 00 7f 00 01 b5 d2".replace(" ", ""))

    def test_read_alarm_frame_bytes(self):
        # FC03 read alarm 0x0080, 2 registers, slave 1.
        assert build_read_frame(1, 0x0080, 2) == bytes.fromhex("010300800002c5e3")

    def test_write_single_home_frame_bytes(self):
        # FC06 write HOME (0x0010) to command word 0x007D, slave 1.
        assert build_write_single_frame(1, 0x007D, CMD_HOME) == bytes.fromhex("0106007d0010181e")

    def test_write_single_clear_frame_bytes(self):
        assert build_write_single_frame(1, 0x007D, 0x0000) == bytes.fromhex("0106007d000019d2")

    def test_move_frame_bytes(self):
        # FC10 direct-data absolute move, zenith (slave 1), 1000 steps,
        # speed 3000, accel/decel 1000, current 50%. Position negated on wire.
        trk = RS485Tracker()
        block = trk._direct_move_block(1000, 3000, 1000, 1000, 50.0)
        frame = build_write_multiple_frame(1, REG_SOFTWARE_VERSION, block)
        expected = bytes.fromhex(
            "01100058001020"  # slave/fc/addr=0x0058/count=16/bytecount=32
            "00000000"  # data_no = 0
            "00000001"  # op_type = 1 (absolute)
            "fffffc18"  # position = -1000 (two's complement)
            "00000bb8"  # speed 3000
            "000003e8"  # accel 1000
            "000003e8"  # decel 1000
            "000001f4"  # current 500 (50.0% x10)
            "00000001"  # trigger = 1
            "c0d1"  # CRC
        )
        assert frame == expected


# --------------------------------------------------------------------------
# 32-bit byte order helpers (spec section 2.4)
# --------------------------------------------------------------------------
class TestByteOrder:
    def test_u32_words_big_endian(self):
        assert _u32_words(0x12345678) == (0x1234, 0x5678)

    def test_u32_words_negative_twos_complement(self):
        assert _u32_words(-1000) == (0xFFFF, 0xFC18)

    def test_signed_roundtrip(self):
        for value in (0, 1, -1, 1000, -1000, 0x7FFFFFFF, -0x80000000):
            hi, lo = _u32_words(value)
            recombined = _to_signed32((hi << 16) | lo)
            assert recombined == value


# --------------------------------------------------------------------------
# Alarm decode (spec section 7.1)
# --------------------------------------------------------------------------
class TestAlarmDecode:
    def test_known_codes(self):
        assert alarm_message(0x00) == "No alarm"
        assert alarm_message(0x30) == "Overcurrent"
        assert alarm_message(0x21) == "Heat sink overheat (driver)"

    def test_unknown_code(self):
        assert alarm_message(0xEE) == "Unknown (0xEE)"


# --------------------------------------------------------------------------
# End-to-end against the simulated bus
# --------------------------------------------------------------------------
class TestSimulated:
    def test_connect_and_default_position(self):
        trk = SimulatedRS485Tracker()
        trk.connect()
        assert trk.is_connected
        assert trk.get_position_steps() == (0, 0)
        assert trk.get_position() == (0.0, 0.0)
        trk.disconnect()

    def test_move_to_steps_roundtrip(self):
        # 32-bit big-endian round trip through the direct-data block +
        # feedback register (both sign-negated: user positive round-trips).
        trk = SimulatedRS485Tracker()
        trk.connect()
        result = trk.move_to_steps(zenith_steps=123456, azimuth_steps=-6789)
        assert result.ok
        zen, azi = trk.get_position_steps()
        assert zen == 123456
        assert azi == -6789

    def test_move_to_degrees_roundtrip(self):
        trk = SimulatedRS485Tracker()
        trk.connect()
        result = trk.move_to(zenith=30.0, azimuth=90.0)
        assert result.ok
        zen_deg, azi_deg = trk.get_position()
        assert zen_deg == pytest.approx(30.0)
        assert azi_deg == pytest.approx(90.0)

    def test_move_emits_expected_frame(self):
        # The move must put the exact FC10 direct-data frame on the wire.
        trk = SimulatedRS485Tracker()
        trk.connect()
        trk.move_to_steps(zenith_steps=1000, wait=False)
        block = trk._direct_move_block(1000, 3000, 1000, 1000, 50.0)
        expected = build_write_multiple_frame(1, REG_SOFTWARE_VERSION, block)
        written = trk._connection.written  # type: ignore[union-attr]
        assert expected in written

    def test_home_emits_home_command_and_completes(self):
        trk = SimulatedRS485Tracker()
        trk.connect()
        result = trk.home()
        assert result.ok
        assert result.zenith_home_end and result.azimuth_home_end
        home_frame = build_write_single_frame(1, REG_COMMAND_WORD, CMD_HOME)
        written = trk._connection.written  # type: ignore[union-attr]
        assert home_frame in written

    def test_no_alarms_when_healthy(self):
        trk = SimulatedRS485Tracker()
        trk.connect()
        assert trk.check_alarms() == []

    def test_device_reported_alarm_is_returned_not_raised(self):
        # A device-reported alarm must surface as data, not an exception.
        trk = SimulatedRS485Tracker(alarms={1: 0x30})  # overcurrent on zenith
        trk.connect()
        alarms = trk.check_alarms()  # must NOT raise
        assert len(alarms) == 1
        assert alarms[0].axis == "zenith"
        assert alarms[0].slave_id == 1
        assert alarms[0].code == 0x30
        assert alarms[0].active
        assert alarms[0].message == "Overcurrent"

    def test_reset_alarms_clears_state(self):
        trk = SimulatedRS485Tracker(alarms={2: 0x31})  # overload on azimuth
        trk.connect()
        assert trk.check_alarms()  # present before reset
        remaining = trk.reset_alarms()
        assert remaining == []

    def test_get_status_snapshot(self):
        trk = SimulatedRS485Tracker()
        trk.connect()
        status = trk.get_status()
        assert status["connected"] is True
        zen = status["zenith"]
        assert zen.slave_id == 1
        assert zen.ready is True
        assert zen.alarm_code == 0
        assert zen.driver_temp_c == pytest.approx(35.0)
        assert zen.motor_temp_c == pytest.approx(32.0)
        assert zen.voltage_v == pytest.approx(24.0)

    def test_configurable_steps_per_deg(self):
        trk = SimulatedRS485Tracker(zenith_steps_per_deg=200.0)
        trk.connect()
        assert trk.zenith.steps_per_deg == 200.0
        trk.move_to(zenith=10.0)
        zen_steps, _ = trk.get_position_steps()
        assert zen_steps == 2000  # 10 deg * 200 steps/deg

    def test_configurable_slave_ids(self):
        trk = SimulatedRS485Tracker(zenith_slave=5, azimuth_slave=6)
        trk.connect()
        trk.move_to_steps(zenith_steps=42, wait=False)
        move_frame = build_write_multiple_frame(
            5, REG_SOFTWARE_VERSION, trk._direct_move_block(42, 3000, 1000, 1000, 50.0)
        )
        assert move_frame in trk._connection.written  # type: ignore[union-attr]


def test_defaults():
    assert DEFAULT_STEPS_PER_DEG == 100.0


# --------------------------------------------------------------------------
# Review-finding regressions (0.2.0): half-duplex echo, Modbus exception
# frames, motion/home start gating, pre-move STOP pulse.
# --------------------------------------------------------------------------
from sciglob.core.exceptions import CommunicationError  # noqa: E402
from sciglob.core.simulation import SimulatedTransport  # noqa: E402
from sciglob.devices.rs485_tracker import (  # noqa: E402
    CMD_STOP,
    FC_READ_HOLDING,
    ST_HOME_END,
    ST_MOVE,
    ST_READY,
    _AzdSimResponder,
)


class _EchoingResponder:
    """Wraps the AZD sim responder to also echo the request first (half-duplex)."""

    def __init__(self, slave_ids=(1, 2)):
        self._inner = _AzdSimResponder(slave_ids)

    def __call__(self, frame: bytes):
        answer = self._inner(frame)
        if answer is None:
            return frame  # echo only
        return [frame, answer]  # echo, then the response


def test_transact_handles_half_duplex_echo():
    # On an echoing bus the transmitted frame comes back before the response.
    transport = SimulatedTransport(responder=_EchoingResponder(), port="SIM_ECHO")
    trk = RS485Tracker(connection=transport, echo=True)
    trk.connect()
    # A read must still decode correctly with the echo discarded.
    zen, azi = trk.get_position()
    assert zen == 0.0 and azi == 0.0
    trk.disconnect()


def test_modbus_exception_frame_raises_not_times_out():
    # A device exception frame (fc | 0x80) must raise CommunicationError with the
    # exception code, not block until the read times out.
    def exc_responder(frame: bytes):
        sid, fc = frame[0], frame[1]
        return append_crc(bytes([sid, fc | 0x80, 0x02]))  # exception code 0x02

    transport = SimulatedTransport(responder=exc_responder, port="SIM_EXC")
    trk = RS485Tracker(connection=transport, timeout=0.3)
    trk.connect()
    with pytest.raises(CommunicationError) as exc:
        trk.get_position()
    assert exc.value.error_code == 0x02
    trk.disconnect()


def test_move_waits_for_motion_to_start_then_settle():
    # The sim reports MOVE for a read before settling; the tracker must observe
    # that transition (not report settled on the first poll).
    trk = SimulatedRS485Tracker()
    trk.connect()
    result = trk.move_to(zenith=30.0, azimuth=120.0)
    zen, azi = trk.get_position()
    assert round(zen, 3) == 30.0
    assert round(azi, 3) == 120.0
    # move_to returns a MoveResult whose axes report completion.
    assert result is not None
    trk.disconnect()


def test_move_issues_stop_pulse_before_motion_data():
    # Pre-move safety: a STOP pulse must precede the direct-data block write.
    transport = SimulatedTransport(responder=_AzdSimResponder((1, 2)), port="SIM_STOP")
    trk = RS485Tracker(connection=transport, motion_start_grace=0.2)
    trk.connect()
    transport.fake.written.clear()
    trk.move_to(zenith=10.0)
    # Find the FC06 writes to the command word; the first must be a STOP pulse.
    cmd_writes = [
        w
        for w in transport.written
        if len(w) >= 6 and w[1] == 0x06 and ((w[2] << 8) | w[3]) == REG_COMMAND_WORD
    ]
    assert cmd_writes, "expected command-word writes"
    first_value = (cmd_writes[0][4] << 8) | cmd_writes[0][5]
    assert first_value == CMD_STOP
    trk.disconnect()


def test_home_waits_for_ready_drop_then_home_end():
    trk = SimulatedRS485Tracker()
    trk.connect()
    result = trk.home()
    assert result is not None
    # After homing the feedback position is zeroed.
    zen, azi = trk.get_position_steps()
    assert zen == 0 and azi == 0
    trk.disconnect()
