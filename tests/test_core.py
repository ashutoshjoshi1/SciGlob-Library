"""Tests for core module functionality."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from sciglob.core.exceptions import (
    SciGlobError,
    ConnectionError,
    CommunicationError,
    DeviceError,
    TimeoutError,
    ConfigurationError,
    TrackerError,
    MotorError,
    FilterWheelError,
    PositionError,
    HomingError,
    MotorAlarmError,
    SensorError,
    RecoveryError,
)
from sciglob.core.protocols import (
    DeviceType,
    ErrorCode,
    MotorAlarmCode,
    SerialConfig,
    get_error_message,
    get_motor_alarm_message,
    ERROR_MESSAGES,
    MOTOR_ALARM_MESSAGES,
)
from sciglob.core.utils import (
    degrees_to_steps,
    steps_to_degrees,
    validate_angle,
    normalize_azimuth,
    calculate_angular_distance,
    shortest_rotation_path,
    dec2hex,
    hex2dec,
    get_checksum,
    parse_hdc2080_humidity,
    parse_hdc2080_temperature,
    nmea_to_decimal,
)
from sciglob.core.connection import (
    SerialConnection,
    parse_response,
    parse_position_response,
    parse_sensor_value,
)


class TestExceptions:
    """Tests for custom exceptions."""
    
    def test_sciglob_error_is_base(self):
        """Test that SciGlobError is the base exception."""
        assert issubclass(ConnectionError, SciGlobError)
        assert issubclass(DeviceError, SciGlobError)
        assert issubclass(TimeoutError, SciGlobError)
    
    def test_position_error(self):
        """Test PositionError attributes."""
        err = PositionError(100.0, 0.0, 90.0, axis="Zenith")
        assert err.position == 100.0
        assert err.min_pos == 0.0
        assert err.max_pos == 90.0
        assert err.axis == "Zenith"
        assert "100" in str(err)
        assert "0" in str(err)
        assert "90" in str(err)
    
    def test_motor_alarm_error(self):
        """Test MotorAlarmError attributes."""
        err = MotorAlarmError("Motor overheating", alarm_code=26, axis="zenith")
        assert err.alarm_code == 26
        assert err.axis == "zenith"
    
    def test_communication_error_with_code(self):
        """Test CommunicationError with error code."""
        err = CommunicationError("Test error", error_code=5)
        assert err.error_code == 5
    
    def test_recovery_error(self):
        """Test RecoveryError attributes."""
        err = RecoveryError("Recovery failed", recovery_level=10)
        assert err.recovery_level == 10


class TestProtocols:
    """Tests for protocol definitions."""
    
    def test_device_types(self):
        """Test DeviceType enum values."""
        assert DeviceType.SCIGLOB_HSN1.value == "SciGlobHSN1"
        assert DeviceType.SCIGLOB_HSN2.value == "SciGlobHSN2"
        assert DeviceType.LUFTBLICK_TR1.value == "LuftBlickTR1"
    
    def test_error_codes(self):
        """Test ErrorCode enum values."""
        assert ErrorCode.OK == 0
        assert ErrorCode.FILTERWHEEL_MIRROR_ERROR == 3
        assert ErrorCode.LOW_LEVEL_SERIAL_ERROR == 99
    
    def test_motor_alarm_codes(self):
        """Test MotorAlarmCode enum values."""
        assert MotorAlarmCode.OK == 0
        assert MotorAlarmCode.MOTOR_OVERHEATING == 26
        assert MotorAlarmCode.RS485_COMM_ERROR == 84
    
    def test_get_error_message(self):
        """Test error message retrieval."""
        assert get_error_message(0) == "OK"
        assert get_error_message(3) == "Cannot find filterwheel mirror"
        assert "Unknown" in get_error_message(999)
    
    def test_get_motor_alarm_message(self):
        """Test motor alarm message retrieval."""
        assert get_motor_alarm_message(0) == "No alarm"
        assert get_motor_alarm_message(26) == "Motor overheating"
        assert "Unknown" in get_motor_alarm_message(999)
    
    def test_serial_config_defaults(self):
        """Test SerialConfig default values."""
        config = SerialConfig()
        assert config.baudrate == 9600
        assert config.bytesize == 8
        assert config.parity == "N"
        assert config.stopbits == 1
        assert config.timeout == 0
        assert config.write_timeout == 20.0


class TestUtils:
    """Tests for utility functions."""
    
    def test_degrees_to_steps_at_home(self):
        """Test conversion at home position."""
        steps = degrees_to_steps(180.0, degrees_per_step=0.01, home_position=180.0)
        assert steps == 0
    
    def test_degrees_to_steps_positive(self):
        """Test conversion with positive steps."""
        steps = degrees_to_steps(90.0, degrees_per_step=0.01, home_position=180.0)
        assert steps == 9000
    
    def test_degrees_to_steps_negative(self):
        """Test conversion with negative steps."""
        steps = degrees_to_steps(270.0, degrees_per_step=0.01, home_position=180.0)
        assert steps == -9000
    
    def test_steps_to_degrees_at_home(self):
        """Test conversion at home position."""
        degrees = steps_to_degrees(0, degrees_per_step=0.01, home_position=180.0)
        assert degrees == 180.0
    
    def test_steps_to_degrees_positive(self):
        """Test conversion from positive steps."""
        degrees = steps_to_degrees(9000, degrees_per_step=0.01, home_position=180.0)
        assert degrees == 90.0
    
    def test_steps_to_degrees_negative(self):
        """Test conversion from negative steps."""
        degrees = steps_to_degrees(-9000, degrees_per_step=0.01, home_position=180.0)
        assert degrees == 270.0
    
    def test_roundtrip_conversion(self):
        """Test that degrees->steps->degrees gives same value."""
        original = 45.0
        steps = degrees_to_steps(original, 0.01, 180.0)
        result = steps_to_degrees(steps, 0.01, 180.0)
        assert abs(result - original) < 0.01  # Within one step
    
    def test_normalize_azimuth_positive(self):
        """Test azimuth normalization for positive values."""
        assert normalize_azimuth(0.0) == 0.0
        assert normalize_azimuth(180.0) == 180.0
        assert normalize_azimuth(360.0) == 0.0
        assert normalize_azimuth(450.0) == 90.0
    
    def test_normalize_azimuth_negative(self):
        """Test azimuth normalization for negative values."""
        assert normalize_azimuth(-90.0) == 270.0
        assert normalize_azimuth(-180.0) == 180.0
        assert normalize_azimuth(-360.0) == 0.0
    
    def test_validate_angle_valid(self):
        """Test angle validation with valid angle."""
        result = validate_angle(45.0, 0.0, 90.0)
        assert result == 45.0
    
    def test_validate_angle_invalid(self):
        """Test angle validation with invalid angle."""
        with pytest.raises(ValueError):
            validate_angle(100.0, 0.0, 90.0, wrap=False)
    
    def test_validate_angle_wrap(self):
        """Test angle validation with wrapping."""
        result = validate_angle(450.0, 0.0, 360.0, wrap=True)
        assert result == 90.0
    
    def test_shortest_rotation_path_clockwise(self):
        """Test shortest path clockwise."""
        delta = shortest_rotation_path(350.0, 10.0)
        assert abs(delta - 20.0) < 0.01
    
    def test_shortest_rotation_path_counter_clockwise(self):
        """Test shortest path counter-clockwise."""
        delta = shortest_rotation_path(10.0, 350.0)
        assert abs(delta - (-20.0)) < 0.01
    
    def test_calculate_angular_distance_same(self):
        """Test angular distance for same point."""
        dist = calculate_angular_distance(45.0, 180.0, 45.0, 180.0)
        assert abs(dist) < 0.01
    
    def test_calculate_angular_distance_different(self):
        """Test angular distance for different points."""
        dist = calculate_angular_distance(0.0, 0.0, 90.0, 0.0)
        assert abs(dist - 90.0) < 0.01
    
    def test_dec2hex_positive(self):
        """Test decimal to hex conversion for positive values."""
        assert dec2hex(255, 16) == "00ff"
        assert dec2hex(256, 16) == "0100"
    
    def test_dec2hex_negative(self):
        """Test decimal to hex conversion for negative values."""
        result = dec2hex(-1, 16)
        assert result == "ffff"
    
    def test_hex2dec_positive(self):
        """Test hex to decimal conversion for positive values."""
        assert hex2dec("00ff", 16) == 255
        assert hex2dec("0100", 16) == 256
    
    def test_hex2dec_negative(self):
        """Test hex to decimal conversion for negative values."""
        assert hex2dec("ffff", 16) == -1
    
    def test_get_checksum(self):
        """Test checksum calculation."""
        # Simple test
        checksum = get_checksum("abc")
        expected = format((ord('a') + ord('b') + ord('c')) % 256, '02x')
        assert checksum == expected
    
    def test_parse_hdc2080_humidity(self):
        """Test HDC2080 humidity parsing."""
        # 50% humidity example
        humidity = parse_hdc2080_humidity("0080")
        assert 0 <= humidity <= 100
    
    def test_parse_hdc2080_temperature(self):
        """Test HDC2080 temperature parsing."""
        temp = parse_hdc2080_temperature("6666")
        assert -40 <= temp <= 125  # Valid range for sensor
    
    def test_nmea_to_decimal_north(self):
        """Test NMEA conversion for northern latitude."""
        result = nmea_to_decimal("3859.3500", "N")
        assert abs(result - (38 + 59.35/60)) < 0.0001
    
    def test_nmea_to_decimal_south(self):
        """Test NMEA conversion for southern latitude."""
        result = nmea_to_decimal("3859.3500", "S")
        assert result < 0
    
    def test_nmea_to_decimal_east(self):
        """Test NMEA conversion for eastern longitude."""
        result = nmea_to_decimal("07652.8949", "E")
        assert abs(result - (76 + 52.8949/60)) < 0.0001
    
    def test_nmea_to_decimal_west(self):
        """Test NMEA conversion for western longitude."""
        result = nmea_to_decimal("07652.8949", "W")
        assert result < 0
    
    def test_nmea_to_decimal_empty(self):
        """Test NMEA conversion with empty string."""
        result = nmea_to_decimal("", "N")
        assert result == 0.0


class TestConnection:
    """Tests for connection utilities."""
    
    def test_parse_response_success(self):
        """Test parsing successful response."""
        success, data, error = parse_response("TR0", "TR")
        assert success is True
        assert error == 0
    
    def test_parse_response_error(self):
        """Test parsing error response."""
        success, data, error = parse_response("TR3", "TR")
        assert success is False
        assert error == 3
    
    def test_parse_response_with_data(self):
        """Test parsing response with data marker."""
        success, data, error = parse_response("HT!25000", "HT")
        assert success is True
        assert data == "25000"
    
    def test_parse_response_position(self):
        """Test parsing position response."""
        success, data, error = parse_response("TRh-1200,3100", "TR")
        assert success is True
        assert "-1200,3100" in data
    
    def test_parse_response_empty(self):
        """Test parsing empty response."""
        success, data, error = parse_response("", "TR")
        assert success is False
    
    def test_parse_position_response_valid(self):
        """Test parsing valid position response."""
        azi, zen = parse_position_response("TRh-1200,3100")
        assert azi == -1200
        assert zen == 3100
    
    def test_parse_position_response_invalid(self):
        """Test parsing invalid position response."""
        azi, zen = parse_position_response("TR0")
        assert azi is None
        assert zen is None
    
    def test_parse_sensor_value_valid(self):
        """Test parsing valid sensor value."""
        value = parse_sensor_value("HT!25000", "HT", 100.0)
        assert value == 250.0
    
    def test_parse_sensor_value_invalid(self):
        """Test parsing invalid sensor value."""
        value = parse_sensor_value("HT3", "HT", 100.0)
        assert value is None


class TestSerialConnection:
    """Tests for SerialConnection class."""
    
    def test_serial_connection_init(self):
        """Test SerialConnection initialization."""
        conn = SerialConnection(port="/dev/ttyUSB0")
        assert conn.port == "/dev/ttyUSB0"
        assert conn.is_open is False
    
    def test_serial_connection_with_config(self):
        """Test SerialConnection with custom config."""
        config = SerialConfig(baudrate=115200, timeout=2.0)
        conn = SerialConnection(port="/dev/ttyUSB0", config=config)
        assert conn.config.baudrate == 115200
    
    @patch('serial.Serial')
    def test_serial_connection_open(self, mock_serial):
        """Test opening serial connection."""
        mock_serial.return_value.is_open = True
        
        conn = SerialConnection(port="/dev/ttyUSB0")
        conn.open()
        
        assert conn.is_open is True
        mock_serial.assert_called_once()
    
    @patch('serial.Serial')
    def test_serial_connection_context_manager(self, mock_serial):
        """Test SerialConnection as context manager."""
        mock_serial.return_value.is_open = True
        
        with SerialConnection(port="/dev/ttyUSB0") as conn:
            assert conn.is_open is True
    
    def test_serial_connection_no_port(self):
        """Test opening connection without port."""
        conn = SerialConnection()
        with pytest.raises(ConnectionError):
            conn.open()

