"""Tests for Tracker functionality."""

import pytest
from sciglob.devices.tracker import Tracker
from sciglob.core.exceptions import TrackerError, PositionError
from sciglob.core.utils import degrees_to_steps, steps_to_degrees


class TestPositionConversion:
    """Tests for position conversion utilities."""
    
    def test_degrees_to_steps(self):
        """Test degree to step conversion."""
        # At home (180°), steps should be 0
        steps = degrees_to_steps(180.0, degrees_per_step=0.01, home_position=180.0)
        assert steps == 0
        
        # 90° from home
        steps = degrees_to_steps(90.0, degrees_per_step=0.01, home_position=180.0)
        assert steps == 9000
        
        # Negative steps
        steps = degrees_to_steps(270.0, degrees_per_step=0.01, home_position=180.0)
        assert steps == -9000
    
    def test_steps_to_degrees(self):
        """Test step to degree conversion."""
        # At step 0, should be home position
        degrees = steps_to_degrees(0, degrees_per_step=0.01, home_position=180.0)
        assert degrees == 180.0
        
        # Positive steps
        degrees = steps_to_degrees(9000, degrees_per_step=0.01, home_position=180.0)
        assert degrees == 90.0
        
        # Negative steps
        degrees = steps_to_degrees(-9000, degrees_per_step=0.01, home_position=180.0)
        assert degrees == 270.0


class TestTracker:
    """Tests for Tracker class."""
    
    def test_tracker_creation(self, tracker):
        """Test tracker creation."""
        assert tracker.degrees_per_step == 0.01
        assert tracker.is_luftblick is True
    
    def test_get_position_steps(self, tracker):
        """Test getting position in steps."""
        azi, zen = tracker.get_position_steps()
        assert azi == 0
        assert zen == 0
    
    def test_get_position_degrees(self, tracker):
        """Test getting position in degrees."""
        zen, azi = tracker.get_position()
        # At step 0, should be at home position
        assert zen == tracker.zenith_home
        assert azi == tracker.azimuth_home
    
    def test_move_to_steps(self, tracker):
        """Test moving to step position."""
        tracker.move_to_steps(zenith_steps=4500, azimuth_steps=-1200)
        # Verify command was sent
        tracker._hs.send_command.assert_called()
    
    def test_move_to_degrees(self, tracker):
        """Test moving to degree position."""
        tracker.move_to(zenith=45.0, azimuth=90.0)
        tracker._hs.send_command.assert_called()
    
    def test_move_to_invalid_zenith(self, tracker):
        """Test that invalid zenith raises PositionError."""
        with pytest.raises(PositionError) as exc_info:
            tracker.move_to(zenith=100.0, azimuth=180.0)
        assert exc_info.value.min_pos == 0
        assert exc_info.value.max_pos == 90
    
    def test_pan(self, tracker):
        """Test pan (azimuth only) movement."""
        tracker.pan(azimuth=90.0)
        tracker._hs.send_command.assert_called()
    
    def test_tilt(self, tracker):
        """Test tilt (zenith only) movement."""
        tracker.tilt(zenith=45.0)
        tracker._hs.send_command.assert_called()
    
    def test_home(self, tracker):
        """Test homing the tracker."""
        tracker.home()
        tracker._hs.send_command.assert_called()
    
    def test_reset(self, tracker):
        """Test soft reset."""
        result = tracker.reset()
        assert result is True
    
    def test_power_reset(self, tracker):
        """Test power reset."""
        result = tracker.power_reset()
        assert result is True
    
    def test_get_motor_temperatures(self, tracker):
        """Test getting motor temperatures (LuftBlickTR1)."""
        temps = tracker.get_motor_temperatures()
        assert "azimuth_driver_temp" in temps
    
    def test_get_motor_alarms(self, tracker):
        """Test getting motor alarms (LuftBlickTR1)."""
        alarms = tracker.get_motor_alarms()
        assert "zenith" in alarms
        assert "azimuth" in alarms
    
    def test_get_status(self, tracker):
        """Test getting tracker status."""
        status = tracker.get_status()
        assert "tracker_type" in status
        assert "degrees_per_step" in status
        assert "home_position" in status

