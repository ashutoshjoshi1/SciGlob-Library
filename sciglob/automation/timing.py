"""
Timing and astronomical calculations for SciGlob automation.

Provides calculations for:
- Solar position (zenith angle, azimuth)
- Lunar position and phase
- Sunrise, sunset, solar noon
- Schedule time calculations

Based on the astronomical calculations in Blick's blick_atmos.py
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


# Constants
DEG2RAD = math.pi / 180.0
RAD2DEG = 180.0 / math.pi
EARTH_RADIUS_EQUATOR = 6378.5  # in km
EARTH_RADIUS_POLAR = 6357.0   # in km


class Target(Enum):
    """Astronomical targets for positioning."""
    SUN = auto()
    MOON = auto()


@dataclass
class SolarPosition:
    """
    Solar position at a given time and location.

    Attributes:
        zenith_angle: Solar zenith angle in degrees (0 = overhead, 90 = horizon)
        azimuth: Solar azimuth in degrees (0 = north, 90 = east)
        hour_angle: Hour angle in degrees
        declination: Solar declination in degrees
        right_ascension: Right ascension in degrees
        distance: Earth-Sun distance in AU
    """
    zenith_angle: float
    azimuth: float
    hour_angle: float = 0.0
    declination: float = 0.0
    right_ascension: float = 0.0
    distance: float = 1.0

    @property
    def elevation(self) -> float:
        """Solar elevation angle (90 - zenith_angle)."""
        return 90.0 - self.zenith_angle

    @property
    def is_above_horizon(self) -> bool:
        """Check if sun is above the horizon."""
        return self.zenith_angle < 90.0

    @property
    def is_daytime(self) -> bool:
        """Check if it's daytime (sun well above horizon)."""
        return self.zenith_angle < 85.0


@dataclass
class LunarPosition:
    """
    Lunar position at a given time and location.

    Attributes:
        zenith_angle: Lunar zenith angle in degrees
        azimuth: Lunar azimuth in degrees
        phase: Lunar phase (0-1, 0=new moon, 0.5=full moon)
        illumination: Illuminated fraction (0-1)
        distance: Earth-Moon distance in km
    """
    zenith_angle: float
    azimuth: float
    phase: float = 0.0
    illumination: float = 0.0
    distance: float = 384400.0  # Average Earth-Moon distance

    @property
    def is_above_horizon(self) -> bool:
        """Check if moon is above the horizon."""
        return self.zenith_angle < 90.0


@dataclass
class AstronomicalEvents:
    """
    Daily astronomical events for a location.

    Attributes:
        date: Date for these events (UTC)
        latitude: Location latitude in degrees
        longitude: Location longitude in degrees
        sunrise: UTC datetime of sunrise
        sunset: UTC datetime of sunset
        solar_noon: UTC datetime of solar noon
        civil_dawn: Civil twilight dawn
        civil_dusk: Civil twilight dusk
        moonrise: UTC datetime of moonrise
        moonset: UTC datetime of moonset
    """
    date: datetime
    latitude: float
    longitude: float
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None
    solar_noon: Optional[datetime] = None
    civil_dawn: Optional[datetime] = None
    civil_dusk: Optional[datetime] = None
    nautical_dawn: Optional[datetime] = None
    nautical_dusk: Optional[datetime] = None
    moonrise: Optional[datetime] = None
    moonset: Optional[datetime] = None

    # Events dictionary for flexible access
    _events: dict[str, Optional[datetime]] = field(default_factory=dict)

    def __post_init__(self):
        """Build events dictionary."""
        self._events = {
            "localmidnight": datetime.combine(self.date.date(), datetime.min.time(), tzinfo=timezone.utc),
            "localnoon": self.solar_noon,
            "solarzen90am": self.sunrise,
            "solarzen90pm": self.sunset,
            "sunrise": self.sunrise,
            "sunset": self.sunset,
            "civil_dawn": self.civil_dawn,
            "civil_dusk": self.civil_dusk,
            "moonrise": self.moonrise,
            "moonset": self.moonset,
        }

    def get_event_time(self, event_name: str) -> Optional[datetime]:
        """Get the time for a named event."""
        return self._events.get(event_name.lower())

    @property
    def day_length(self) -> Optional[timedelta]:
        """Get the length of the day."""
        if self.sunrise and self.sunset:
            return self.sunset - self.sunrise
        return None


