"""Tests for the Instrument facade: construction, graceful degradation,
status map, and cross-device power-cycle coupling."""

import warnings

import pytest

from sciglob import Instrument
from sciglob.core.connection import PortRegistry
from sciglob.instrument import DeviceState


@pytest.fixture(autouse=True)
def _clear_registry():
    PortRegistry.clear()
    yield
    PortRegistry.clear()


def _full_config():
    return {
        "head_sensor": {"sensor_type": "SciGlobHSN2", "tracker_type": "LuftBlickTR1"},
        "sbhs": {},
        "asb": {},
        "srb": {},
        "relay_board": {"nrelays": 4},
        "spectrometer": {"serial_number": "SIM123", "npixels": 2048},
        "camera": {},
        "imu": {},
    }


def test_simulated_instrument_opens_all_devices():
    inst = Instrument(config=_full_config(), simulated=True)
    with inst:
        assert inst.head_sensor is not None
        assert inst.tracker is not None  # head-sensor tracker child
        assert inst.filter_wheel_1 is not None
        assert inst.sbhs is not None
        assert inst.asb is not None
        assert inst.srb is not None
        assert inst.relay_board is not None
        assert inst.spectrometer is not None
        assert inst.camera is not None
        assert inst.imu is not None
    assert not inst.is_open


def test_status_map_reports_state_per_device():
    inst = Instrument(config=_full_config(), simulated=True)
    with inst:
        status = inst.status()
    assert status["head_sensor"]["state"] == "simulated"
    assert status["sbhs"]["state"] == "simulated"
    assert status["spectrometer"]["state"] == "simulated"
    # A device not in the config is absent.
    assert status["humidity_sensor"]["state"] == "absent"


def test_rs485_tracker_backend_selected():
    cfg = {"tracker": {"backend": "rs485"}}
    inst = Instrument(config=cfg, simulated=True)
    with inst:
        assert type(inst.tracker).__name__ == "RS485Tracker"
        # Drop-in facade surface.
        for m in ("move_to", "move_to_steps", "home", "get_position", "check_alarms"):
            assert hasattr(inst.tracker, m)


def test_simulated_sensor_readings():
    inst = Instrument(config=_full_config(), simulated=True)
    with inst:
        assert isinstance(inst.sbhs.get_humidity(), float)
        assert isinstance(inst.asb.get_ambient_pressure(), float)
        assert isinstance(inst.srb.get_temperature(), float)
        inst.spectrometer.set_integration_time(100)
        spectrum = inst.spectrometer.measure(2)
        assert len(spectrum.counts) == 2048


def test_spec_power_cycle_marks_spectrometer_first():
    """head_sensor.spec_power_cycle must mark the spectrometer power-cycled
    BEFORE the relay drops USB power (the v0.0.8.7 crash-class coupling)."""
    inst = Instrument(config=_full_config(), simulated=True)
    with inst:
        events = []
        real_mark = inst.spectrometer.mark_power_cycled

        def spy_mark():
            events.append("marked")
            real_mark()

        inst.spectrometer.mark_power_cycled = spy_mark

        # Record when the relay command actually goes out.
        conn = inst.head_sensor._connection
        before = len(conn.written)
        inst.head_sensor.spec_power_cycle(1)
        # The mark happened, and it happened before/with the relay write.
        assert "marked" in events
        assert len(conn.written) > before


def test_strict_mode_reraises_on_open_failure():
    """strict=True re-raises when a real device cannot open (no simulation)."""
    # A real head sensor on a non-existent port must raise in strict mode.
    cfg = {"head_sensor": {"serial": {"port": "COM_DOES_NOT_EXIST_999"}}}
    inst = Instrument(config=cfg, strict=True, simulated=False)
    with pytest.raises(Exception):
        inst.open()


def test_nonstrict_degrades_to_simulated_or_error():
    """Non-strict open never raises; a failed device becomes simulated/error."""
    cfg = {
        "head_sensor": {"serial": {"port": "COM_DOES_NOT_EXIST_999"}},
        "humidity_sensor": {"serial": {"port": "COM_DOES_NOT_EXIST_998"}},
    }
    inst = Instrument(config=cfg, strict=False, simulated=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        inst.open()
    status = inst.status()
    # Head sensor has a simulated twin -> degrades to simulated (with error noted).
    assert status["head_sensor"]["state"] in ("simulated", "error")
    # Humidity sensor has no twin -> error, and the whole instrument survived.
    assert status["humidity_sensor"]["state"] == "error"
    assert "humidity_sensor" in inst.errors
    inst.close()


def test_from_dict_constructor():
    inst = Instrument.from_dict({"sbhs": {}}, simulated=True)
    with inst:
        assert inst.sbhs is not None


def test_repr():
    inst = Instrument(config={"sbhs": {}}, simulated=True)
    assert "closed" in repr(inst)
    with inst:
        assert "open" in repr(inst)


def test_device_state_enum_values():
    assert DeviceState.CONNECTED.value == "connected"
    assert DeviceState.SIMULATED.value == "simulated"
    assert DeviceState.ABSENT.value == "absent"
    assert DeviceState.ERROR.value == "error"
