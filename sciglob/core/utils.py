"""Utility functions for SciGlob library."""

import math


def degrees_to_steps(
    degrees: float,
    degrees_per_step: float = 0.01,
    home_position: float = 0.0,
) -> int:
    """
    Convert angle in degrees to tracker step position.

    The tracker uses step positions relative to a home position.
    Position = (home_position - degrees) / degrees_per_step

    Args:
        degrees: Angle in degrees
        degrees_per_step: Tracker resolution (typically 0.01°/step)
        home_position: Home angle in degrees

    Returns:
        Step position (integer)
    """
    return round((home_position - degrees) / degrees_per_step)


def steps_to_degrees(
    steps: int,
    degrees_per_step: float = 0.01,
    home_position: float = 0.0,
) -> float:
    """
    Convert tracker step position to angle in degrees.

    Args:
        steps: Step position
        degrees_per_step: Tracker resolution
        home_position: Home angle in degrees

    Returns:
        Angle in degrees
    """
    return home_position - (steps * degrees_per_step)


def validate_angle(
    angle: float,
    min_angle: float,
    max_angle: float,
    wrap: bool = False,
) -> float:
    """
    Validate and optionally wrap an angle.

    Args:
        angle: Angle to validate
        min_angle: Minimum allowed angle
        max_angle: Maximum allowed angle
        wrap: If True, wrap angle to valid range instead of raising error

    Returns:
        Validated angle

    Raises:
        ValueError: If angle is out of range and wrap is False
    """
    if wrap:
        # Wrap to 0-360 range first
        while angle < 0:
            angle += 360.0
        while angle >= 360:
            angle -= 360.0

    if angle < min_angle or angle > max_angle:
        if not wrap:
            raise ValueError(f"Angle {angle} is out of range [{min_angle}, {max_angle}]")

    return angle


def normalize_azimuth(azimuth: float) -> float:
    """
    Normalize azimuth angle to 0-360 range.

    Args:
        azimuth: Azimuth angle in degrees

    Returns:
        Normalized angle (0-360)
    """
    azimuth = azimuth % 360.0
    if azimuth < 0:
        azimuth += 360.0
    return azimuth


def calculate_angular_distance(
    zen1: float,
    azi1: float,
    zen2: float,
    azi2: float,
) -> float:
    """
    Calculate angular distance between two directions.

    Args:
        zen1: Zenith angle of first direction (degrees)
        azi1: Azimuth angle of first direction (degrees)
        zen2: Zenith angle of second direction (degrees)
        azi2: Azimuth angle of second direction (degrees)

    Returns:
        Angular distance in degrees
    """
    # Convert to radians
    zen1_rad = math.radians(zen1)
    azi1_rad = math.radians(azi1)
    zen2_rad = math.radians(zen2)
    azi2_rad = math.radians(azi2)

    # Spherical law of cosines
    cos_dist = math.sin(zen1_rad) * math.sin(zen2_rad) * math.cos(azi1_rad - azi2_rad) + math.cos(
        zen1_rad
    ) * math.cos(zen2_rad)

    # Clamp to valid range
    cos_dist = max(-1.0, min(1.0, cos_dist))

    return math.degrees(math.acos(cos_dist))


def shortest_rotation_path(
    current: float,
    target: float,
    max_angle: float = 360.0,
) -> float:
    """
    Calculate shortest rotation to reach target angle.

    Args:
        current: Current angle (degrees)
        target: Target angle (degrees)
        max_angle: Maximum angle (for wrap calculation)

    Returns:
        Rotation delta (positive=clockwise, negative=counter-clockwise)
    """
    current = current % max_angle
    target = target % max_angle

    # Calculate both possible rotations
    clockwise = (target - current) % max_angle
    counter_clockwise = (current - target) % max_angle

    if clockwise <= counter_clockwise:
        return clockwise
    else:
        return -counter_clockwise


def dec2hex(value: int, nbits: int = 16) -> str:
    """
    Convert decimal to hex string for TETech commands.

    Handles negative values using two's complement.

    Args:
        value: Decimal integer (can be negative)
        nbits: Bit width (16 for TETech1, 32 for TETech2)

    Returns:
        Hex string padded to nbits/4 characters
    """
    vmax = 2**nbits
    nchar = nbits // 4

    if value < 0:
        hex_value = format((vmax + value) & (vmax - 1), "x")
    else:
        hex_value = format(abs(value), "x")

    return hex_value.zfill(nchar)


