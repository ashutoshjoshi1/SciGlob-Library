"""Regression tests for bugs fixed in 0.1.6.

Each test pins behaviour that was previously broken:

* Astronomical timing — solar noon was ~6 h off (bad equation of time),
  lunar illumination oscillated daily, and moonrise/moonset were never computed.
* ``TemperatureController.connect()`` always failed (``_query`` checked
  ``_connected`` before verification set it).
* ``Tracker.check_alarms()`` reported a read failure (code ``-1``) as an alarm.
* Shadowband math raised ``ZeroDivisionError`` / domain errors at ``ratio >= 1``.
* ``GlobalSatGPS._query()`` dropped the command terminator.
* ``exec()`` / ``eval()`` of routine-file content (remote code execution).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from sciglob.automation.executor import RoutineExecutor
from sciglob.automation.routines import RoutineCommand, RoutineKeyword
from sciglob.automation.timing import TimeCalculator
from sciglob.core.utils import (
    position_to_shadowband_angle,
    shadowband_angle_to_position,
)


class TestSolarTiming:
    """Solar noon / sunrise / sunset (timing.py)."""

    def test_solar_noon_near_midday_at_prime_meridian(self):
        # At longitude 0, solar noon is ~12:00 UTC (was ~18:00 due to bad EoT).
        tc = TimeCalculator(latitude=0.0, longitude=0.0)
        ev = tc.calculate_events(datetime(2024, 6, 20, tzinfo=timezone.utc))
        assert ev.solar_noon.hour in (11, 12)

    def test_hour_angle_is_zero_at_solar_noon(self):
        # Sun is on the local meridian (hour angle ~0) at computed solar noon.
        tc = TimeCalculator(latitude=48.14, longitude=11.58)
        ev = tc.calculate_events(datetime(2024, 6, 21, tzinfo=timezone.utc))
        ha = tc.calculate_solar_position(ev.solar_noon).hour_angle
        assert abs(ha) < 0.05  # degrees

    def test_sunrise_before_noon_before_sunset(self):
        tc = TimeCalculator(latitude=40.0, longitude=-105.0)
        ev = tc.calculate_events(datetime(2024, 3, 20, tzinfo=timezone.utc))
        assert ev.sunrise < ev.solar_noon < ev.sunset


class TestLunarTiming:
    """Lunar phase / illumination / rise / set (timing.py)."""

    def test_illumination_stable_across_day(self):
        # The old formula tracked sidereal time and swung 0->1 within a day.
        tc = TimeCalculator(latitude=0.0, longitude=0.0)
        vals = [
            tc.calculate_lunar_position(datetime(2024, 6, 22, h, tzinfo=timezone.utc)).illumination
            for h in range(0, 24, 3)
        ]
        assert max(vals) - min(vals) < 0.1

    def test_illumination_extremes(self):
        tc = TimeCalculator(latitude=0.0, longitude=0.0)
        new_moon = tc.calculate_lunar_position(datetime(2024, 6, 6, 12, tzinfo=timezone.utc))
        full_moon = tc.calculate_lunar_position(datetime(2024, 6, 22, 1, tzinfo=timezone.utc))
        assert new_moon.illumination < 0.1
        assert full_moon.illumination > 0.9

    def test_moonrise_moonset_populated(self):
        tc = TimeCalculator(latitude=48.14, longitude=11.58)
        ev = tc.calculate_events(datetime(2024, 6, 21, tzinfo=timezone.utc))
        assert ev.moonrise is not None
        assert ev.moonset is not None


class TestShadowbandMath:
    """Numerical safety in shadowband conversions (utils.py)."""

    def test_no_crash_at_ratio_one(self):
        # ratio=1 with alfa=0 previously raised ZeroDivisionError / domain error.
        assert isinstance(position_to_shadowband_angle(250, 0.36, 1.0), float)
        assert isinstance(shadowband_angle_to_position(90.0, 0.36, 1.0), int)

    def test_default_ratio_roundtrip(self):
        pos = shadowband_angle_to_position(30.0, 0.36, 0.5)
        angle = position_to_shadowband_angle(pos, 0.36, 0.5)
        assert abs(angle - 30.0) < 5.0


class TestTemperatureControllerConnect:
    """TemperatureController.connect() must succeed (temperature_controller.py)."""

    def test_connect_succeeds(self):
        from sciglob.devices.temperature_controller import TemperatureController

        with patch("sciglob.devices.temperature_controller.SerialConnection") as MockConn:
            MockConn.return_value.read_until.return_value = b"*0060ab^"
            tc = TemperatureController(port="COM1", controller_type="TETech1")
            tc.connect()  # previously raised ConnectionError unconditionally
            assert tc.is_connected is True
            tc.disconnect()


def _luftblick_tracker(alarm_response: str):
    """Build a Tracker on a mock head sensor returning a fixed alarm response."""
    from sciglob.devices.tracker import Tracker

    hs = MagicMock()
    hs._connected = True
    hs.tracker_type = "LuftBlickTR1"
    hs.degrees_per_step = 0.01
    hs.motion_limits = [0, 90, 0, 360]
    hs.home_position = [0.0, 180.0]
    hs.send_command = MagicMock(return_value=alarm_response)
    return Tracker(hs)


class TestTrackerAlarms:
    """check_alarms() must distinguish read failures from real alarms."""

    def test_read_failure_does_not_raise(self):
        # "MZxy" -> int("xy") fails -> code -1; must not be reported as an alarm.
        tracker = _luftblick_tracker("MZxy")
        tracker.check_alarms()  # must not raise

    def test_real_alarm_raises(self):
        from sciglob.core.exceptions import MotorAlarmError

        tracker = _luftblick_tracker("Alarm Code = 26")
        with pytest.raises(MotorAlarmError):
            tracker.check_alarms()


class TestGlobalSatQuery:
    """GlobalSatGPS._query() must send commands with the protocol terminator."""

    def test_query_sends_with_terminator(self):
        from sciglob.devices.positioning import GlobalSatGPS

        gps = GlobalSatGPS(port="COM1")
        gps._connection = MagicMock()
        gps._connection.read_until.return_value = b"$GPGGA,,,,,,0,,,,,,,,*00\r\n"
        gps.send_command("$PSRF103,00,01,00,01*25")
        _, kwargs = gps._connection.send_command.call_args
        assert kwargs.get("end_char") == "\r\n"  # was "" (no terminator)


class TestNoCodeExecution:
    """Routine files must never trigger code execution (executor.py)."""

    def test_command_does_not_exec(self):
        import os

        os.environ.pop("SCIGLOB_RCE", None)
        ex = RoutineExecutor()
        cmd = RoutineCommand(
            keyword=RoutineKeyword.COMMAND,
            subkeywords={"VALUE": "import os; os.environ['SCIGLOB_RCE']='1'"},
        )
        ex._execute_custom_command(cmd)
        assert "SCIGLOB_RCE" not in os.environ

    def test_xij_literal_parsed_safely(self):
        ex = RoutineExecutor()
        cmd = RoutineCommand(
            keyword=RoutineKeyword.START_LOOP,
            subkeywords={"XIJ": "[10, 20, 30]"},
        )
        ex._start_loop(cmd, [], 0)
        assert ex.context.loop_stack[-1]["values"] == [10, 20, 30]

    def test_xij_non_literal_not_executed(self):
        ex = RoutineExecutor()
        payload = "__import__('os').system('echo hacked')"
        cmd = RoutineCommand(
            keyword=RoutineKeyword.START_LOOP,
            subkeywords={"XIJ": payload},
        )
        ex._start_loop(cmd, [], 0)
        # Non-literal falls back to the raw string as a single loop value.
        assert ex.context.loop_stack[-1]["values"] == [payload]
