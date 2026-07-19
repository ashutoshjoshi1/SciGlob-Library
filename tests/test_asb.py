"""Tests for the ASB ESP32 JSON sensor box (sciglob.devices.asb)."""

import json

import pytest

from sciglob.core.connection import PortRegistry
from sciglob.core.exceptions import DeviceIdentityError
from sciglob.core.simulation import SimulatedTransport
from sciglob.devices.asb import ASB, SimulatedASB, make_asb_responder
from sciglob.devices.sbhs import ANSWER_END, QUESTION_END_CHAR, make_sbhs_responder


@pytest.fixture(autouse=True)
def _clear_port_registry():
    PortRegistry.clear()
    yield
    PortRegistry.clear()


def _asb_over(responder, port="SIM_ASB", device_id=None):
    transport = SimulatedTransport(
        responder=responder, port=port, owner="ASB", esp32_safe=True
    )
    return ASB(port=port, device_id=device_id, connection=transport), transport


def test_asb_identify_hardware_4():
    asb, _ = _asb_over(make_asb_responder())
    asb.connect()
    assert asb.is_connected
    raw = json.loads(asb.send_command("v"))
    assert raw["Hardware"] == 4
    asb.disconnect()


def test_asb_rejects_sbhs_with_code_98():
    """An SBHS (Hardware:3) found where an ASB is expected -> error code 98."""
    asb, _ = _asb_over(make_sbhs_responder())
    with pytest.raises(DeviceIdentityError) as excinfo:
        asb.connect()
    assert excinfo.value.error_code == 98
    assert not asb.is_connected


def test_asb_get_ambient_pressure_from_mprls():
    asb, _ = _asb_over(make_asb_responder(ambient_pressure=1002.4))
    asb.connect()
    assert asb.get_ambient_pressure() == 1002.4


def test_asb_bme280_readings():
    asb, _ = _asb_over(
        make_asb_responder(temperature=18.0, humidity=55.0, pressure=995.0)
    )
    asb.connect()
    assert asb.get_temperature() == 18.0
    assert asb.get_humidity() == 55.0
    assert asb.get_pressure() == 995.0


def test_asb_record_has_both_bme280_and_mprls():
    asb, _ = _asb_over(make_asb_responder())
    asb.connect()
    record = asb.get_record(force=True)
    assert record.bme280 is not None
    assert record.sensor("MPRLS") is not None


def test_esp32_open_never_pulses_reset_asb():
    asb, transport = _asb_over(make_asb_responder())
    asb.connect()
    events = transport.line_events
    assert events[0] == ("dtr", True)
    assert events[1] == ("rts", True)
    assert all(not (e.line == "dtr" and e.value is False) for e in events)
    assert all(e.line != "sleep" for e in events)


def test_asb_reset_pulse_line_sequence():
    asb, transport = _asb_over(make_asb_responder())
    asb.connect()
    asb.reset_pulse()
    seq = transport.line_events[2:]
    assert seq[0] == ("rts", True)
    assert seq[1] == ("dtr", False)
    assert seq[2] == ("sleep", 0.5)
    assert seq[3] == ("dtr", True)


def test_ap_command_is_wired():
    asb, transport = _asb_over(make_asb_responder())
    asb.connect()
    asb.send_command("AP")
    assert (b"AP" + QUESTION_END_CHAR.encode()) in transport.written


def test_simulated_asb_convenience():
    asb = SimulatedASB(ambient_pressure=1007.7)
    asb.connect()
    assert asb.get_ambient_pressure() == 1007.7
    asb.disconnect()
