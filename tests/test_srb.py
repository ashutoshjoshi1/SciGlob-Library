"""Tests for the SciGlobSRB1 sensors-reading board driver.

Drives the SRB entirely through SimulatedTransport (no hardware, no real
serial). Asserts exact bytes-in / answer-out and the ':' value parse.
"""

import pytest

from sciglob.core.connection import PortRegistry
from sciglob.core.exceptions import DeviceError
from sciglob.core.protocols import ESP32_SENSOR_ERROR_MESSAGES
from sciglob.core.simulation import SimulatedTransport, make_responder
from sciglob.devices.srb import SRB, SimulatedSRB


@pytest.fixture(autouse=True)
def _clear_registry():
    """Release any port claims between tests."""
    PortRegistry.clear()
    yield
    PortRegistry.clear()


def _srb(mapping, port="SIM_SRB", **kwargs):
    """Build an SRB over a scripted transport from a command->answer mapping."""
    responder = make_responder(mapping, end_char="\r")
    transport = SimulatedTransport(responder=responder, port=port, owner="SRB")
    return SRB(port=port, connection=transport, **kwargs)


# -- identity / connect --------------------------------------------------


def test_connect_requires_ready():
    srb = _srb({"?": "SciGlobSRB1 ready\r"})
    srb.connect()
    assert srb.is_connected
    # exact bytes written for identify
    assert srb._connection.written[0] == b"?\r"
    srb.disconnect()


def test_connect_fails_without_ready():
    srb = _srb({"?": "SciGlobSRB1 booting\r"})
    with pytest.raises(DeviceError):
        srb.connect()
    assert not srb.is_connected


def test_identify_true_false():
    srb = _srb({"?": "board is ready now\r"})
    srb.connect()
    assert srb.identify() is True
    srb.disconnect()


def test_identify_probe_no_grace_retry_on_silent_port():
    # spec §6: a port-scan identification probe must abort promptly at its
    # own timeout, not inherit ask()'s short-timeout grace-retry (which would
    # re-ask up to 3x with 1 s waits). Against a silent transport, identify()
    # must return False after exactly ONE write (no re-ask) and quickly.
    import time

    srb = _srb({})  # empty mapping -> transport stays silent
    srb._connection = srb._injected_connection
    srb._connection.open()
    start = time.monotonic()
    result = srb.identify(probe_timeout=0.4)
    elapsed = time.monotonic() - start
    assert result is False
    # exactly one write: the single '?\r' probe, no grace re-ask
    assert srb._connection.written == [b"?\r"]
    # aborts near the probe timeout, not ~3.4 s (0.4 s + 3 grace seconds)
    assert elapsed < 1.5
    srb._connection.close()


def test_connect_no_port():
    from sciglob.core.exceptions import ConnectionError as ScConnectionError

    srb = SRB(port=None)
    with pytest.raises(ScConnectionError):
        srb.connect()


# -- exact command bytes -------------------------------------------------


def test_humidity_bytes_and_answer():
    srb = _srb(
        {"?": "SciGlobSRB1 ready\r", "H1": "Humidity(%):42.5\r"}
    )
    srb.connect()
    srb._connection.fake.written.clear()
    value = srb.get_humidity()
    assert value == 42.5
    assert srb._connection.written == [b"H1\r"]
    srb.disconnect()


def test_temperature_bytes_and_answer():
    srb = _srb(
        {"?": "SciGlobSRB1 ready\r", "T1": "Temperature(degC):23.75\r"}
    )
    srb.connect()
    srb._connection.fake.written.clear()
    value = srb.get_temperature()
    assert value == 23.75
    assert srb._connection.written == [b"T1\r"]
    srb.disconnect()


def test_pressure_bytes_and_answer():
    srb = _srb(
        {"?": "SciGlobSRB1 ready\r", "P1": "Pressure(hPa):1008.3\r"}
    )
    srb.connect()
    srb._connection.fake.written.clear()
    value = srb.get_pressure()
    assert value == 1008.3
    assert srb._connection.written == [b"P1\r"]
    srb.disconnect()


def test_answer_terminator_is_cr_not_crlf():
    # Answer ends with a bare "\r" (spec §2). Confirm the value still parses.
    srb = _srb({"?": "SciGlobSRB1 ready\r", "H1": "Humidity(%):55.0\r"})
    srb.connect()
    assert srb.get_humidity() == 55.0
    srb.disconnect()


