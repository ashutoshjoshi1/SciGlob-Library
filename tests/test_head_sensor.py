"""Tests for HeadSensor functionality."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from sciglob.devices.head_sensor import HeadSensor
from sciglob.core.exceptions import ConnectionError, DeviceError, SensorError


class TestHeadSensorInit:
    """Tests for HeadSensor initialization."""
    
    def test_default_init(self):
        """Test HeadSensor with default parameters."""
        hs = HeadSensor()
        assert hs.port is None
        assert hs.baudrate == 9600
        assert hs.timeout == 1.0
        assert hs.tracker_type == "Directed Perceptions"
        assert hs.degrees_per_step == 0.01
    
    def test_custom_init(self):
        """Test HeadSensor with custom parameters."""
        hs = HeadSensor(
            port="/dev/ttyUSB0",
            baudrate=19200,
            tracker_type="LuftBlickTR1",
            degrees_per_step=0.005,
            motion_limits=[0, 85, 10, 350],
            home_position=[5.0, 190.0],
        )
        assert hs.port == "/dev/ttyUSB0"
        assert hs.baudrate == 19200
        assert hs.tracker_type == "LuftBlickTR1"
        assert hs.degrees_per_step == 0.005
        assert hs.motion_limits == [0, 85, 10, 350]
        assert hs.home_position == [5.0, 190.0]
    
    def test_filter_wheel_config(self):
        """Test HeadSensor filter wheel configuration."""
        fw1 = ["OPEN", "U340", "BP300", "LPNIR", "ND1", "ND2", "ND3", "ND4", "OPAQUE"]
        fw2 = ["OPEN", "DIFF", "U340+DIFF", "BP300+DIFF", "LPNIR+DIFF", "ND1", "ND2", "ND3", "OPAQUE"]
        
        hs = HeadSensor(fw1_filters=fw1, fw2_filters=fw2)
        
        assert hs.fw1_filters == fw1
        assert hs.fw2_filters == fw2
    
    def test_not_connected_initially(self):
        """Test that HeadSensor is not connected initially."""
        hs = HeadSensor()
        assert hs.is_connected is False
        assert hs.device_id is None
        assert hs.sensor_type is None


class TestHeadSensorConnection:
    """Tests for HeadSensor connection management."""
    
    @patch('sciglob.devices.head_sensor.SerialConnection')
    def test_connect_success(self, mock_serial_class):
        """Test successful connection."""
        mock_conn = MagicMock()
        mock_conn.query.return_value = "SciGlobHSN2"
        mock_serial_class.return_value = mock_conn
        
        hs = HeadSensor(port="/dev/ttyUSB0")
        hs.connect()
        
        assert hs.is_connected is True
        assert hs.device_id == "SciGlobHSN2"
        assert hs.sensor_type == "SciGlobHSN2"
    
    @patch('sciglob.devices.head_sensor.SerialConnection')
    def test_connect_sciglob_hsn1(self, mock_serial_class):
        """Test connection to SciGlobHSN1."""
        mock_conn = MagicMock()
        mock_conn.query.return_value = "SciGlobHSN1"
        mock_serial_class.return_value = mock_conn
        
        hs = HeadSensor(port="/dev/ttyUSB0")
        hs.connect()
        
        assert hs.sensor_type == "SciGlobHSN1"
    
    def test_connect_no_port(self):
        """Test connection without port raises error."""
        hs = HeadSensor()
        
        with patch.object(hs, '_scan_for_head_sensor', return_value=None):
            with pytest.raises(ConnectionError):
                hs.connect()
    
    @patch('sciglob.devices.head_sensor.SerialConnection')
    def test_disconnect(self, mock_serial_class):
        """Test disconnection."""
        mock_conn = MagicMock()
        mock_conn.query.return_value = "SciGlobHSN2"
        mock_serial_class.return_value = mock_conn
        
        hs = HeadSensor(port="/dev/ttyUSB0")
        hs.connect()
        hs.disconnect()
        
        assert hs.is_connected is False
        mock_conn.close.assert_called_once()
    
    @patch('sciglob.devices.head_sensor.SerialConnection')
    def test_context_manager(self, mock_serial_class):
        """Test HeadSensor as context manager."""
        mock_conn = MagicMock()
        mock_conn.query.return_value = "SciGlobHSN2"
        mock_serial_class.return_value = mock_conn
        
        with HeadSensor(port="/dev/ttyUSB0") as hs:
            assert hs.is_connected is True
        
        mock_conn.close.assert_called()


class TestHeadSensorSensors:
    """Tests for HeadSensor sensor readings."""
    
    @pytest.fixture
    def connected_hs(self):
        """Create a connected HeadSensor mock."""
        hs = HeadSensor(port="/dev/ttyUSB0")
        hs._connected = True
        hs._sensor_type = "SciGlobHSN2"
        hs._connection = MagicMock()
        return hs
    
    def test_get_temperature(self, connected_hs):
        """Test temperature reading."""
        connected_hs._connection.query.return_value = "HT!25000"
        
        temp = connected_hs.get_temperature()
        assert temp == 250.0  # 25000 / 100
    
    def test_get_humidity(self, connected_hs):
        """Test humidity reading."""
        connected_hs._connection.query.return_value = "HT!51200"
        
        humidity = connected_hs.get_humidity()
        assert humidity == 50.0  # 51200 / 1024
    
    def test_get_pressure(self, connected_hs):
        """Test pressure reading."""
        connected_hs._connection.query.return_value = "HT!101325"
        
        pressure = connected_hs.get_pressure()
        assert pressure == 1013.25  # 101325 / 100
    
    def test_sensor_not_supported_on_hsn1(self):
        """Test that sensors are not supported on HSN1."""
        hs = HeadSensor(port="/dev/ttyUSB0")
        hs._connected = True
        hs._sensor_type = "SciGlobHSN1"
        hs._connection = MagicMock()
        
        with pytest.raises(SensorError):
            hs.get_temperature()
    
    def test_get_all_sensors(self, connected_hs):
        """Test getting all sensor readings."""
        connected_hs._connection.query.side_effect = [
            "HT!25000",  # temperature
            "HT!51200",  # humidity
            "HT!101325", # pressure
        ]
        
        sensors = connected_hs.get_all_sensors()
        
        assert "temperature" in sensors
        assert "humidity" in sensors
        assert "pressure" in sensors


class TestHeadSensorDeviceAccess:
    """Tests for accessing sub-devices through HeadSensor."""
    
    def test_tracker_access(self, mock_head_sensor):
        """Test accessing tracker through HeadSensor."""
        hs = HeadSensor(port="/dev/ttyUSB0")
        hs._connected = True
        hs._sensor_type = "SciGlobHSN2"
        hs._connection = MagicMock()
        hs._connection.query.return_value = "TR0"
        
        tracker = hs.tracker
        
        assert tracker is not None
        # Accessing again should return same instance
        assert hs.tracker is tracker
    
    def test_filter_wheel_access(self, mock_head_sensor):
        """Test accessing filter wheels through HeadSensor."""
        hs = HeadSensor(port="/dev/ttyUSB0")
        hs._connected = True
        hs._connection = MagicMock()
        
        fw1 = hs.filter_wheel_1
        fw2 = hs.filter_wheel_2
        
        assert fw1 is not None
        assert fw2 is not None
        assert fw1.wheel_id == 1
        assert fw2.wheel_id == 2
    
    def test_shadowband_access(self, mock_head_sensor):
        """Test accessing shadowband through HeadSensor."""
        hs = HeadSensor(port="/dev/ttyUSB0")
        hs._connected = True
        hs._connection = MagicMock()
        
        sb = hs.shadowband
        
        assert sb is not None


class TestHeadSensorCommands:
    """Tests for HeadSensor command sending."""
    
    @pytest.fixture
    def connected_hs(self):
        """Create a connected HeadSensor."""
        hs = HeadSensor(port="/dev/ttyUSB0")
        hs._connected = True
        hs._connection = MagicMock()
        return hs
    
    def test_send_command(self, connected_hs):
        """Test sending raw command."""
        connected_hs._connection.query.return_value = "TR0"
        
        response = connected_hs.send_command("TRw")
        
        assert response == "TR0"
        connected_hs._connection.query.assert_called_once()
    
    def test_send_command_not_connected(self):
        """Test sending command when not connected."""
        hs = HeadSensor(port="/dev/ttyUSB0")
        
        with pytest.raises(DeviceError):
            hs.send_command("TRw")
    
    def test_get_id(self, connected_hs):
        """Test getting device ID."""
        connected_hs._connection.query.return_value = "SciGlobHSN2"
        
        device_id = connected_hs.get_id()
        
        assert device_id == "SciGlobHSN2"
    
    def test_power_reset_tracker(self, connected_hs):
        """Test power reset for tracker."""
        connected_hs._connection.query.return_value = "TR0"
        
        result = connected_hs.power_reset("tracker")
        
        assert result is True


class TestHeadSensorStatus:
    """Tests for HeadSensor status reporting."""
    
    def test_get_status_disconnected(self):
        """Test status when disconnected."""
        hs = HeadSensor(port="/dev/ttyUSB0")
        
        status = hs.get_status()
        
        assert status["connected"] is False
        assert status["port"] == "/dev/ttyUSB0"
    
    def test_get_status_connected(self):
        """Test status when connected."""
        hs = HeadSensor(port="/dev/ttyUSB0")
        hs._connected = True
        hs._device_id = "SciGlobHSN2"
        hs._sensor_type = "SciGlobHSN2"
        hs._tracker_type = "LuftBlickTR1"
        hs._connection = MagicMock()
        hs._connection.query.side_effect = [
            "HT!25000", "HT!51200", "HT!101325"
        ]
        
        status = hs.get_status()
        
        assert status["connected"] is True
        assert status["device_id"] == "SciGlobHSN2"
        assert status["sensor_type"] == "SciGlobHSN2"
        assert status["tracker_type"] == "LuftBlickTR1"
        assert "sensors" in status

