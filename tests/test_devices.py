"""Tests for other device modules."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from sciglob.devices.shadowband import Shadowband
from sciglob.devices.temperature_controller import TemperatureController
from sciglob.devices.humidity_sensor import HumiditySensor
from sciglob.devices.positioning import GlobalSatGPS, NovatelGPS
from sciglob.core.exceptions import ConnectionError, DeviceError, SensorError


class TestShadowband:
    """Tests for Shadowband class."""
    
    @pytest.fixture
    def shadowband(self, mock_head_sensor):
        """Create a Shadowband instance."""
        return Shadowband(mock_head_sensor)
    
    def test_init(self, shadowband):
        """Test Shadowband initialization."""
        assert shadowband.position == 0
        assert shadowband.resolution == 0.36
        assert shadowband.ratio == 0.5
    
    def test_move_to_position(self, shadowband):
        """Test moving to step position."""
        shadowband.move_to_position(500)
        assert shadowband.position == 500
    
    def test_move_to_position_negative(self, shadowband):
        """Test moving to negative position."""
        shadowband.move_to_position(-300)
        assert shadowband.position == -300
    
    def test_move_to_angle(self, shadowband):
        """Test moving to angle."""
        shadowband.move_to_angle(30.0)
        # Position should be calculated
        assert shadowband.position != 0
    
    def test_move_relative(self, shadowband):
        """Test relative movement."""
        shadowband.move_to_position(500)
        shadowband.move_relative(100)
        assert shadowband.position == 600
    
    def test_reset(self, shadowband):
        """Test resetting shadowband."""
        shadowband.move_to_position(500)
        shadowband.reset()
        assert shadowband.position == 0
    
    def test_get_status(self, shadowband):
        """Test getting status."""
        shadowband.move_to_position(500)
        status = shadowband.get_status()
        
        assert status["position"] == 500
        assert "angle" in status
        assert status["resolution"] == 0.36


class TestTemperatureController:
    """Tests for TemperatureController class."""
    
    def test_init_tetech1(self):
        """Test TETech1 initialization."""
        tc = TemperatureController(
            port="/dev/ttyUSB0",
            controller_type="TETech1"
        )
        assert tc.controller_type == "TETech1"
        assert tc.nbits == 16
    
    def test_init_tetech2(self):
        """Test TETech2 initialization."""
        tc = TemperatureController(
            port="/dev/ttyUSB0",
            controller_type="TETech2"
        )
        assert tc.controller_type == "TETech2"
        assert tc.nbits == 32
    
    def test_init_invalid_type(self):
        """Test initialization with invalid type."""
        with pytest.raises(ValueError):
            TemperatureController(controller_type="Invalid")
    
    @patch('sciglob.devices.temperature_controller.SerialConnection')
    def test_connect(self, mock_serial_class):
        """Test connection."""
        mock_conn = MagicMock()
        # Mock the serial read behavior for connection verification
        mock_serial_class.return_value = mock_conn
        
        tc = TemperatureController(port="/dev/ttyUSB0")
        # Mock _verify_connection to return True
        tc._verify_connection = MagicMock(return_value=True)
        tc.connect()
        
        assert tc.is_connected is True
    
    def test_build_command_tetech1(self):
        """Test command building for TETech1."""
        tc = TemperatureController(controller_type="TETech1")
        
        # Test without value
        cmd = tc._build_command("1c", 250)
        assert cmd.startswith("*")
        assert "1c" in cmd
    
    @pytest.fixture
    def connected_tc(self):
        """Create a connected TemperatureController."""
        tc = TemperatureController(port="/dev/ttyUSB0", controller_type="TETech1")
        tc._connected = True
        tc._connection = MagicMock()
        return tc
    
    def test_set_temperature(self, connected_tc):
        """Test setting temperature."""
        connected_tc._connection.read_until.return_value = b"00fa^"
        
        result = connected_tc.set_temperature(25.0)
        assert result is True
    
    def test_get_status(self):
        """Test getting status when disconnected."""
        tc = TemperatureController(port="/dev/ttyUSB0")
        status = tc.get_status()
        
        assert status["connected"] is False
        assert status["controller_type"] == "TETech1"


class TestHumiditySensor:
    """Tests for HumiditySensor class."""
    
    def test_init(self):
        """Test initialization."""
        hs = HumiditySensor(port="/dev/ttyUSB0")
        assert hs.port == "/dev/ttyUSB0"
        assert hs.is_connected is False
        assert hs.is_initialized is False
    
    @patch('sciglob.devices.humidity_sensor.SerialConnection')
    def test_connect(self, mock_serial_class):
        """Test connection."""
        mock_conn = MagicMock()
        mock_conn.read_until.side_effect = [
            b"S,HDC2080EVM,part,\r\n",  # ID response
            b"stream stop\r\n",          # Initialize response
        ]
        mock_serial_class.return_value = mock_conn
        
        hs = HumiditySensor(port="/dev/ttyUSB0")
        hs.connect()
        
        assert hs.is_connected is True
    
    @pytest.fixture
    def connected_hs(self):
        """Create a connected HumiditySensor."""
        hs = HumiditySensor(port="/dev/ttyUSB0")
        hs._connected = True
        hs._initialized = True
        hs._connection = MagicMock()
        return hs
    
    def test_get_temperature(self, connected_hs):
        """Test getting temperature."""
        connected_hs._connection.read_until.return_value = b"6666\r\n"
        
        temp = connected_hs.get_temperature()
        assert -40 <= temp <= 125  # Valid range
    
    def test_get_humidity(self, connected_hs):
        """Test getting humidity."""
        connected_hs._connection.read_until.return_value = b"8000\r\n"
        
        humidity = connected_hs.get_humidity()
        assert 0 <= humidity <= 100
    
    def test_get_readings(self, connected_hs):
        """Test getting all readings."""
        connected_hs._connection.read_until.side_effect = [
            b"6666\r\n",  # temperature
            b"8000\r\n",  # humidity
        ]
        
        readings = connected_hs.get_readings()
        
        assert "temperature" in readings
        assert "humidity" in readings


class TestGlobalSatGPS:
    """Tests for GlobalSatGPS class."""
    
    def test_init(self):
        """Test initialization."""
        gps = GlobalSatGPS(port="/dev/ttyUSB0")
        assert gps.port == "/dev/ttyUSB0"
        assert gps.is_connected is False
    
    @pytest.fixture
    def connected_gps(self):
        """Create a connected GPS."""
        gps = GlobalSatGPS(port="/dev/ttyUSB0")
        gps._connected = True
        gps._configured = True
        gps._connection = MagicMock()
        return gps
    
    def test_parse_gpgga_valid(self, connected_gps):
        """Test parsing valid GPGGA message."""
        response = "$GPGGA,170145.000,3859.3500,N,07652.8949,W,1,07,1.7,42.0,M,-33.5,M,,0000*5C\r\n"
        
        result = connected_gps._parse_gpgga(response)
        
        assert result["quality"] == 1
        assert result["latitude"] > 0  # North
        assert result["longitude"] < 0  # West
        assert result["satellites"] == 7
    
    def test_parse_gpgga_no_fix(self, connected_gps):
        """Test parsing GPGGA with no fix."""
        response = "$GPGGA,170145.000,,,,,0,00,99.9,,,,,*48\r\n"
        
        result = connected_gps._parse_gpgga(response)
        
        assert result["quality"] == 0
        assert "error" in result
    
    def test_parse_gpgga_no_message(self, connected_gps):
        """Test parsing without GPGGA message."""
        response = "garbage data\r\n"
        
        result = connected_gps._parse_gpgga(response)
        
        assert "error" in result


class TestNovatelGPS:
    """Tests for NovatelGPS class."""
    
    def test_init(self):
        """Test initialization."""
        gps = NovatelGPS(port="/dev/ttyUSB0")
        assert gps.port == "/dev/ttyUSB0"
        assert gps.is_connected is False
    
    @pytest.fixture
    def connected_gps(self):
        """Create a connected Novatel GPS."""
        gps = NovatelGPS(port="/dev/ttyUSB0")
        gps._connected = True
        gps._configured = True
        gps._connection = MagicMock()
        return gps
    
    def test_parse_inspva_valid(self, connected_gps):
        """Test parsing valid INSPVA message."""
        response = """<INSPVA USB1 0 95.0 FINESTEERING 1918 131036.000 20000000 0000 312
