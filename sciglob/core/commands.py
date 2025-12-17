"""
Comprehensive firmware command definitions for SciGlob devices.

This module contains all commands from the Firmware Commands & Versions V7 specification.
Commands are organized by hardware component for easy reference.

Command Format Notes:
    - * stands for a number/value
    - Standard response without error: HW_PART + "0" + "\\n" (e.g., "F10\\n")
    - Standard response with ? query: HW_PART + "!" + VALUE + "\\n" (e.g., "F1!142\\n")
    - Error response: HW_PART + ERROR_INDEX + "\\n" (e.g., "F11\\n")
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CommandCategory(str, Enum):
    """Categories of firmware commands."""

    HEAD_SENSOR = "HT"
    FILTER_WHEEL_1 = "F1"
    FILTER_WHEEL_2 = "F2"
    FILTER_WHEELS = "FW"
    TRACKER = "TR"
    AZIMUTH_MOTOR = "MA"
    ZENITH_MOTOR = "MZ"
    BOTH_MOTORS = "MB"
    SPECTROMETER_1 = "S1"
    SPECTROMETER_2 = "S2"


@dataclass
class FirmwareCommand:
    """Definition of a firmware command."""

    command: str
    description: str
    category: CommandCategory
    has_parameter: bool = False
    is_query: bool = False
    response_prefix: str = ""
    timeout: float = 1.0
    conversion_factor: Optional[float] = None
    notes: str = ""


# =============================================================================
# HEAD SENSOR COMMANDS (HT)
# =============================================================================

HEAD_SENSOR_COMMANDS = {
    # Version and ID
    "get_version": FirmwareCommand(
        command="HTv?",
        description="Get the software version (e.g., V4_C96)",
        category=CommandCategory.HEAD_SENSOR,
        is_query=True,
        response_prefix="V",
    ),
    "get_id": FirmwareCommand(
        command="?",
        description="Get the sensor head number (returns Pan*HST)",
        category=CommandCategory.HEAD_SENSOR,
        is_query=True,
    ),
    "get_head_id": FirmwareCommand(
        command="HTI?",
        description="Read head sensor ID (number only)",
        category=CommandCategory.HEAD_SENSOR,
        is_query=True,
    ),
    "set_head_id": FirmwareCommand(
        command="HTI{value}",
        description="Change head sensor ID to Pan*HST",
        category=CommandCategory.HEAD_SENSOR,
        has_parameter=True,
    ),
    # Environmental Sensors
    "get_temperature": FirmwareCommand(
        command="HTt?",
        description="Read head sensor temperature (divide by 100 for °C)",
        category=CommandCategory.HEAD_SENSOR,
        is_query=True,
        response_prefix="HT",
        conversion_factor=100.0,
        timeout=5.0,
        notes="Takes around 5 seconds to receive response",
    ),
    "get_humidity": FirmwareCommand(
        command="HTh?",
        description="Read head sensor humidity (divide by 1024 for %RH)",
        category=CommandCategory.HEAD_SENSOR,
        is_query=True,
        response_prefix="HT",
        conversion_factor=1024.0,
        timeout=5.0,
        notes="Takes around 5 seconds to receive response",
    ),
    "get_pressure": FirmwareCommand(
        command="HTp?",
        description="Read head sensor pressure (divide by 100 for hPa)",
        category=CommandCategory.HEAD_SENSOR,
        is_query=True,
        response_prefix="HT",
        conversion_factor=100.0,
        timeout=5.0,
        notes="Takes around 5 seconds to receive response",
    ),
    # Baud Rate Commands
    "get_tracker_baudrate": FirmwareCommand(
        command="HTbt?",
        description="Read tracker baud rate (between head sensor and tracker)",
        category=CommandCategory.HEAD_SENSOR,
        is_query=True,
    ),
    "get_sensor_baudrate_b": FirmwareCommand(
        command="HTbsB?",
        description="Read sensor head baud rate PORT B (head sensor to tracker)",
        category=CommandCategory.HEAD_SENSOR,
        is_query=True,
    ),
    "get_sensor_baudrate_c": FirmwareCommand(
        command="HTbs?",
        description="Read sensor head baud rate PORT C (computer to head sensor)",
        category=CommandCategory.HEAD_SENSOR,
        is_query=True,
    ),
    "set_sensor_baudrate": FirmwareCommand(
        command="HTbs{value}",
        description="Change baud rate for PORT C (4800/9600/14400/19200/38400/57600/115200/128000)",
        category=CommandCategory.HEAD_SENSOR,
        has_parameter=True,
    ),
    "set_tracker_baudrate_hw": FirmwareCommand(
        command="HTbth{value}",
        description="Change tracker baud rate by hardware (0=9600,1=19200,2=38400,3=57600,4=115200)",
        category=CommandCategory.HEAD_SENSOR,
        has_parameter=True,
    ),
    "set_tracker_baudrate_sw": FirmwareCommand(
        command="HTbts{value}",
        description="Change tracker baud rate by software (0=9600,1=19200,2=38400,3=57600,4=115200)",
        category=CommandCategory.HEAD_SENSOR,
        has_parameter=True,
    ),
    "find_tracker_baudrate": FirmwareCommand(
        command="HTbm",
        description="Find tracker baud rate and set sensor head to match",
        category=CommandCategory.HEAD_SENSOR,
    ),
    # Reset
    "reset_head_sensor": FirmwareCommand(
        command="HTr",
        description="Reset head sensor (restarts the program)",
        category=CommandCategory.HEAD_SENSOR,
        timeout=5.0,
    ),
}


# =============================================================================
# FILTER WHEEL 1 COMMANDS (F1)
# =============================================================================

FILTER_WHEEL_1_COMMANDS = {
    "set_position": FirmwareCommand(
        command="F1{position}",
        description="Move FW1 to position (1-9)",
        category=CommandCategory.FILTER_WHEEL_1,
        has_parameter=True,
        response_prefix="F1",
    ),
    "move_backward": FirmwareCommand(
        command="F1b",
        description="Move FW1 backward by FWn steps",
        category=CommandCategory.FILTER_WHEEL_1,
        response_prefix="F1",
    ),
    "move_backward_steps": FirmwareCommand(
        command="F1B{steps}",
        description="Move FW1 backwards for * integer steps",
        category=CommandCategory.FILTER_WHEEL_1,
        has_parameter=True,
        response_prefix="F1",
    ),
    "move_forward": FirmwareCommand(
        command="F1f",
        description="Move FW1 forward by FWn steps",
        category=CommandCategory.FILTER_WHEEL_1,
        response_prefix="F1",
    ),
    "move_forward_steps": FirmwareCommand(
        command="F1F{steps}",
        description="Move FW1 forwards for * integer steps",
        category=CommandCategory.FILTER_WHEEL_1,
        has_parameter=True,
        response_prefix="F1",
    ),
    "move_to_mirror": FirmwareCommand(
        command="F1M",
        description="Move FW1 to the mirror position",
        category=CommandCategory.FILTER_WHEEL_1,
        response_prefix="F1",
    ),
    "test_movement": FirmwareCommand(
        command="F1m",
        description="Move FW1 in both directions (movement test)",
        category=CommandCategory.FILTER_WHEEL_1,
        response_prefix="F1",
    ),
    "save_offset": FirmwareCommand(
        command="F1o",
        description="Save current position as offset position for FW1",
        category=CommandCategory.FILTER_WHEEL_1,
        response_prefix="F1",
    ),
    "get_offset": FirmwareCommand(
        command="F1o?",
        description="Read offset value between mirror and home position",
        category=CommandCategory.FILTER_WHEEL_1,
        is_query=True,
        response_prefix="F1",
    ),
    "set_offset": FirmwareCommand(
        command="F1o{value}",
        description="Change offset value (use F1o0 to reset)",
        category=CommandCategory.FILTER_WHEEL_1,
        has_parameter=True,
        response_prefix="F1",
    ),
    "reset": FirmwareCommand(
        command="F1r",
        description="Reset FW1 (ends at OPEN position)",
        category=CommandCategory.FILTER_WHEEL_1,
        response_prefix="F1",
        timeout=10.0,
    ),
}


# =============================================================================
# FILTER WHEEL 2 COMMANDS (F2)
# =============================================================================

FILTER_WHEEL_2_COMMANDS = {
    "set_position": FirmwareCommand(
        command="F2{position}",
        description="Move FW2 to position (1-9)",
        category=CommandCategory.FILTER_WHEEL_2,
        has_parameter=True,
        response_prefix="F2",
    ),
    "move_backward": FirmwareCommand(
        command="F2b",
        description="Move FW2 backward by FWn steps",
        category=CommandCategory.FILTER_WHEEL_2,
        response_prefix="F2",
    ),
    "move_backward_steps": FirmwareCommand(
        command="F2B{steps}",
        description="Move FW2 backwards for * integer steps",
        category=CommandCategory.FILTER_WHEEL_2,
        has_parameter=True,
        response_prefix="F2",
    ),
    "move_forward": FirmwareCommand(
        command="F2f",
        description="Move FW2 forward by FWn steps",
        category=CommandCategory.FILTER_WHEEL_2,
        response_prefix="F2",
    ),
    "move_forward_steps": FirmwareCommand(
        command="F2F{steps}",
        description="Move FW2 forwards for * integer steps",
        category=CommandCategory.FILTER_WHEEL_2,
        has_parameter=True,
        response_prefix="F2",
    ),
    "move_to_mirror": FirmwareCommand(
        command="F2M",
        description="Move FW2 to the mirror position",
        category=CommandCategory.FILTER_WHEEL_2,
        response_prefix="F2",
    ),
    "test_movement": FirmwareCommand(
        command="F2m",
        description="Move FW2 in both directions (movement test)",
        category=CommandCategory.FILTER_WHEEL_2,
        response_prefix="F2",
    ),
    "save_offset": FirmwareCommand(
        command="F2o",
        description="Save current position as offset position for FW2",
        category=CommandCategory.FILTER_WHEEL_2,
        response_prefix="F2",
    ),
    "get_offset": FirmwareCommand(
        command="F2o?",
        description="Read offset value between mirror and home position",
        category=CommandCategory.FILTER_WHEEL_2,
        is_query=True,
        response_prefix="F2",
    ),
    "set_offset": FirmwareCommand(
        command="F2o{value}",
        description="Change offset value (use F2o0 to reset)",
        category=CommandCategory.FILTER_WHEEL_2,
        has_parameter=True,
        response_prefix="F2",
    ),
    "reset": FirmwareCommand(
        command="F2r",
        description="Reset FW2 (ends at OPEN position)",
        category=CommandCategory.FILTER_WHEEL_2,
        response_prefix="F2",
        timeout=10.0,
    ),
}


# =============================================================================
# FILTER WHEELS COMMON COMMANDS (FW)
# =============================================================================

FILTER_WHEELS_COMMON_COMMANDS = {
    "get_steps_per_position": FirmwareCommand(
        command="FWn?",
        description="Get number of steps between 2 FW positions",
        category=CommandCategory.FILTER_WHEELS,
        is_query=True,
        response_prefix="FW",
    ),
    "set_steps_per_position": FirmwareCommand(
        command="FWn{value}",
        description="Change steps per position (1S=142, 2S=150, new driver=70)",
        category=CommandCategory.FILTER_WHEELS,
        has_parameter=True,
        response_prefix="FW",
    ),
    "get_speed": FirmwareCommand(
        command="FWs?",
        description="Get filter wheels speed",
        category=CommandCategory.FILTER_WHEELS,
        is_query=True,
        response_prefix="FW",
    ),
    "set_speed": FirmwareCommand(
        command="FWs{value}",
        description="Change FW speed (larger=slower, new board=200, old=100, new driver=170)",
        category=CommandCategory.FILTER_WHEELS,
        has_parameter=True,
        response_prefix="FW",
    ),
}


# =============================================================================
# TRACKER COMMANDS (TR)
# =============================================================================

TRACKER_COMMANDS = {
    "power_off": FirmwareCommand(
        command="TR0",
        description="Turn off the tracker",
        category=CommandCategory.TRACKER,
        response_prefix="TR",
    ),
    "power_on": FirmwareCommand(
        command="TR1",
        description="Turn on the tracker",
        category=CommandCategory.TRACKER,
        response_prefix="TR",
    ),
    "move_to": FirmwareCommand(
        command="TRb{azimuth},{zenith}",
        description="Move tracker to position (pan,tilt)",
        category=CommandCategory.TRACKER,
        has_parameter=True,
        response_prefix="TR",
        timeout=30.0,
    ),
    "move_pan": FirmwareCommand(
        command="TRp{steps}",
        description="Move pan (azimuth) to position in steps",
        category=CommandCategory.TRACKER,
        has_parameter=True,
        response_prefix="TR",
        timeout=30.0,
    ),
    "move_tilt": FirmwareCommand(
        command="TRt{steps}",
        description="Move tilt (zenith) to position in steps",
        category=CommandCategory.TRACKER,
        has_parameter=True,
        response_prefix="TR",
        timeout=30.0,
    ),
    "get_position": FirmwareCommand(
        command="TRw",
        description="Read tracker current position (AZ, ZE)",
        category=CommandCategory.TRACKER,
        is_query=True,
        response_prefix="TR",
    ),
    "get_magnetic_encoder": FirmwareCommand(
        command="TRm",
        description="Read the magnetic encoder position",
        category=CommandCategory.TRACKER,
        is_query=True,
        response_prefix="TR",
    ),
    "reset": FirmwareCommand(
        command="TRr",
        description="Reset tracker to home position",
        category=CommandCategory.TRACKER,
        response_prefix="TR",
        timeout=60.0,
    ),
    "power_cycle": FirmwareCommand(
        command="TRs",
        description="Tracker power cycle",
        category=CommandCategory.TRACKER,
        response_prefix="TR",
        timeout=30.0,
    ),
    "get_power_cycle_delay": FirmwareCommand(
        command="TRd?",
        description="Read delay for TRs (time tracker is off in seconds)",
        category=CommandCategory.TRACKER,
        is_query=True,
        response_prefix="TR",
    ),
    "set_power_cycle_delay": FirmwareCommand(
        command="TRd{value}",
        description="Set delay for TRs (time tracker is off in seconds)",
        category=CommandCategory.TRACKER,
        has_parameter=True,
        response_prefix="TR",
    ),
    "get_power_cycle_relay": FirmwareCommand(
        command="TRS?",
        description="Get relay triggered by TRs command",
        category=CommandCategory.TRACKER,
        is_query=True,
        response_prefix="TR",
    ),
    "set_power_cycle_relay": FirmwareCommand(
        command="TRS{value}",
        description="Set relay for TRs command (default=2)",
        category=CommandCategory.TRACKER,
        has_parameter=True,
        response_prefix="TR",
    ),
    "configure_oriental": FirmwareCommand(
        command="TRo",
        description="Set all tracker parameters for Oriental Motor (takes ~3 sec)",
        category=CommandCategory.TRACKER,
        response_prefix="TR",
        timeout=5.0,
    ),
}


# =============================================================================
# AZIMUTH MOTOR COMMANDS (MA)
# =============================================================================

AZIMUTH_MOTOR_COMMANDS = {
    "set_direction_ccw": FirmwareCommand(
        command="MA1",
        description="Change direction of Azimuth motor to CCW",
        category=CommandCategory.AZIMUTH_MOTOR,
        response_prefix="MA",
    ),
    "set_direction_cw": FirmwareCommand(
        command="MA2",
        description="Change direction of Azimuth motor to CW",
        category=CommandCategory.AZIMUTH_MOTOR,
        response_prefix="MA",
    ),
    "reset_alarm": FirmwareCommand(
        command="MAa",
        description="Reset the Alarm for Azimuth (if driver LEDs are flashing)",
        category=CommandCategory.AZIMUTH_MOTOR,
        response_prefix="MA",
    ),
    "get_alarm_code": FirmwareCommand(
        command="MAa?",
        description="Read Alarm Code for Azimuth",
        category=CommandCategory.AZIMUTH_MOTOR,
        is_query=True,
    ),
    "set_gear_a": FirmwareCommand(
        command="MAA{value}",
        description="Change gear A value for Az (changes motor resolution)",
        category=CommandCategory.AZIMUTH_MOTOR,
        has_parameter=True,
        response_prefix="MA",
    ),
    "set_home_acceleration": FirmwareCommand(
        command="MAa{value}",
        description="Change acceleration of home position command for Az",
        category=CommandCategory.AZIMUTH_MOTOR,
        has_parameter=True,
        response_prefix="MA",
    ),
    "set_gear_b": FirmwareCommand(
        command="MAB{value}",
        description="Change gear B value for Az (changes motor resolution)",
        category=CommandCategory.AZIMUTH_MOTOR,
        has_parameter=True,
        response_prefix="MA",
    ),
    "configure": FirmwareCommand(
        command="MAc",
        description="Configure Az motor driver after changing parameters",
        category=CommandCategory.AZIMUTH_MOTOR,
        response_prefix="MA",
    ),
    "set_defaults": FirmwareCommand(
        command="MAd",
        description="Set all Az motor parameters to default values",
        category=CommandCategory.AZIMUTH_MOTOR,
        response_prefix="MA",
    ),
    "get_driver_temp": FirmwareCommand(
        command="MAd?",
        description="Read Az driver temperature (divide by 10 for °C)",
        category=CommandCategory.AZIMUTH_MOTOR,
        is_query=True,
        response_prefix="MA",
        conversion_factor=10.0,
    ),
    "get_comm_error": FirmwareCommand(
        command="MAe?",
        description="Read Communication Error Code for Az",
        category=CommandCategory.AZIMUTH_MOTOR,
        is_query=True,
    ),
    "get_parameters": FirmwareCommand(
        command="MAf?",
        description="Check all Azimuth motor parameters",
        category=CommandCategory.AZIMUTH_MOTOR,
        is_query=True,
        timeout=5.0,
    ),
    "set_home_position": FirmwareCommand(
        command="MAh",
        description="Change home position of Az motor to current position",
        category=CommandCategory.AZIMUTH_MOTOR,
        response_prefix="MA",
    ),
    "set_home_starting_speed": FirmwareCommand(
        command="MAi{value}",
        description="Change starting speed of home position command",
        category=CommandCategory.AZIMUTH_MOTOR,
        has_parameter=True,
        response_prefix="MA",
    ),
    "save_to_memory": FirmwareCommand(
        command="MAm",
        description="Save Az driver changes to non-volatile memory",
        category=CommandCategory.AZIMUTH_MOTOR,
        response_prefix="MA",
    ),
    "get_motor_temp": FirmwareCommand(
        command="MAm?",
        description="Read Az motor temperature (divide by 10 for °C)",
        category=CommandCategory.AZIMUTH_MOTOR,
        is_query=True,
        response_prefix="MA",
        conversion_factor=10.0,
    ),
    "get_position": FirmwareCommand(
        command="MAp?",
        description="Read tracker current position AZ",
        category=CommandCategory.AZIMUTH_MOTOR,
        is_query=True,
        response_prefix="MA",
    ),
    "set_wrap_offset": FirmwareCommand(
        command="MAp{value}",
        description="Change wrap range offset ratio for Az",
        category=CommandCategory.AZIMUTH_MOTOR,
        has_parameter=True,
        response_prefix="MA",
    ),
    "read_register": FirmwareCommand(
        command="MAR?",
        description="Read the AZ Register",
        category=CommandCategory.AZIMUTH_MOTOR,
        is_query=True,
    ),
    "write_register": FirmwareCommand(
        command="MAR{value}",
        description="Write to the AZ Register",
        category=CommandCategory.AZIMUTH_MOTOR,
        has_parameter=True,
        response_prefix="MA",
    ),
    "set_home_speed": FirmwareCommand(
        command="MAs{value}",
        description="Change speed of home position command for Az",
        category=CommandCategory.AZIMUTH_MOTOR,
        has_parameter=True,
        response_prefix="MA",
    ),
    "set_wrap_range": FirmwareCommand(
        command="MAw{value}",
        description="Change wrap setting range for Az",
        category=CommandCategory.AZIMUTH_MOTOR,
        has_parameter=True,
        response_prefix="MA",
    ),
}


# =============================================================================
# ZENITH MOTOR COMMANDS (MZ)
# =============================================================================

ZENITH_MOTOR_COMMANDS = {
    "set_direction_ccw": FirmwareCommand(
        command="MZ1",
        description="Change direction of Zenith motor to CCW",
        category=CommandCategory.ZENITH_MOTOR,
        response_prefix="MZ",
    ),
    "set_direction_cw": FirmwareCommand(
        command="MZ2",
        description="Change direction of Zenith motor to CW",
        category=CommandCategory.ZENITH_MOTOR,
        response_prefix="MZ",
    ),
    "reset_alarm": FirmwareCommand(
        command="MZa",
        description="Reset the Alarm for Zenith (if driver LEDs are flashing)",
        category=CommandCategory.ZENITH_MOTOR,
        response_prefix="MZ",
    ),
    "get_alarm_code": FirmwareCommand(
        command="MZa?",
        description="Read Alarm Code for Zenith",
        category=CommandCategory.ZENITH_MOTOR,
        is_query=True,
    ),
    "set_gear_a": FirmwareCommand(
        command="MZA{value}",
        description="Change gear A value for Ze (changes motor resolution)",
        category=CommandCategory.ZENITH_MOTOR,
        has_parameter=True,
        response_prefix="MZ",
    ),
    "set_home_acceleration": FirmwareCommand(
        command="MZa{value}",
        description="Change acceleration of home position command for Ze",
        category=CommandCategory.ZENITH_MOTOR,
        has_parameter=True,
        response_prefix="MZ",
    ),
    "set_gear_b": FirmwareCommand(
        command="MZB{value}",
        description="Change gear B value for Ze (changes motor resolution)",
        category=CommandCategory.ZENITH_MOTOR,
        has_parameter=True,
        response_prefix="MZ",
    ),
    "configure": FirmwareCommand(
        command="MZc",
        description="Configure Ze motor driver after changing parameters",
        category=CommandCategory.ZENITH_MOTOR,
        response_prefix="MZ",
    ),
    "set_defaults": FirmwareCommand(
        command="MZd",
        description="Set all Ze motor parameters to default values",
        category=CommandCategory.ZENITH_MOTOR,
        response_prefix="MZ",
    ),
    "get_driver_temp": FirmwareCommand(
        command="MZd?",
        description="Read Ze driver temperature (divide by 10 for °C)",
        category=CommandCategory.ZENITH_MOTOR,
        is_query=True,
        response_prefix="MZ",
        conversion_factor=10.0,
    ),
    "get_comm_error": FirmwareCommand(
        command="MZe?",
        description="Read Communication Error Code for Ze",
        category=CommandCategory.ZENITH_MOTOR,
        is_query=True,
    ),
    "get_parameters": FirmwareCommand(
        command="MZf?",
        description="Check all Zenith motor parameters",
        category=CommandCategory.ZENITH_MOTOR,
        is_query=True,
        timeout=5.0,
    ),
    "set_home_position": FirmwareCommand(
        command="MZh",
        description="Change home position of Ze motor to current position",
        category=CommandCategory.ZENITH_MOTOR,
        response_prefix="MZ",
        notes="After sending, TRw returns TRh0,0. Restart power to verify.",
    ),
    "set_home_starting_speed": FirmwareCommand(
        command="MZi{value}",
        description="Change starting speed of home position command",
        category=CommandCategory.ZENITH_MOTOR,
        has_parameter=True,
        response_prefix="MZ",
    ),
    "save_to_memory": FirmwareCommand(
        command="MZm",
        description="Save Ze driver changes to non-volatile memory",
        category=CommandCategory.ZENITH_MOTOR,
        response_prefix="MZ",
    ),
    "get_motor_temp": FirmwareCommand(
        command="MZm?",
        description="Read Ze motor temperature (divide by 10 for °C)",
        category=CommandCategory.ZENITH_MOTOR,
        is_query=True,
        response_prefix="MZ",
        conversion_factor=10.0,
    ),
    "get_position": FirmwareCommand(
        command="MZp?",
        description="Read tracker current position ZE",
        category=CommandCategory.ZENITH_MOTOR,
        is_query=True,
        response_prefix="MZ",
    ),
    "set_wrap_offset": FirmwareCommand(
        command="MZp{value}",
        description="Change wrap range offset ratio for Ze",
        category=CommandCategory.ZENITH_MOTOR,
        has_parameter=True,
        response_prefix="MZ",
    ),
    "read_register": FirmwareCommand(
        command="MZR?",
        description="Read the ZE Register",
        category=CommandCategory.ZENITH_MOTOR,
        is_query=True,
    ),
    "write_register": FirmwareCommand(
        command="MZR{value}",
        description="Write to the ZE Register",
        category=CommandCategory.ZENITH_MOTOR,
        has_parameter=True,
        response_prefix="MZ",
    ),
    "set_home_speed": FirmwareCommand(
        command="MZs{value}",
        description="Change speed of home position command for Ze",
        category=CommandCategory.ZENITH_MOTOR,
        has_parameter=True,
        response_prefix="MZ",
    ),
    "set_wrap_range": FirmwareCommand(
        command="MZw{value}",
        description="Change wrap setting range for Ze",
        category=CommandCategory.ZENITH_MOTOR,
        has_parameter=True,
        response_prefix="MZ",
    ),
}


# =============================================================================
# BOTH MOTORS COMMANDS (MB)
# =============================================================================

BOTH_MOTORS_COMMANDS = {
    "get_motor_current": FirmwareCommand(
        command="MBc?",
        description="Read motor current (expected: 00 3 e8)",
        category=CommandCategory.BOTH_MOTORS,
        is_query=True,
        response_prefix="MB",
    ),
    "set_motor_current": FirmwareCommand(
        command="MBc{value}",
        description="Change motor current (Oriental only, e.g., MBc8000 = 80%)",
        category=CommandCategory.BOTH_MOTORS,
        has_parameter=True,
        response_prefix="MB",
    ),
    "set_home_position": FirmwareCommand(
        command="MBh",
        description="Change home position for both Az & Ze motors to current position",
        category=CommandCategory.BOTH_MOTORS,
        response_prefix="MB",
    ),
    "get_register_number": FirmwareCommand(
        command="MBR?",
        description="Read register number (hex and decimal)",
        category=CommandCategory.BOTH_MOTORS,
        is_query=True,
    ),
    "set_register_number": FirmwareCommand(
        command="MBR{value}",
        description="Change register number",
        category=CommandCategory.BOTH_MOTORS,
        has_parameter=True,
        response_prefix="MB",
    ),
    "get_motor_speed": FirmwareCommand(
        command="MBs?",
        description="Read motor speed (expected: 0 0 27 10)",
        category=CommandCategory.BOTH_MOTORS,
        is_query=True,
        response_prefix="MB",
    ),
    "set_motor_speed": FirmwareCommand(
        command="MBs{value}",
        description="Change motor speed (Oriental only)",
        category=CommandCategory.BOTH_MOTORS,
        has_parameter=True,
        response_prefix="MB",
    ),
    "get_acceleration": FirmwareCommand(
        command="MBa?",
        description="Read starting/changing speed rate (1=0.001 kHz/s)",
        category=CommandCategory.BOTH_MOTORS,
        is_query=True,
        response_prefix="MB",
    ),
    "set_acceleration": FirmwareCommand(
        command="MBa{value}",
        description="Change starting/changing speed rate (1 to 1,000,000,000)",
        category=CommandCategory.BOTH_MOTORS,
        has_parameter=True,
        response_prefix="MB",
    ),
    "get_deceleration": FirmwareCommand(
        command="MBd?",
        description="Read stopping deceleration (1=0.001 kHz/s)",
        category=CommandCategory.BOTH_MOTORS,
        is_query=True,
        response_prefix="MB",
    ),
    "set_deceleration": FirmwareCommand(
        command="MBd{value}",
        description="Change stopping deceleration (1 to 1,000,000,000)",
        category=CommandCategory.BOTH_MOTORS,
        has_parameter=True,
        response_prefix="MB",
    ),
    "get_motor_type": FirmwareCommand(
        command="MBt?",
        description="Read motor type (OrientalMotor or FLIR)",
        category=CommandCategory.BOTH_MOTORS,
        is_query=True,
    ),
    "set_motor_type": FirmwareCommand(
        command="MBt{value}",
        description="Select motor type (0=Directed Perceptions, 1=Oriental Motor)",
        category=CommandCategory.BOTH_MOTORS,
        has_parameter=True,
        response_prefix="MB",
    ),
}


# =============================================================================
# SPECTROMETER COMMANDS (S1, S2)
# =============================================================================

SPECTROMETER_1_COMMANDS = {
    "power_cycle": FirmwareCommand(
        command="S1s",
        description="Spectrometer 1 power cycle",
        category=CommandCategory.SPECTROMETER_1,
        response_prefix="S1",
        timeout=10.0,
    ),
    "get_relay": FirmwareCommand(
        command="S1S?",
        description="Get number of relay triggered by S1s command",
        category=CommandCategory.SPECTROMETER_1,
        is_query=True,
        response_prefix="S1",
    ),
    "set_relay": FirmwareCommand(
        command="S1S{value}",
        description="Assign relay to S1s command (default=3)",
        category=CommandCategory.SPECTROMETER_1,
        has_parameter=True,
        response_prefix="S1",
    ),
}

SPECTROMETER_2_COMMANDS = {
    "power_cycle": FirmwareCommand(
        command="S2s",
        description="Spectrometer 2 power cycle",
        category=CommandCategory.SPECTROMETER_2,
        response_prefix="S2",
        timeout=10.0,
    ),
    "get_relay": FirmwareCommand(
        command="S2S?",
        description="Get number of relay triggered by S2s command",
        category=CommandCategory.SPECTROMETER_2,
        is_query=True,
        response_prefix="S2",
    ),
    "set_relay": FirmwareCommand(
        command="S2S{value}",
        description="Assign relay to S2s command (default=4)",
        category=CommandCategory.SPECTROMETER_2,
        has_parameter=True,
        response_prefix="S2",
    ),
}


# =============================================================================
# ALL COMMANDS - Combined reference
# =============================================================================

ALL_COMMANDS = {
    "head_sensor": HEAD_SENSOR_COMMANDS,
    "filter_wheel_1": FILTER_WHEEL_1_COMMANDS,
    "filter_wheel_2": FILTER_WHEEL_2_COMMANDS,
    "filter_wheels": FILTER_WHEELS_COMMON_COMMANDS,
    "tracker": TRACKER_COMMANDS,
    "azimuth_motor": AZIMUTH_MOTOR_COMMANDS,
    "zenith_motor": ZENITH_MOTOR_COMMANDS,
    "both_motors": BOTH_MOTORS_COMMANDS,
    "spectrometer_1": SPECTROMETER_1_COMMANDS,
    "spectrometer_2": SPECTROMETER_2_COMMANDS,
}


def get_command(category: str, command_name: str) -> Optional[FirmwareCommand]:
    """
    Get a command by category and name.

    Args:
        category: Command category (e.g., 'head_sensor', 'tracker')
        command_name: Command name (e.g., 'get_position', 'reset')

    Returns:
        FirmwareCommand if found, None otherwise

    Example:
        >>> cmd = get_command('tracker', 'get_position')
        >>> print(cmd.command)  # 'TRw'
    """
    commands = ALL_COMMANDS.get(category, {})
    return commands.get(command_name)


def list_commands(category: Optional[str] = None) -> dict:
    """
    List all available commands, optionally filtered by category.

    Args:
        category: Optional category to filter by

    Returns:
        Dictionary of commands
    """
    if category:
        return ALL_COMMANDS.get(category, {})
    return ALL_COMMANDS


def print_command_reference(category: Optional[str] = None) -> None:
    """
    Print a formatted command reference.

    Args:
        category: Optional category to filter by
    """
    commands = list_commands(category)

    if category:
        print(f"\n{'=' * 60}")
        print(f" {category.upper().replace('_', ' ')} COMMANDS")
        print(f"{'=' * 60}")
        for name, cmd in commands.items():
            print(f"\n  {name}:")
            print(f"    Command: {cmd.command}")
            print(f"    Description: {cmd.description}")
            if cmd.notes:
                print(f"    Notes: {cmd.notes}")
    else:
        for cat_name, cat_commands in commands.items():
            print(f"\n{'=' * 60}")
            print(f" {cat_name.upper().replace('_', ' ')} COMMANDS")
            print(f"{'=' * 60}")
            for name, cmd in cat_commands.items():
                print(f"  {name}: {cmd.description}")
