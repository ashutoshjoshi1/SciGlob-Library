"""Hardening tests for HeadSensor (sciglob 0.2.0).

These drive the real QA/recovery code paths through an injected
``SimulatedTransport`` - no serial hardware, no mocks of the transport.
They cover:

* the spectrometer power-cycle safety hook and its critical ordering
  (hook fires BEFORE the ``S<n>s`` relay byte is written) - the v0.0.8.7
  crash-class regression;
* motor alarm / temperature / current decoding;
* each recovery-ladder step individually, plus full-ladder success and
  exhaustion.
"""

import pytest

from sciglob.core.connection import PortRegistry
from sciglob.core.exceptions import RecoveryFailed
from sciglob.core.simulation import SimulatedTransport, make_responder
from sciglob.devices.head_sensor import HeadSensor, SimulatedHeadSensor


@pytest.fixture(autouse=True)
def _clear_registry():
    """Keep the process-wide port registry clean between tests."""
    PortRegistry.clear()
    yield
    PortRegistry.clear()


def _make_hs(mapping, *, port="SIM_HST", default="\n", sensor_type="SciGlobHSN2"):
    """Build a connected HeadSensor over a SimulatedTransport with `mapping`.

    Injects the transport exactly the way the task describes: assign
    ``_connection`` and set ``_connected`` (plus the identity fields a
    connected head sensor would have).
    """
    transport = SimulatedTransport(
        responder=make_responder(mapping, default=default),
        port=port,
        owner="test-hs",
    )
    transport.open()
    hs = HeadSensor(name="HeadSensor", sensor_type=sensor_type, tracker_type="LuftBlickTR1")
    hs._connection = transport
    hs._connected = True
    hs._device_id = sensor_type
    hs._sensor_type = sensor_type
    return hs, transport


# ---------------------------------------------------------------------------
# Spectrometer power-cycle hook + ordering
# ---------------------------------------------------------------------------


class TestSpecPowerCycleHook:
    def test_hook_fires_before_relay_write(self):
        """The hook must run BEFORE the S<n>s relay byte is written."""
        hs, transport = _make_hs({"S1s": "S10\n"}, port="SIM_HOOK1")

        events = []

        def recording_hook(spec):
            # snapshot exactly what has been written at hook time
            events.append((spec, list(transport.written)))

        hs.set_spec_power_cycle_hook(recording_hook)
        assert hs.spec_power_cycle(1) is True

        # Hook fired exactly once, with the right spec number.
        assert len(events) == 1
        assert events[0][0] == 1
        # At hook time, NOTHING had been written yet - in particular no S1s.
        assert events[0][1] == []
        assert all(b"S1s" not in w for w in events[0][1])
        # The relay command really was written afterwards.
        assert b"S1s\r" in transport.written

    def test_spec2_delegates_and_returns(self):
        hs, transport = _make_hs({"S2s": "S20\n"}, port="SIM_HOOK2")
        fired = []
        hs.set_spec_power_cycle_hook(fired.append)
        assert hs.spec_power_cycle(2) is True
        assert fired == [2]
        assert b"S2s\r" in transport.written

    def test_no_hook_is_noop(self):
        hs, transport = _make_hs({"S1s": "S10\n"}, port="SIM_HOOK3")
        assert hs.spec_power_cycle(1) is True
        assert b"S1s\r" in transport.written

    def test_register_alias_and_property(self):
        hs, _ = _make_hs({"S1s": "S10\n"}, port="SIM_HOOK4")
        cb = lambda spec: None  # noqa: E731
        hs.register_spec_power_hook(cb)
        assert hs.spec_power_cycle_hook is cb
        hs.spec_power_cycle_hook = None
        assert hs.spec_power_cycle_hook is None

    def test_invalid_spec_raises(self):
        hs, _ = _make_hs({}, port="SIM_HOOK5")
        with pytest.raises(ValueError):
            hs.spec_power_cycle(3)

    def test_hook_exception_prevents_relay(self):
        """If the safety hook raises, the relay is NOT fired (fail loud)."""
        hs, transport = _make_hs({"S1s": "S10\n"}, port="SIM_HOOK6")

        def bad_hook(spec):
            raise RuntimeError("handle still live")

        hs.set_spec_power_cycle_hook(bad_hook)
        with pytest.raises(RuntimeError):
            hs.spec_power_cycle(1)
        assert all(b"S1s" not in w for w in transport.written)


