"""Tests for the SBHS ESP32 JSON sensor box (sciglob.devices.sbhs)."""

import json

import pytest

from sciglob.core.connection import PortRegistry
from sciglob.core.exceptions import CommunicationError, DeviceIdentityError, SensorError
from sciglob.core.simulation import SimulatedTransport
from sciglob.devices.asb import make_asb_responder
from sciglob.devices.sbhs import (
    ANSWER_END,
    QUESTION_END_CHAR,
    SBHS,
    SensorRecord,
    SimulatedSBHS,
    extract_json_objects,
    make_sbhs_responder,
)


@pytest.fixture(autouse=True)
def _clear_port_registry():
    """Isolate the process-wide port registry between tests."""
    PortRegistry.clear()
    yield
    PortRegistry.clear()


def _sbhs_over(responder, port="SIM_SBHS", device_id=None):
    transport = SimulatedTransport(
        responder=responder, port=port, owner="SBHS", esp32_safe=True
    )
    return SBHS(port=port, device_id=device_id, connection=transport), transport


def _reset_events(transport):
    """Line events recorded after the two open-time assertions (dtr, rts)."""
    return transport.line_events[2:]


# -- identification -----------------------------------------------------


def test_sbhs_identify_without_configured_id():
    """v0.0.8.11: Hardware:3 matches with an empty id; an ASB is rejected (98)."""
    # Empty configured id must still identify via the Hardware:3 signature.
    sbhs, _ = _sbhs_over(make_sbhs_responder(), device_id=None)
    sbhs.connect()
    assert sbhs.is_connected
    raw = json.loads(sbhs.send_command("v"))
    assert raw["Hardware"] == 3
    sbhs.disconnect()

    # An ASB (Hardware:4) found where an SBHS is expected -> error code 98.
    asb_dev, _ = _sbhs_over(make_asb_responder(), port="SIM_SBHS_2", device_id=None)
    with pytest.raises(DeviceIdentityError) as excinfo:
        asb_dev.connect()
    assert excinfo.value.error_code == 98
    assert not asb_dev.is_connected


def test_identify_configured_id_fallback_when_hardware_absent():
    """With no Hardware field, identification falls back to the configured id."""

    def responder(data: bytes):
        return (json.dumps({"UUID": "unit-071-abc", "Firmware": 3}) + ANSWER_END).encode(
            "latin-1"
        )

    ok, _ = _sbhs_over(responder, device_id="071")
    ok.connect()
    assert ok.is_connected
    ok.disconnect()

    bad, _ = _sbhs_over(responder, port="SIM_SBHS_3", device_id="999")
    with pytest.raises(DeviceIdentityError) as excinfo:
        bad.connect()
    assert excinfo.value.error_code == 1


# -- ESP32 open / reset doctrine ---------------------------------------


def test_esp32_open_never_pulses_reset():
    """A normal open asserts DTR/RTS and never pulses a reset line."""
    sbhs, transport = _sbhs_over(make_sbhs_responder())
    sbhs.connect()

    events = transport.line_events
    # Open asserts both lines high; nothing else touches control lines.
    assert events[0] == ("dtr", True)
    assert events[1] == ("rts", True)
    # No reset pulse: no DTR=False and no sleep-hold recorded after open.
    assert all(not (e.line == "dtr" and e.value is False) for e in events)
    assert all(e.line != "sleep" for e in events)


def test_reset_pulse_line_sequence():
    """reset_pulse() drives RTS high, DTR low, holds 0.5 s, then DTR high."""
    sbhs, transport = _sbhs_over(make_sbhs_responder())
    sbhs.connect()
    sbhs.reset_pulse()

    seq = _reset_events(transport)
    assert seq[0] == ("rts", True)
    assert seq[1] == ("dtr", False)
    assert seq[2] == ("sleep", 0.5)
    assert seq[3] == ("dtr", True)