< 1918 131036.002500000 52.458109776 13.310504415 112.364119180 0.003697356 0.001826098 0.000169055 0.188712512 -0.332215923 350.645755624 INS_SOLUTION_GOOD"""
        
        result = connected_gps._parse_inspva(response)
        
        assert result is not None
        assert abs(result["latitude"] - 52.458109776) < 0.0001
        assert abs(result["longitude"] - 13.310504415) < 0.0001
        assert result["status"] == "INS_SOLUTION_GOOD"
    
    def test_parse_inspva_no_message(self, connected_gps):
        """Test parsing without INSPVA message."""
        response = "garbage data\r\n"
        
        result = connected_gps._parse_inspva(response)
        
        assert result is None
    
    def test_get_orientation(self, connected_gps):
        """Test getting orientation."""
        connected_gps._last_inspva = {
            "roll": 0.5,
            "pitch": -0.3,
            "yaw": 180.0,
        }
        
        orient = connected_gps.get_orientation()
        
        assert orient["roll"] == 0.5
        assert orient["pitch"] == -0.3
        assert orient["yaw"] == 180.0


class TestDeviceIntegration:
    """Integration tests for device interactions."""
    
    def test_head_sensor_tracker_filter_workflow(self, mock_head_sensor):
        """Test typical workflow with tracker and filter wheel."""
        # This tests the mock infrastructure works correctly
        
        # Create tracker and filter wheel from mock
        from sciglob.devices.tracker import Tracker
        from sciglob.devices.filter_wheel import FilterWheel
        
        tracker = Tracker(mock_head_sensor)
        fw1 = FilterWheel(mock_head_sensor, wheel_id=1)
        
        # Test tracker operations
        tracker.move_to(zenith=45.0, azimuth=180.0)
        mock_head_sensor.send_command.assert_called()
        
        # Test filter wheel operations
        fw1.set_position(2)
        assert fw1.position == 2