# ---------------------------------------------------------------------------
# Motor alarms
# ---------------------------------------------------------------------------


class TestMotorAlarms:
    def test_luftblick_alarm_codes(self):
        hs, _ = _make_hs(
            {"MZa?": "Alarm Code = 22\n", "MAa?": "Alarm Code = 0\n"},
            port="SIM_ALARM1",
        )
        alarms = hs.get_motor_alarms()
        assert alarms["zenith"] == (22, "Overvoltage in the motor driver")
        assert alarms["azimuth"] == (0, "No alarm")

    def test_head_sensor_echo_code_cabling_fault(self):
        """MZ5/MA5 = head-sensor error 5 (cannot read tracker driver register)."""
        hs, _ = _make_hs(
            {"MZa?": "MZ5\n", "MAa?": "MA5\n"},
            port="SIM_ALARM2",
        )
        alarms = hs.get_motor_alarms()
        assert alarms["zenith"] == (5, "Cannot read from tracker driver register")
        assert alarms["azimuth"] == (5, "Cannot read from tracker driver register")


# ---------------------------------------------------------------------------
# Motor temperatures / currents
# ---------------------------------------------------------------------------


class TestMotorTemperatures:
    def test_decode_all_four(self):
        hs, _ = _make_hs(
            {
                "MZd?": "MZ!235\n",
                "MZm?": "MZ!247\n",
                "MAd?": "MA!212\n",
                "MAm?": "MA!229\n",
            },
            port="SIM_TEMP1",
        )
        temps = hs.get_motor_temperatures()
        assert temps == {
            "zenith_driver": 23.5,
            "zenith_motor": 24.7,
            "azimuth_driver": 21.2,
            "azimuth_motor": 22.9,
        }

    def test_error_answer_yields_sentinel(self):
        hs, _ = _make_hs(
            {
                "MZd?": "MZ!235\n",
                "MZm?": "MZ7\n",  # error code -> sentinel
                "MAd?": "MA!212\n",
                "MAm?": "MA!229\n",
            },
            port="SIM_TEMP2",
        )
        temps = hs.get_motor_temperatures()
        assert temps["zenith_driver"] == 23.5
        assert temps["zenith_motor"] == 999.0


class TestMotorCurrents:
    def test_decode(self):
        hs, transport = _make_hs(
            {"MZc?": "MZ!158\n", "MAc?": "MA!163\n"},
            port="SIM_CURR1",
        )
        currents = hs.get_motor_currents()
        assert currents == {"zenith": 15.8, "azimuth": 16.3}
        assert b"MZc?\r" in transport.written
        assert b"MAc?\r" in transport.written


# ---------------------------------------------------------------------------
# Recovery ladder - individual steps
# ---------------------------------------------------------------------------


class TestRecoverySteps:
    def test_check_id_success(self):
        hs, _ = _make_hs({"?": "SciGlobHSN2\n"}, port="SIM_REC1")
        assert hs._recover_check_id(timeout=0.2) is True

    def test_check_id_failure_when_silent(self):
        hs, _ = _make_hs({}, port="SIM_REC2", default=None)
        assert hs._recover_check_id(timeout=0.05) is False

    def test_reset_pulse_pulses_dtr(self):
        hs, transport = _make_hs({}, port="SIM_REC3")
        assert hs._recover_reset_pulse(hold=0.5) is True
        # reset_pulse drops DTR low then re-asserts.
        assert ("dtr", False) in transport.line_events
        assert ("dtr", True) in transport.line_events
        assert ("sleep", 0.5) in transport.line_events

    def test_dtr_cycle_uses_field_hold(self):
        hs, transport = _make_hs({}, port="SIM_REC4")
        assert hs._recover_dtr_cycle() is True
        # field-verified 3 s hold twice (low, then settle).
        sleeps = [e.value for e in transport.line_events if e.line == "sleep"]
        assert sleeps == [3.0, 3.0]

    def test_reopen_port_reopens(self):
        hs, _ = _make_hs({"?": "SciGlobHSN2\n"}, port="SIM_REC5")
        assert hs._recover_reopen_port() is True
        assert hs._connection.is_open is True
        # communication works after reopen
        assert hs._recover_check_id(timeout=0.2) is True

    def test_peripheral_reset(self):
        hs, transport = _make_hs({"TRr": "TR0\n"}, port="SIM_REC6")
        assert hs._recover_peripheral_reset() is True
        assert b"TRr\r" in transport.written

    def test_power_reset(self):
        hs, transport = _make_hs({"TRs": "TR0\n"}, port="SIM_REC7")
        assert hs._recover_power_reset() is True
        assert b"TRs\r" in transport.written


