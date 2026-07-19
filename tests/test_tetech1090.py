"""Tests for the TETech1090 temperature-controller extension.

Drives the controller entirely through SimulatedTransport (no hardware, no
real serial). Asserts exact frame bytes, CRC-16/XMODEM checksums against the
spec's worked examples (specs/tetech.md §4), and float32 round-trips.
"""

import pytest

from sciglob.core.connection import PortRegistry
from sciglob.core.exceptions import CommunicationError, DeviceError
from sciglob.core.simulation import SimulatedTransport, make_responder
from sciglob.devices import _tetech1090 as t
from sciglob.devices.temperature_controller import (
    SimulatedTemperatureController1090,
    TemperatureController,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Release any port claims between tests."""
    PortRegistry.clear()
    yield
    PortRegistry.clear()


# -- pure protocol helpers -------------------------------------------------

# CRC-16/XMODEM worked examples verified in the spec (§4.2), each a literal
# checksum that appears hardcoded in the field code.
SPEC_CRC_CASES = {
    "#000000?VR006401": "A912",
    "#000000?VR0BB801": "0DF2",
    "#000000?VR0BC201": "BC87",
    "#000000?VR0BC301": "8BB7",
    "#000000?VR03E801": "EB08",
    "#000000?VR03E901": "DC38",
    "!000000+05": "A7C4",
}

# IEEE-754 float32 -> 8 hex chars worked examples (§4.4).
SPEC_FLOAT_CASES = {
    20.0: "41A00000",
    -5.0: "C0A00000",
    1.0: "3F800000",
    5.0: "40A00000",
    0.8: "3F4CCCCD",
}


@pytest.mark.parametrize("text,expected", SPEC_CRC_CASES.items())
def test_crc16_xmodem_matches_spec(text, expected):
    assert t.crc_hex(text) == expected


@pytest.mark.parametrize("value,expected", SPEC_FLOAT_CASES.items())
def test_float_to_hex8_matches_spec(value, expected):
    assert t.float_to_hex8(value) == expected


def test_float_hex8_is_zero_padded():
    # Fixes the legacy Blick hex() quirk: 0.0 must be 8 chars, not "0" (§4.4/§11).
    assert t.float_to_hex8(0.0) == "00000000"
    assert len(t.float_to_hex8(0.0)) == 8


@pytest.mark.parametrize("value", [20.0, -5.0, 1.0, 5.0, 0.8, 0.0, 37.25, -12.5])
def test_float32_round_trip(value):
    assert t.hex8_to_float(t.float_to_hex8(value)) == pytest.approx(value, rel=1e-6, abs=1e-6)


def test_identify_frame_literal_and_crc():
    # Identify handshake frame, spec §1: "#000000?VR006401A912".
    assert t.IDENTIFY_FRAME == "#000000?VR006401A912"
    # CRC portion is the verified worked example.
    assert t.IDENTIFY_FRAME[-4:] == "A912"


def test_set_temp_frame_literal_and_crc():
    # Worked example (§4.4): set target temperature 20.0 degC.
    payload = t.CMD_SET_TEMP + t.float_to_hex8(20.0)
    frame = t.build_frame(payload)
    assert frame == "#000000VS0BB80141A00000551C"
    assert t.frame_crc(payload) == "551C"


# -- constructor -----------------------------------------------------------


def test_init_accepts_1090_and_defaults_baud():
    tc = TemperatureController(controller_type="TETech1090")
    assert tc.controller_type == "TETech1090"
    assert tc.nbits == 32
    assert tc.baudrate == 19200  # 1090 default when caller left 9600 untouched


def test_init_1090_honours_explicit_baud():
    tc = TemperatureController(controller_type="TETech1090", baudrate=57600)
    assert tc.baudrate == 57600


def test_init_still_rejects_invalid_type():
    with pytest.raises(ValueError):
        TemperatureController(controller_type="Invalid")


def test_init_tetech1_and_tetech2_unchanged():
    tc1 = TemperatureController(controller_type="TETech1")
    assert tc1.controller_type == "TETech1" and tc1.nbits == 16
    tc2 = TemperatureController(controller_type="TETech2")
    assert tc2.controller_type == "TETech2" and tc2.nbits == 32


# -- connect / identify ----------------------------------------------------


def test_connect_sends_identify_frame_bytes():
    tc = SimulatedTemperatureController1090(connect=True)
    assert tc.is_connected
    # Exact bytes written for the identify handshake (# frame + CR).
    assert tc._connection.written[0] == b"#000000?VR006401A912\r"
    tc.disconnect()


# -- write frames ----------------------------------------------------------


def test_set_temperature_writes_exact_frame():
    tc = SimulatedTemperatureController1090()
    assert tc.set_temperature(20.0) is True
    # The write frame matches the spec worked example (CRC 551C).
    assert tc._connection.written[-1] == b"#000000VS0BB80141A00000551C\r"
    tc.disconnect()


def test_enable_and_disable_output_frames():
    tc = SimulatedTemperatureController1090()
    assert tc.enable_output() is True
    assert tc._connection.written[-1].startswith(b"#000000VS07DA0100000001")
    assert tc._connection.written[-1].endswith(b"\r")
    assert tc.disable_output() is True
    assert tc._connection.written[-1].startswith(b"#000000VS07DA0100000000")
    tc.disconnect()


# -- read / round-trip -----------------------------------------------------


def test_setpoint_round_trip():
    tc = SimulatedTemperatureController1090(setpoint=15.0)
    assert tc.get_setpoint() == pytest.approx(15.0)
    # Set a new setpoint and read it back through the device register bank.
    assert tc.set_temperature(37.25) is True
    assert tc.get_setpoint() == pytest.approx(37.25)
    tc.disconnect()


def test_object_and_sink_temperature():
    tc = SimulatedTemperatureController1090(object_temp=19.6, sink_temp=23.4)
    assert tc.get_object_temperature() == pytest.approx(19.6)
    assert tc.get_sink_temperature() == pytest.approx(23.4)
    # Exact read frames.
    assert b"#000000?VR03E801EB08\r" in tc._connection.written
    assert b"#000000?VR03E901DC38\r" in tc._connection.written
    tc.disconnect()


def test_pid_conversion_round_trip():
    # User units PB=0.5, Ki=0.1 -> device Kp=1/PB=2.0, Ti=1/(PB*Ki)=20.0 (§4.5).
    tc = SimulatedTemperatureController1090()
    assert tc.set_pid(bandwidth=0.5, integral_gain=0.1) is True
    # Kp write frame carries float32(2.0) = 40000000.
    kp_frame = b"#000000VS0BC201" + t.float_to_hex8(2.0).encode()
    assert any(w.startswith(kp_frame) for w in tc._connection.written)
    # Read back in user units: PB = 1/Kp, Ki = Kp/Ti.
    assert tc.get_proportional_bandwidth() == pytest.approx(0.5, rel=1e-5)
    assert tc.get_integral_gain() == pytest.approx(0.1, rel=1e-5)
    tc.disconnect()


def test_set_pid_with_derivative():
    tc = SimulatedTemperatureController1090()
    assert tc.set_pid(bandwidth=1.0, integral_gain=0.5, derivative_gain=0.25) is True
    kd_frame = b"#000000VS0BC401" + t.float_to_hex8(0.25).encode()
    assert any(w.startswith(kd_frame) for w in tc._connection.written)
    tc.disconnect()


def test_get_status_1090():
    tc = SimulatedTemperatureController1090(object_temp=18.0, sink_temp=22.0, setpoint=20.0)
    status = tc.get_status()
    assert status["controller_type"] == "TETech1090"
    assert status["object_temperature"] == pytest.approx(18.0)
    assert status["sink_temperature"] == pytest.approx(22.0)
    assert status["setpoint"] == pytest.approx(20.0)
    tc.disconnect()


# -- error handling --------------------------------------------------------


def test_error_frame_raises_communication_error():
    # A device error answer ("+05") must raise, never return a stale value (§4.6).
    err_body = "!000000+05"
    err_frame = err_body + t.crc_hex(err_body) + "\r"
    id_body = "!00000000000441"
    id_frame = id_body + t.crc_hex(id_body) + "\r"
    responder = make_responder({t.IDENTIFY_FRAME: id_frame}, default=err_frame, end_char="\r")
    transport = SimulatedTransport(responder=responder, port="SIM_ERR", owner="tec")
    tc = TemperatureController(port="SIM_ERR", controller_type="TETech1090", connection=transport)
    tc.connect()
    with pytest.raises(CommunicationError):
        tc.get_object_temperature()
    tc.disconnect()


def test_bad_crc_raises_communication_error():
    with pytest.raises(CommunicationError):
        t.parse_get_answer("!00000041A000000000")  # wrong CRC


def test_require_1090_guard_on_non_1090():
    tc = TemperatureController(controller_type="TETech1")
    with pytest.raises(DeviceError):
        tc.get_object_temperature()
    with pytest.raises(DeviceError):
        tc.get_sink_temperature()