def test_reset_pulse_auto_throttle():
    """Automatic reset pulses are throttled to >= 600 s apart."""
    sbhs, transport = _sbhs_over(make_sbhs_responder())
    sbhs.connect()
    assert sbhs._maybe_auto_reset_pulse() is True
    # Second immediate automatic firing is suppressed by the throttle.
    assert sbhs._maybe_auto_reset_pulse() is False


# -- parsing ------------------------------------------------------------


def test_last_complete_json_record_parsing():
    """A stale complete record preceding the fresh one is discarded."""
    stale = json.dumps(
        {
            "Hardware": 3,
            "Firmware": 3,
            "UUID": "STALE",
            "Sensors": [
                {"ID": "BME280", "Temperature": 11.11, "Humidity": 1.0, "Pressure": 900.0}
            ],
        }
    )
    fresh = json.dumps(
        {
            "Hardware": 3,
            "Firmware": 3,
            "UUID": "FRESH",
            "Sensors": [
                {"ID": "BME280", "Temperature": 30.1, "Humidity": 9.46, "Pressure": 1024.89}
            ],
        }
    )

    def responder(data: bytes):
        text = data.decode("latin-1")
        if text == "T" + QUESTION_END_CHAR:
            # A stale fragment from a timed-out earlier read precedes the answer.
            return [stale + ANSWER_END, fresh + ANSWER_END]
        if text == "v" + QUESTION_END_CHAR:
            # Identify returns Hardware only (no cached sensor record).
            return (json.dumps({"Hardware": 3, "Firmware": 3, "UUID": "id"}) + ANSWER_END)
        return None

    sbhs, _ = _sbhs_over(responder)
    sbhs.connect()
    record = sbhs.get_record(force=True)
    assert record.uuid == "FRESH"
    assert record.bme280 is not None
    assert record.bme280.temperature == 30.1
    assert sbhs.get_temperature() == 30.1


def test_extract_json_objects_skips_partial_fragment():
    text = '{"Hardware":3,"Firm' + '{"Hardware":3,"UUID":"real","Sensors":[]}'
    objs = extract_json_objects(text)
    assert len(objs) == 1
    assert objs[0]["UUID"] == "real"


# -- readings & cache ---------------------------------------------------


def test_readings_and_wire_commands():
    sbhs, transport = _sbhs_over(
        make_sbhs_responder(temperature=25.0, humidity=40.0, pressure=1000.0)
    )
    sbhs.connect()
    assert sbhs.get_temperature() == 25.0
    assert sbhs.get_humidity() == 40.0
    assert sbhs.get_pressure() == 1000.0
    # Identify wrote "v\r".
    assert (b"v" + QUESTION_END_CHAR.encode()) in transport.written


def test_record_cache_serves_siblings():
    """One read serves sibling quantities from cache (no extra wire traffic)."""
    sbhs, transport = _sbhs_over(make_sbhs_responder())
    sbhs.connect()
    sbhs.get_record(force=True)
    writes_after_first = len(transport.written)
    # These three come from the cached record.
    sbhs.get_temperature()
    sbhs.get_humidity()
    sbhs.get_pressure()
    assert len(transport.written) == writes_after_first


def test_simulated_sbhs_convenience():
    sbhs = SimulatedSBHS(temperature=19.5)
    sbhs.connect()
    assert isinstance(sbhs.get_record(force=True), SensorRecord)
    assert sbhs.get_temperature() == 19.5
    sbhs.disconnect()


def test_read_failure_raises_low_level_serial():
    """A silent box (no answer) raises CommunicationError with code 99."""

    def silent(data: bytes):
        text = data.decode("latin-1")
        if text == "v" + QUESTION_END_CHAR:
            return (json.dumps({"Hardware": 3, "UUID": "id"}) + ANSWER_END)
        return None

    sbhs, _ = _sbhs_over(silent)
    sbhs.timeout = 0.05  # keep the test fast
    sbhs.connect()
    with pytest.raises(CommunicationError) as excinfo:
        sbhs.get_record(force=True)
    assert excinfo.value.error_code == 99


def test_not_connected_raises():
    sbhs = SBHS(port="COM_UNUSED")
    with pytest.raises(Exception):
        sbhs.get_temperature()