# ---------------------------------------------------------------------------
# Recovery ladder - full runs
# ---------------------------------------------------------------------------


class _HealAfterCommand:
    """Stateful responder: the link is dead until a heal-command is seen."""

    def __init__(self, id_str, heal_cmd):
        self.id = id_str
        self.heal_cmd = heal_cmd
        self.healthy = False

    def __call__(self, data):
        cmd = data.decode("latin-1").rstrip("\r")
        if cmd == self.heal_cmd:
            self.healthy = True
            return "TR0\n"
        if cmd == "?":
            return f"{self.id}\n" if self.healthy else None
        if cmd in ("TRr", "TRs"):
            return "TR0\n"
        return None


class TestRecoveryLadder:
    def test_recovered_immediately_at_check_id(self):
        hs, _ = _make_hs({"?": "SciGlobHSN2\n"}, port="SIM_LAD1")
        result = hs.recover(verify_timeout=0.2)
        assert result["recovered"] is True
        assert result["final_step"] == "check_id"
        assert len(result["steps"]) == 1
        assert result["device"] == "HeadSensor"

    def test_recovered_after_power_reset(self):
        transport = SimulatedTransport(
            responder=_HealAfterCommand("SciGlobHSN2", "TRs"),
            port="SIM_LAD2",
            owner="test-hs",
        )
        transport.open()
        hs = HeadSensor(name="HeadSensor", sensor_type="SciGlobHSN2")
        hs._connection = transport
        hs._connected = True
        hs._device_id = "SciGlobHSN2"
        hs._sensor_type = "SciGlobHSN2"

        result = hs.recover(verify_timeout=0.05)
        assert result["recovered"] is True
        assert result["final_step"] == "power_reset"
        step_names = [s["step"] for s in result["steps"]]
        # ladder walked through the cheaper steps first, in order
        assert step_names == [
            "check_id",
            "reset_pulse",
            "dtr_cycle",
            "reopen_port",
            "peripheral_reset",
            "power_reset",
        ]

    def test_ladder_exhausted_raises(self):
        # Never answers "?", so no step can restore communication.
        transport = SimulatedTransport(
            responder=make_responder({"TRr": "TR0\n", "TRs": "TR0\n"}, default=None),
            port="SIM_LAD3",
            owner="test-hs",
        )
        transport.open()
        hs = HeadSensor(name="HeadSensor", sensor_type="SciGlobHSN2")
        hs._connection = transport
        hs._connected = True
        hs._device_id = "SciGlobHSN2"
        hs._sensor_type = "SciGlobHSN2"

        with pytest.raises(RecoveryFailed) as excinfo:
            hs.recover(verify_timeout=0.05, wait_retries=1)
        assert excinfo.value.device == "HeadSensor"

    def test_recover_requires_connection(self):
        hs = HeadSensor(name="HeadSensor")
        from sciglob.core.exceptions import DeviceError

        with pytest.raises(DeviceError):
            hs.recover()


# ---------------------------------------------------------------------------
# Simulated convenience twin
# ---------------------------------------------------------------------------


class TestSimulatedHeadSensor:
    def test_builds_connected_twin(self):
        hs = SimulatedHeadSensor(port="SIM_TWIN1")
        try:
            assert hs.is_connected is True
            assert hs.sensor_type == "SciGlobHSN2"
            assert hs.get_motor_alarms()["zenith"] == (0, "No alarm")
            temps = hs.get_motor_temperatures()
            assert temps["zenith_driver"] == 23.5
            assert hs.spec_power_cycle(1) is True
        finally:
            hs.disconnect()
