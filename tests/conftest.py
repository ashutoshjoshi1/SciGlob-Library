"""Pytest configuration and fixtures for SciGlob tests."""

from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.fixture
def mock_serial():
    """Create a mock serial connection."""
    mock = MagicMock()
    mock.is_open = True
    mock.in_waiting = 0
    mock.read.return_value = b"OK\r\n"
    mock.readline.return_value = b"OK\r\n"
    mock.write.return_value = 4
    mock.reset_input_buffer = Mock()
    mock.reset_output_buffer = Mock()
    return mock


@pytest.fixture
def mock_serial_connection(mock_serial):
    """Patch serial.Serial to return mock."""
    with patch("serial.Serial", return_value=mock_serial):
        yield mock_serial


@pytest.fixture
def mock_head_sensor():
    """Create a mock HeadSensor for testing dependent modules."""
    mock = MagicMock()
    mock.is_connected = True
    mock._connected = True
    mock.port = "/dev/ttyUSB0"
    mock.baudrate = 9600
    mock.timeout = 1.0
    mock.device_id = "SciGlobHSN2"
    mock.sensor_type = "SciGlobHSN2"
    mock.tracker_type = "LuftBlickTR1"
    mock.degrees_per_step = 0.01
    mock.motion_limits = [0, 90, 0, 360]
    mock.home_position = [0.0, 180.0]
    mock.fw1_filters = ["OPEN", "U340", "BP300", "LPNIR", "ND1", "ND2", "ND3", "ND4", "OPAQUE"]
    mock.fw2_filters = [
        "OPEN",
        "DIFF",
        "U340+DIFF",
        "BP300+DIFF",
        "LPNIR+DIFF",
        "ND1",
        "ND2",
        "ND3",
        "OPAQUE",
    ]

    # Mock send_command to return success responses
    def mock_send_command(cmd, timeout=None):
        if cmd == "?":
            return "SciGlobHSN2"
        elif cmd.startswith("TR"):
            if cmd == "TRw":
                return "TRh0,0"
            return "TR0"
        elif cmd.startswith("F1"):
            return "F10"
        elif cmd.startswith("F2"):
            return "F20"
        elif cmd.startswith("SB"):
            return "SB0"
        elif cmd.startswith("HT"):
            return "HT!25000"
        elif cmd.startswith("MA") or cmd.startswith("MZ"):
            if "a?" in cmd:
                return "Alarm Code = 0"
            return "MA!215"
        return "OK"

    mock.send_command = Mock(side_effect=mock_send_command)
    return mock


@pytest.fixture
def tracker(mock_head_sensor):
    """Create a Tracker instance for testing."""
    from sciglob.devices.tracker import Tracker

    return Tracker(mock_head_sensor)


@pytest.fixture
def filter_wheel_1(mock_head_sensor):
    """Create a FilterWheel instance for testing (FW1)."""
    from sciglob.devices.filter_wheel import FilterWheel

    return FilterWheel(mock_head_sensor, wheel_id=1)


@pytest.fixture
def filter_wheel_2(mock_head_sensor):
    """Create a FilterWheel instance for testing (FW2)."""
    from sciglob.devices.filter_wheel import FilterWheel

    return FilterWheel(mock_head_sensor, wheel_id=2)


@pytest.fixture
def shadowband(mock_head_sensor):
    """Create a Shadowband instance for testing."""
    from sciglob.devices.shadowband import Shadowband

    return Shadowband(mock_head_sensor)
