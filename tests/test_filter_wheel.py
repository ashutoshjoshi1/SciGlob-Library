"""Tests for FilterWheel functionality."""

import pytest
from sciglob.devices.filter_wheel import FilterWheel
from sciglob.core.exceptions import FilterWheelError


class TestFilterWheel:
    """Tests for FilterWheel class."""
    
    def test_filter_wheel_creation(self, filter_wheel_1):
        """Test filter wheel creation."""
        assert filter_wheel_1.wheel_id == 1
        assert filter_wheel_1.device_id == "F1"
        assert filter_wheel_1.num_positions == 9
    
    def test_filter_wheel_2_creation(self, filter_wheel_2):
        """Test filter wheel 2 creation."""
        assert filter_wheel_2.wheel_id == 2
        assert filter_wheel_2.device_id == "F2"
    
    def test_invalid_wheel_id(self, mock_head_sensor):
        """Test that invalid wheel ID raises error."""
        with pytest.raises(ValueError):
            FilterWheel(mock_head_sensor, wheel_id=3)
    
    def test_get_filter_names(self, filter_wheel_1):
        """Test getting filter names."""
        names = filter_wheel_1.filter_names
        assert len(names) == 9
        assert "OPEN" in names
        assert "U340" in names
    
    def test_set_position(self, filter_wheel_1):
        """Test setting position."""
        filter_wheel_1.set_position(5)
        assert filter_wheel_1.position == 5
    
    def test_set_invalid_position_low(self, filter_wheel_1):
        """Test that position 0 raises error."""
        with pytest.raises(ValueError):
            filter_wheel_1.set_position(0)
    
    def test_set_invalid_position_high(self, filter_wheel_1):
        """Test that position 10 raises error."""
        with pytest.raises(ValueError):
            filter_wheel_1.set_position(10)
    
    def test_set_filter_by_name(self, filter_wheel_1):
        """Test setting filter by name."""
        filter_wheel_1.set_filter("U340")
        assert filter_wheel_1.position == 2  # U340 is at position 2
    
    def test_set_filter_case_insensitive(self, filter_wheel_1):
        """Test case-insensitive filter name."""
        filter_wheel_1.set_filter("u340")
        assert filter_wheel_1.position == 2
    
    def test_set_invalid_filter(self, filter_wheel_1):
        """Test that invalid filter name raises error."""
        with pytest.raises(FilterWheelError):
            filter_wheel_1.set_filter("INVALID_FILTER")
    
    def test_current_filter(self, filter_wheel_1):
        """Test getting current filter name."""
        filter_wheel_1.set_position(1)
        assert filter_wheel_1.current_filter == "OPEN"
        
        filter_wheel_1.set_position(2)
        assert filter_wheel_1.current_filter == "U340"
    
    def test_reset(self, filter_wheel_1):
        """Test resetting filter wheel."""
        filter_wheel_1.set_position(5)
        filter_wheel_1.reset()
        assert filter_wheel_1.position == 1  # Reset goes to position 1
    
    def test_get_filter_map(self, filter_wheel_1):
        """Test getting filter map."""
        filter_map = filter_wheel_1.get_filter_map()
        assert filter_map[1] == "OPEN"
        assert filter_map[2] == "U340"
        assert len(filter_map) == 9
    
    def test_get_position_for_filter(self, filter_wheel_1):
        """Test getting position for filter name."""
        pos = filter_wheel_1.get_position_for_filter("U340")
        assert pos == 2
        
        pos = filter_wheel_1.get_position_for_filter("NONEXISTENT")
        assert pos is None
    
    def test_get_available_filters(self, filter_wheel_1):
        """Test getting available filters."""
        filters = filter_wheel_1.get_available_filters()
        assert len(filters) == 9
        assert "OPEN" in filters
    
    def test_get_status(self, filter_wheel_1):
        """Test getting status."""
        filter_wheel_1.set_position(3)
        status = filter_wheel_1.get_status()
        
        assert status["wheel_id"] == 1
        assert status["position"] == 3
        assert "filter_map" in status
