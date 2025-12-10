"""Protocol definitions and constants for SciGlob devices."""

from dataclasses import dataclass
from enum import Enum, IntEnum


class DeviceType(str, Enum):
    """Supported device types."""
    SCIGLOB_HSN1 = "SciGlobHSN1"
    SCIGLOB_HSN2 = "SciGlobHSN2"
    LUFTBLICK_TR1 = "LuftBlickTR1"
    DIRECTED_PERCEPTIONS = "Directed Perceptions"
    TETECH1 = "TETech1"
    TETECH2 = "TETech2"
    HDC2080EVM = "HDC2080EVM"
    NOVATEL = "Novatel"
    GLOBALSAT = "GlobalSat"


class ErrorCode(IntEnum):
    """Standard error codes."""
    OK = 0
    MEMORY_READ_ERROR = 1
    WRONG_TRACKER_ECHO = 2
    FILTERWHEEL_MIRROR_ERROR = 3
    MEMORY_WRITE_ERROR = 4
    DRIVER_READ_ERROR = 5
    DRIVER_WRITE_ERROR = 6
    SENSOR_READ_ERROR = 7
    RESET_FAILED = 8
    POWER_RESET_FAILED = 9
    LOW_LEVEL_SERIAL_ERROR = 99


class MotorAlarmCode(IntEnum):
    """Motor alarm codes for LuftBlickTR1."""
    OK = 0
    EXCESSIVE_POSITION_DEVIATION = 10
    MOTOR_OVERHEATING = 26
    LOAD_EXCEEDS_TORQUE = 30
    POSITION_SENSOR_ERROR = 42
    WRAP_SETTING_ERROR = 72
    RS485_COMM_ERROR = 84


# Error code messages
ERROR_MESSAGES: dict[int, str] = {
    0: "OK",
    1: "Cannot read from head sensor microcontroller memory",
    2: "Wrong tracker echo response",
    3: "Cannot find filterwheel mirror",
    4: "Cannot write to head sensor microcontroller memory",
    5: "Cannot read from tracker driver register",
    6: "Cannot write to tracker driver register",
    7: "Cannot read sensor data",
    8: "Cannot reset head sensor software",
    9: "Tracker did not reset power",
    99: "Low level serial communication error",
}

MOTOR_ALARM_MESSAGES: dict[int, str] = {
    0: "No alarm",
    10: "Excessive position deviation",
    26: "Motor overheating",
    30: "Load exceeding maximum configured torque",
    42: "Absolute position sensor error at power on",
    72: "Wrap setting parameter error",
    84: "RS-485 communication error",
}


@dataclass
class SerialConfig:
    """Serial port configuration."""
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    timeout: float = 0  # Non-blocking read
    write_timeout: float = 20.0
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False


# Default configurations for each device type
DEVICE_CONFIGS: dict[str, SerialConfig] = {
    "head_sensor": SerialConfig(baudrate=9600),
    "temperature_controller": SerialConfig(baudrate=9600),
    "humidity_sensor": SerialConfig(baudrate=9600),
    "gps": SerialConfig(baudrate=9600),
}


@dataclass
class CommandProtocol:
    """Protocol definition for a command."""
    command: str
    end_char: str = "\r"
    response_end_char: str = "\n"
    expected_prefix: str = ""
    timeout: float = 1.0


# Head Sensor Commands
HEAD_SENSOR_COMMANDS = {
    "id": CommandProtocol(command="?", expected_prefix=""),
    "temperature": CommandProtocol(command="HTt?", expected_prefix="HT"),
    "humidity": CommandProtocol(command="HTh?", expected_prefix="HT"),
    "pressure": CommandProtocol(command="HTp?", expected_prefix="HT"),
}

# Tracker Commands
TRACKER_COMMANDS = {
    "pan": CommandProtocol(command="TRp{steps}", expected_prefix="TR"),
    "tilt": CommandProtocol(command="TRt{steps}", expected_prefix="TR"),
    "both": CommandProtocol(command="TRb{azimuth},{zenith}", expected_prefix="TR"),
    "where": CommandProtocol(command="TRw", expected_prefix="TR"),
    "magnetic": CommandProtocol(command="TRm", expected_prefix="TR"),
    "reset": CommandProtocol(command="TRr", expected_prefix="TR", timeout=5.0),
    "power": CommandProtocol(command="TRs", expected_prefix="TR", timeout=10.0),
}

# Motor Temperature Commands (LuftBlickTR1)
MOTOR_TEMP_COMMANDS = {
    "azimuth_driver_temp": CommandProtocol(command="MAd?", expected_prefix="MA"),
    "azimuth_motor_temp": CommandProtocol(command="MAm?", expected_prefix="MA"),
    "zenith_driver_temp": CommandProtocol(command="MZd?", expected_prefix="MZ"),
    "zenith_motor_temp": CommandProtocol(command="MZm?", expected_prefix="MZ"),
    "azimuth_alarm": CommandProtocol(command="MAa?", expected_prefix=""),
    "zenith_alarm": CommandProtocol(command="MZa?", expected_prefix=""),
}