def hex2dec(hex_string: str, nbits: int = 16) -> int:
    """
    Convert hex string to decimal value.

    Handles negative values (two's complement).

    Args:
        hex_string: Hex string
        nbits: Bit width

    Returns:
        Decimal value
    """
    value = int(hex_string, 16)

    # Check if negative (first nibble > 7)
    if len(hex_string) > 0 and int(hex_string[0], 16) > 7:
        value = value - (2**nbits)

    return value


def get_checksum(hex_string: str) -> str:
    """
    Calculate checksum for TETech commands.

    Checksum is sum of ASCII values mod 256.

    Args:
        hex_string: Command string

    Returns:
        2-character hex checksum
    """
    total = sum(ord(c) for c in hex_string)
    return format(total % 256, "02x")


def parse_hdc2080_humidity(hex_response: str) -> float:
    """
    Parse HDC2080EVM humidity response.

    Response is 4-char hex in little-endian format.
    Humidity = (value / 2^16) * 100 [%]

    Args:
        hex_response: 4-character hex string

    Returns:
        Humidity in percent
    """
    # Swap bytes (little-endian)
    if len(hex_response) >= 4:
        hex_value = hex_response[-2:] + hex_response[:2]
        int_value = int(hex_value, 16)
        return (float(int_value) / 65536.0) * 100.0
    return -1.0


def parse_hdc2080_temperature(hex_response: str) -> float:
    """
    Parse HDC2080EVM temperature response.

    Response is 4-char hex in little-endian format.
    Temperature = (value / 2^16) * 165 - 40 [°C]

    Args:
        hex_response: 4-character hex string

    Returns:
        Temperature in Celsius
    """
    if len(hex_response) >= 4:
        hex_value = hex_response[-2:] + hex_response[:2]
        int_value = int(hex_value, 16)
        return (float(int_value) / 65536.0) * 165.0 - 40.0
    return -999.0


def nmea_to_decimal(coord: str, direction: str) -> float:
    """
    Convert NMEA coordinate to decimal degrees.

    NMEA format: DDMM.MMMM (lat) or DDDMM.MMMM (lon)

    Args:
        coord: NMEA coordinate string
        direction: Direction ('N', 'S', 'E', 'W')

    Returns:
        Decimal degrees
    """
    if not coord:
        return 0.0

    # Split degrees and minutes
    if direction in ["N", "S"]:
        degrees = float(coord[:2])
        minutes = float(coord[2:])
    else:  # E, W
        degrees = float(coord[:3])
        minutes = float(coord[3:])

    decimal = degrees + minutes / 60.0

    if direction in ["S", "W"]:
        decimal = -decimal

    return decimal


def shadowband_angle_to_position(
    angle_deg: float,
    resolution: float,
    ratio: float,
) -> int:
    """
    Convert shadowband angle to step position.

    Args:
        angle_deg: Relative shadowband angle in degrees
        resolution: Degrees per step
        ratio: Shadowband offset / radius ratio

    Returns:
        Step position (integer)
    """
    delta = math.degrees(math.asin(math.sin(math.radians(angle_deg)) * ratio))
    alfa = angle_deg - delta
    return int(round((alfa + 90) / resolution))


def position_to_shadowband_angle(
    position: int,
    resolution: float,
    ratio: float,
) -> float:
    """
    Convert step position to shadowband angle.

    Args:
        position: Step position
        resolution: Degrees per step
        ratio: Shadowband offset / radius ratio

    Returns:
        Shadowband angle in degrees
    """
    alfa = position * resolution - 90
    alfa_rad = math.radians(alfa)

    xq = 1 + ratio**2 - 2 * ratio * math.cos(alfa_rad)
    sbeta = math.sin(alfa_rad) / math.sqrt(xq)
    sbangle = math.degrees(math.asin(sbeta))

    if xq > (1 - ratio**2):
        sbangle = 180 - sbangle
    if sbangle > 180:
        sbangle -= 360

    return sbangle