class TimeCalculator:
    """
    Calculator for astronomical times and schedule timing.

    Uses simplified algorithms suitable for scheduling purposes.
    For high-precision calculations, consider using external libraries.
    """

    def __init__(
        self,
        latitude: float,
        longitude: float,
        altitude: float = 0.0,
    ):
        """
        Initialize time calculator for a location.

        Args:
            latitude: Location latitude in degrees (positive = north)
            longitude: Location longitude in degrees (positive = east)
            altitude: Location altitude in meters
        """
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude

    def calculate_solar_position(self, dt: datetime) -> SolarPosition:
        """
        Calculate solar position for a given datetime.

        Args:
            dt: UTC datetime

        Returns:
            SolarPosition object
        """
        # Convert to UTC if needed
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        elif dt.tzinfo != timezone.utc:
            dt = dt.astimezone(timezone.utc)

        # Calculate Julian date
        jd = self._datetime_to_julian(dt)

        # Calculate solar coordinates
        sun_coords = self._sun_coordinates(jd)

        # Calculate hour angle
        gmst = self._greenwich_mean_sidereal_time(jd)
        local_sidereal_time = gmst + self.longitude
        hour_angle = local_sidereal_time - sun_coords["right_ascension"]

        # Normalize hour angle to -180 to 180
        while hour_angle > 180:
            hour_angle -= 360
        while hour_angle < -180:
            hour_angle += 360

        # Calculate zenith and azimuth
        lat_rad = self.latitude * DEG2RAD
        dec_rad = sun_coords["declination"] * DEG2RAD
        ha_rad = hour_angle * DEG2RAD

        cos_z = (
            math.sin(lat_rad) * math.sin(dec_rad) +
            math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad)
        )
        cos_z = max(-1, min(1, cos_z))  # Clamp to valid range
        zenith = math.acos(cos_z) * RAD2DEG

        # Calculate azimuth
        sin_az = -math.cos(dec_rad) * math.sin(ha_rad)
        cos_az = (
            math.sin(dec_rad) * math.cos(lat_rad) -
            math.cos(dec_rad) * math.sin(lat_rad) * math.cos(ha_rad)
        )
        azimuth = math.atan2(sin_az, cos_az) * RAD2DEG

        # Normalize azimuth to 0-360
        if azimuth < 0:
            azimuth += 360

        return SolarPosition(
            zenith_angle=zenith,
            azimuth=azimuth,
            hour_angle=hour_angle,
            declination=sun_coords["declination"],
            right_ascension=sun_coords["right_ascension"],
            distance=sun_coords["distance"],
        )

    def calculate_lunar_position(self, dt: datetime) -> LunarPosition:
        """
        Calculate lunar position for a given datetime.

        This is a simplified calculation. For high-precision lunar
        calculations, consider using specialized astronomy libraries.

        Args:
            dt: UTC datetime

        Returns:
            LunarPosition object
        """
        # Convert to UTC if needed
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        jd = self._datetime_to_julian(dt)

        # Simplified lunar position calculation
        # Days since J2000.0
        d = jd - 2451545.0

        # Lunar mean longitude (degrees)
        L = (218.32 + 13.176396 * d) % 360

        # Mean anomaly (degrees)
        M = (134.9 + 13.064993 * d) % 360

        # Mean distance (degrees)
        F = (93.3 + 13.229350 * d) % 360

        # Lunar longitude
        lon = L + 6.29 * math.sin(M * DEG2RAD)
        lon = lon % 360

        # Lunar latitude (simplified)
        lat = 5.13 * math.sin(F * DEG2RAD)

        # Convert to RA/Dec
        obliquity = 23.4393 * DEG2RAD
        lon_rad = lon * DEG2RAD
        lat_rad = lat * DEG2RAD

        ra = math.atan2(
            math.sin(lon_rad) * math.cos(obliquity) - math.tan(lat_rad) * math.sin(obliquity),
            math.cos(lon_rad)
        ) * RAD2DEG

        dec = math.asin(
            math.sin(lat_rad) * math.cos(obliquity) +
            math.cos(lat_rad) * math.sin(obliquity) * math.sin(lon_rad)
        ) * RAD2DEG

        # Calculate hour angle
        gmst = self._greenwich_mean_sidereal_time(jd)
        local_sidereal_time = gmst + self.longitude
        hour_angle = local_sidereal_time - ra

        # Calculate zenith and azimuth
        lat_rad = self.latitude * DEG2RAD
        dec_rad = dec * DEG2RAD
        ha_rad = hour_angle * DEG2RAD

        cos_z = (
            math.sin(lat_rad) * math.sin(dec_rad) +
            math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad)
        )
        cos_z = max(-1, min(1, cos_z))
        zenith = math.acos(cos_z) * RAD2DEG

        sin_az = -math.cos(dec_rad) * math.sin(ha_rad)
        cos_az = (
            math.sin(dec_rad) * math.cos(lat_rad) -
            math.cos(dec_rad) * math.sin(lat_rad) * math.cos(ha_rad)
        )
        azimuth = math.atan2(sin_az, cos_az) * RAD2DEG
        if azimuth < 0:
            azimuth += 360

        # Calculate lunar phase
        sun = self.calculate_solar_position(dt)
        phase_angle = abs(lon - sun.right_ascension - sun.hour_angle)
        phase = (1 - math.cos(phase_angle * DEG2RAD)) / 2
        illumination = (1 + math.cos((phase_angle) * DEG2RAD)) / 2

        return LunarPosition(
            zenith_angle=zenith,
            azimuth=azimuth,
            phase=phase,
            illumination=illumination,
        )

    def calculate_events(self, date: datetime) -> AstronomicalEvents:
        """
        Calculate astronomical events for a given date.

        Args:
            date: Date for which to calculate events

        Returns:
            AstronomicalEvents object
        """
        # Ensure date is UTC
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)

        # Start of day
        day_start = datetime.combine(date.date(), datetime.min.time(), tzinfo=timezone.utc)

        # Calculate solar noon (when sun is at highest point)
        solar_noon = self._calculate_solar_noon(day_start)

        # Calculate sunrise/sunset (zenith = 90.833 degrees for standard)
        sunrise, sunset = self._calculate_sunrise_sunset(day_start, zenith_angle=90.833)

        # Civil twilight (zenith = 96 degrees)
        civil_dawn, civil_dusk = self._calculate_sunrise_sunset(day_start, zenith_angle=96.0)

        # Nautical twilight (zenith = 102 degrees)
        nautical_dawn, nautical_dusk = self._calculate_sunrise_sunset(day_start, zenith_angle=102.0)

        return AstronomicalEvents(
            date=day_start,
            latitude=self.latitude,
            longitude=self.longitude,
            sunrise=sunrise,
            sunset=sunset,
            solar_noon=solar_noon,
            civil_dawn=civil_dawn,
            civil_dusk=civil_dusk,
            nautical_dawn=nautical_dawn,
            nautical_dusk=nautical_dusk,
        )

    def _datetime_to_julian(self, dt: datetime) -> float:
        """Convert datetime to Julian date."""
        year = dt.year
        month = dt.month
        day = dt.day + (dt.hour + dt.minute / 60 + dt.second / 3600) / 24

        if month <= 2:
            year -= 1
            month += 12

        a = int(year / 100)
        b = 2 - a + int(a / 4)

        jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524.5
        return jd

    def _sun_coordinates(self, jd: float) -> dict[str, float]:
        """Calculate sun coordinates for a Julian date."""
        # Days since J2000.0
        n = jd - 2451545.0

        # Mean longitude (degrees)
        L = (280.460 + 0.9856474 * n) % 360

        # Mean anomaly (degrees)
        g = (357.528 + 0.9856003 * n) % 360
        g_rad = g * DEG2RAD

        # Ecliptic longitude (degrees)
        lambda_sun = L + 1.915 * math.sin(g_rad) + 0.020 * math.sin(2 * g_rad)
        lambda_rad = lambda_sun * DEG2RAD

        # Obliquity of ecliptic (degrees)
        epsilon = 23.439 - 0.0000004 * n
        epsilon_rad = epsilon * DEG2RAD

        # Right ascension
        ra = math.atan2(math.cos(epsilon_rad) * math.sin(lambda_rad), math.cos(lambda_rad))
        ra = ra * RAD2DEG
        if ra < 0:
            ra += 360

        # Declination
        dec = math.asin(math.sin(epsilon_rad) * math.sin(lambda_rad))
        dec = dec * RAD2DEG

        # Distance in AU
        distance = 1.00014 - 0.01671 * math.cos(g_rad) - 0.00014 * math.cos(2 * g_rad)

        return {
            "right_ascension": ra,
            "declination": dec,
            "distance": distance,
        }

    def _greenwich_mean_sidereal_time(self, jd: float) -> float:
        """Calculate Greenwich Mean Sidereal Time."""
        # Julian centuries since J2000.0
        t = (jd - 2451545.0) / 36525.0

        # GMST at 0h UT
        gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0)
        gmst += 0.000387933 * t * t - t * t * t / 38710000

        return gmst % 360

    def _calculate_solar_noon(self, date: datetime) -> datetime:
        """Calculate solar noon for a given date."""
        # Solar noon occurs when the sun crosses the local meridian
        # Approximation: 12:00 - longitude_offset
        offset_hours = -self.longitude / 15.0
        noon = datetime.combine(
            date.date(),
            datetime.min.time(),
            tzinfo=timezone.utc
        ) + timedelta(hours=12 + offset_hours)

        # Refine with equation of time
        jd = self._datetime_to_julian(noon)
        sun = self._sun_coordinates(jd)

        # Equation of time (minutes)
        eot = 4 * (sun["right_ascension"] - (self.longitude + 180 + 360 * (jd - 2451545.0)) % 360)

        return noon - timedelta(minutes=eot)

    def _calculate_sunrise_sunset(
        self,
        date: datetime,
        zenith_angle: float = 90.833,
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """
        Calculate sunrise and sunset times.

        Args:
            date: Date for calculation
            zenith_angle: Zenith angle for event (90.833 for standard sunrise/sunset)

        Returns:
            (sunrise, sunset) tuple, None for polar day/night
        """
        # Julian date at noon
        noon = datetime.combine(date.date(), datetime.min.time(), tzinfo=timezone.utc)
        noon += timedelta(hours=12)
        jd = self._datetime_to_julian(noon)

        # Sun coordinates at noon
        sun = self._sun_coordinates(jd)

        lat_rad = self.latitude * DEG2RAD
        dec_rad = sun["declination"] * DEG2RAD
        zen_rad = zenith_angle * DEG2RAD

        # Calculate hour angle
        cos_ha = (math.cos(zen_rad) - math.sin(lat_rad) * math.sin(dec_rad)) / (
            math.cos(lat_rad) * math.cos(dec_rad)
        )

        # Check if sun rises/sets at this latitude
        if cos_ha < -1 or cos_ha > 1:
            return None, None  # Polar day or night

        ha = math.acos(cos_ha) * RAD2DEG
        ha_hours = ha / 15.0

        # Calculate solar noon
        solar_noon = self._calculate_solar_noon(date)

        sunrise = solar_noon - timedelta(hours=ha_hours)
        sunset = solar_noon + timedelta(hours=ha_hours)

        return sunrise, sunset


# Convenience functions
def calculate_solar_position(
    latitude: float,
    longitude: float,
    dt: Optional[datetime] = None,
) -> SolarPosition:
    """
    Calculate solar position for a location and time.

    Args:
        latitude: Location latitude in degrees
        longitude: Location longitude in degrees
        dt: UTC datetime (default: now)

    Returns:
        SolarPosition object
    """
    if dt is None:
        dt = datetime.now(timezone.utc)

    calculator = TimeCalculator(latitude, longitude)
    return calculator.calculate_solar_position(dt)


def calculate_lunar_position(
    latitude: float,
    longitude: float,
    dt: Optional[datetime] = None,
) -> LunarPosition:
    """
    Calculate lunar position for a location and time.

    Args:
        latitude: Location latitude in degrees
        longitude: Location longitude in degrees
        dt: UTC datetime (default: now)

    Returns:
        LunarPosition object
    """
    if dt is None:
        dt = datetime.now(timezone.utc)

    calculator = TimeCalculator(latitude, longitude)
    return calculator.calculate_lunar_position(dt)