# Filter Wheel Commands
FILTER_WHEEL_COMMANDS = {
    "set_position": CommandProtocol(command="F{wheel}{position}", expected_prefix="F{wheel}"),
    "reset": CommandProtocol(command="F{wheel}r", expected_prefix="F{wheel}"),
}

# Shadowband Commands
SHADOWBAND_COMMANDS = {
    "move": CommandProtocol(command="SBm{position}", expected_prefix="SB"),
    "reset": CommandProtocol(command="SBr", expected_prefix="SB"),
}

# Sensor reading conversion factors
SENSOR_CONVERSIONS = {
    "temperature": {"factor": 100.0, "unit": "°C", "error_value": 999.0},
    "humidity": {"factor": 1024.0, "unit": "%", "error_value": -9.0},
    "pressure": {"factor": 100.0, "unit": "mbar", "error_value": -9.0},
    "motor_temp": {"factor": 10.0, "unit": "°C", "error_value": 999.0},
}

# Valid filter names
VALID_FILTERS = [
    "OPAQUE",
    "OPEN", "DIFF",
    "U340", "U340+DIFF",
    "BP300", "BP300+DIFF",
    "LPNIR", "LPNIR+DIFF",
] + [f"ND{i}" for i in range(1, 6)] + [
    f"ND{i/10:.1f}" for i in range(1, 51)
] + [f"DIFF{i}" for i in range(1, 6)] + [
    f"FILTER{i}" for i in range(1, 10)
] + [f"POL{i}" for i in range(360)]


# TETech Temperature Controller Protocol
TETECH_PROTOCOL = {
    "TETech1": {
        "connection_test": "*0060",
        "end_char": "^",
        "nbits": 16,
        "write_commands": {
            "ST": {"cmd": "1c", "factor": 10},   # Set temperature
            "BW": {"cmd": "1d", "factor": 10},   # Proportional bandwidth
            "IG": {"cmd": "1e", "factor": 100},  # Integral gain
            "EO": {"cmd": "30", "factor": 1},    # Enable output
        },
        "read_commands": {
            "ST": {"cmd": "5065", "factor": 10},
            "BW": {"cmd": "5166", "factor": 10},
            "IG": {"cmd": "5267", "factor": 100},
            "T1": {"cmd": "0161", "factor": 10},   # Control sensor temp
            "T2": {"cmd": "0464", "factor": 10},   # Secondary sensor temp
        },
        "error_response": "XXXX60",
    },
    "TETech2": {
        "connection_test": "*00430000000047",
        "end_char": "^",
        "nbits": 32,
        "write_commands": {
            "ST": {"cmd": "1c", "factor": 100},
            "BW": {"cmd": "1d", "factor": 100},
            "IG": {"cmd": "1e", "factor": 100},
            "EO": {"cmd": "2d", "factor": 1},
        },
        "read_commands": {
            "ST": {"cmd": "00500000000045", "factor": 100},
            "BW": {"cmd": "00510000000046", "factor": 100},
            "IG": {"cmd": "00520000000047", "factor": 100},
            "T1": {"cmd": "00010000000041", "factor": 100},
            "T2": {"cmd": "00060000000046", "factor": 100},
        },
        "error_response": "XXXXXXXXc0",
    },
}

# HDC2080EVM Humidity Sensor Protocol
HDC2080_PROTOCOL = {
    "id_command": "?",
    "initialize_command": "4",
    "temperature_command": "1",
    "humidity_command": "2",
    "end_char": "\r",
    "response_end_char": "\r\n",
    "expected_id": "HDC2080EVM",
}

# GPS Protocol
GPS_PROTOCOL = {
    "Novatel": {
        "end_char": "\r",
        "response_end_char": "\r\n[USB1]",
        "commands": {
            "clear_logs": "unlogall",
            "read_once": "log inspva once",
            "start_logging": "log inspva ontime {interval}",
        },
    },
    "GlobalSat": {
        "end_char": "\r\n",
        "response_end_char": "\r\n",
        "commands": {
            "disable_rmc": "$PSRF103,04,00,00,01*20",
            "disable_gsa": "$PSRF103,02,00,00,01*26",
            "disable_gsv": "$PSRF103,03,00,00,01*27",
            "disable_gga": "$PSRF103,00,00,00,01*24",
            "query_gga": "$PSRF103,00,01,00,01*25",
        },
    },
}

# Timing parameters
TIMING_CONFIG = {
    "inter_command_delay": 0.1,
    "standard_timeout": 1.0,
    "position_query_timeout": 2.0,
    "movement_timeout": 3.0,
    "soft_reset_timeout": 5.0,
    "power_reset_timeout": 10.0,
    "sensor_reading_timeout": 2.0,
    "buffer_read_timeout": 0.5,
    "max_unexpected_answers": 3,
    "max_recovery_level": 18,
    "luftblick_soft_reset_wait": 15.0,
    "luftblick_power_reset_wait": 30.0,
}


def get_error_message(code: int) -> str:
    """Get human-readable error message for code."""
    return ERROR_MESSAGES.get(code, f"Unknown error code: {code}")


def get_motor_alarm_message(code: int) -> str:
    """Get human-readable motor alarm message."""
    return MOTOR_ALARM_MESSAGES.get(code, f"Unknown alarm code: {code}")