# -- ':' value parsing ---------------------------------------------------


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Humidity(%):50.0", 50.0),
        ("Humidity(%):0", 0.0),
        ("Humidity(%): 12.5 ", 12.5),
        ("Humidity(%):-3.2", -3.2),
        ("Temperature(degC):100", 100.0),
    ],
)
def test_parse_value_after_first_colon(answer, expected):
    assert SRB._parse_value(answer) == expected


@pytest.mark.parametrize("answer", ["nocolonhere", "Humidity(%):notanumber", ""])
def test_parse_value_bad_returns_none(answer):
    assert SRB._parse_value(answer) is None


def test_parse_value_strips_cr():
    assert SRB._parse_value("Pressure(hPa):1013.25\r") == 1013.25


# -- sentinels on failed read --------------------------------------------


def test_humidity_sentinel_on_unparseable():
    srb = _srb({"?": "SciGlobSRB1 ready\r", "H1": "Humidity(%):bad\r"})
    srb.connect()
    assert srb.get_humidity() == SRB.INVALID_HUMIDITY == -9.0
    assert srb.consecutive_failures == 1
    srb.disconnect()


def test_temperature_sentinel_on_unparseable():
    srb = _srb({"?": "SciGlobSRB1 ready\r", "T1": "Temperature(degC):??\r"})
    srb.connect()
    assert srb.get_temperature() == SRB.INVALID_TEMPERATURE == 999.0
    srb.disconnect()


def test_pressure_sentinel_on_no_answer():
    # No mapping for P1 and no default -> transport stays silent -> timeout.
    srb = _srb({"?": "SciGlobSRB1 ready\r"}, timeout=0.05)
    srb.connect()
    assert srb.get_pressure() == SRB.INVALID_PRESSURE == -9.0
    srb.disconnect()


def test_success_resets_failure_counter():
    srb = _srb(
        {
            "?": "SciGlobSRB1 ready\r",
            "H1": "Humidity(%):bad\r",
            "T1": "Temperature(degC):20.0\r",
        }
    )
    srb.connect()
    assert srb.get_humidity() == -9.0
    assert srb.consecutive_failures == 1
    assert srb.get_temperature() == 20.0
    assert srb.consecutive_failures == 0
    srb.disconnect()


# -- aggregate + status --------------------------------------------------


def test_get_all_sensors():
    srb = _srb(
        {
            "?": "SciGlobSRB1 ready\r",
            "H1": "Humidity(%):48.0\r",
            "T1": "Temperature(degC):21.0\r",
            "P1": "Pressure(hPa):1000.0\r",
        }
    )
    srb.connect()
    assert srb.get_all_sensors() == {
        "humidity": 48.0,
        "temperature": 21.0,
        "pressure": 1000.0,
    }
    srb.disconnect()


def test_get_status_connected():
    srb = _srb(
        {
            "?": "SciGlobSRB1 ready\r",
            "H1": "Humidity(%):48.0\r",
            "T1": "Temperature(degC):21.0\r",
            "P1": "Pressure(hPa):1000.0\r",
        }
    )
    srb.connect()
    status = srb.get_status()
    assert status["connected"] is True
    assert status["port"] == "SIM_SRB"
    assert status["readings"]["pressure"] == 1000.0
    srb.disconnect()


def test_read_requires_connection():
    srb = _srb({"?": "SciGlobSRB1 ready\r"})
    with pytest.raises(DeviceError):
        srb.get_humidity()


def test_send_command_raw():
    srb = _srb({"?": "SciGlobSRB1 ready\r", "H1": "Humidity(%):33.3\r"})
    srb.connect()
    assert srb.send_command("H1") == "Humidity(%):33.3"
    srb.disconnect()


# -- error table ---------------------------------------------------------


def test_error_table_includes_pressure_code_5():
    assert SRB.ERROR_MESSAGES is ESP32_SENSOR_ERROR_MESSAGES
    assert SRB.ERROR_MESSAGES[5] == "Could not understand pressure reading"


# -- SimulatedSRB convenience --------------------------------------------


def test_simulated_srb_defaults():
    srb = SimulatedSRB()
    srb.connect()
    assert srb.get_humidity() == 50.0
    assert srb.get_temperature() == 25.0
    assert srb.get_pressure() == 1013.25
    srb.disconnect()


def test_simulated_srb_custom_values():
    srb = SimulatedSRB(humidity=10.0, temperature=5.0, pressure=900.0)
    srb.connect()
    assert srb.get_all_sensors() == {
        "humidity": 10.0,
        "temperature": 5.0,
        "pressure": 900.0,
    }
    srb.disconnect()


def test_context_manager():
    srb = SimulatedSRB()
    with srb:
        assert srb.is_connected
        assert srb.get_temperature() == 25.0
    assert not srb.is_connected
