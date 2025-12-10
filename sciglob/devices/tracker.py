"""Tracker/Motor control interface for SciGlob instruments."""

import logging
import time
from typing import TYPE_CHECKING, Any, Optional

from sciglob.core.connection import parse_position_response, parse_response
from sciglob.core.exceptions import (
    MotorAlarmError,
    PositionError,
    TrackerError,
)
from sciglob.core.help_mixin import HelpMixin
from sciglob.core.protocols import (
    MOTOR_TEMP_COMMANDS,
    SENSOR_CONVERSIONS,
    TIMING_CONFIG,
    get_error_message,
    get_motor_alarm_message,
)
from sciglob.core.utils import (
    degrees_to_steps,
    normalize_azimuth,
    steps_to_degrees,
)

if TYPE_CHECKING:
    from sciglob.devices.head_sensor import HeadSensor


class Tracker(HelpMixin):
    """
    Tracker/Motor controller interface.

    Controls azimuth (pan) and zenith (tilt) motors through the Head Sensor.
    All positioning is done in steps internally, with degree conversion provided.

    Supported tracker types:
    - Directed Perceptions: Standard tracker
    - LuftBlickTR1: Modern tracker with motor temperature sensors and alarms

    Example:
        >>> with HeadSensor(port="/dev/ttyUSB0") as hs:
        ...     tracker = hs.tracker
        ...     # Move to position (in degrees)
        ...     tracker.move_to(zenith=45.0, azimuth=180.0)
        ...     # Get current position
        ...     zen, azi = tracker.get_position()
        ...     print(f"Position: zenith={zen}°, azimuth={azi}°")
        ...     # Move in steps directly
        ...     tracker.move_to_steps(zenith_steps=4500, azimuth_steps=-1200)

    Help:
        >>> tracker.help()              # Show full help
        >>> tracker.help('move_to')     # Help for specific method
        >>> tracker.list_methods()      # List all methods
    """

    # HelpMixin properties
    _device_name = "Tracker"
    _device_description = "Motor controller for azimuth (pan) and zenith (tilt) positioning"
    _supported_types = ["Directed Perceptions", "LuftBlickTR1"]
    _default_config = {
        "degrees_per_step": 0.01,
        "zenith_limits": "[0, 90] degrees",
        "azimuth_limits": "[0, 360] degrees",
        "home_position": "[0.0, 180.0] degrees",
    }
    _command_reference = {
        "TRw": "Get current position (WHERE command)",
        "TRb<az>,<zen>": "Move both axes (BOTH command)",
        "TRp<steps>": "Move azimuth (PAN command)",
        "TRt<steps>": "Move zenith (TILT command)",
        "TRr": "Soft reset tracker",
        "TRY": "Power cycle tracker",
        "TRm": "Get magnetic encoder position (LuftBlickTR1)",
        "MA!t?": "Get azimuth motor temperature",
        "MZ!t?": "Get zenith motor temperature",
        "MA!a?": "Get azimuth alarm status",
        "MZ!a?": "Get zenith alarm status",
    }

    def __init__(self, head_sensor: "HeadSensor"):
        """
        Initialize the Tracker interface.

        Args:
            head_sensor: Connected HeadSensor instance
        """
        self._hs = head_sensor
        self.logger = logging.getLogger("sciglob.Tracker")

        # Cached position (in steps)
        self._zenith_steps: int = 0
        self._azimuth_steps: int = 0
        self._position_valid: bool = False

    @property
    def tracker_type(self) -> str:
        """Get the tracker type."""
        return self._hs.tracker_type

    @property
    def degrees_per_step(self) -> float:
        """Get the tracker resolution (degrees per step)."""
        return self._hs.degrees_per_step

    @property
    def is_luftblick(self) -> bool:
        """Check if this is a LuftBlickTR1 tracker."""
        return "LuftBlick" in self.tracker_type

    @property
    def zenith_home(self) -> float:
        """Get zenith home position in degrees."""
        return self._hs.home_position[0]

    @property
    def azimuth_home(self) -> float:
        """Get azimuth home position in degrees."""
        return self._hs.home_position[1]

    @property
    def zenith_limits(self) -> tuple[float, float]:
        """Get zenith motion limits (min, max) in degrees."""
        limits = self._hs.motion_limits
        return (limits[0], limits[1])

    @property
    def azimuth_limits(self) -> tuple[float, float]:
        """Get azimuth motion limits (min, max) in degrees."""
        limits = self._hs.motion_limits
        return (limits[2], limits[3])

    def _send_command(self, command: str, timeout: Optional[float] = None) -> str:
        """Send a command through the Head Sensor."""
        return self._hs.send_command(command, timeout)

    def _check_response(self, response: str, expected_prefix: str = "TR") -> None:
        """
        Check response for errors.

        Raises:
            TrackerError: If response indicates an error
        """
        success, data, error_code = parse_response(response, expected_prefix)

        if not success and error_code is not None and error_code != 0:
            raise TrackerError(
                f"Tracker error: {get_error_message(error_code)}",
                error_code=error_code,
            )

    def get_position_steps(self) -> tuple[int, int]:
        """
        Get current position in steps.

        Returns:
            Tuple of (azimuth_steps, zenith_steps)

        Raises:
            TrackerError: If query fails
        """
        response = self._send_command("TRw", timeout=TIMING_CONFIG["position_query_timeout"])

        azimuth, zenith = parse_position_response(response)

        if azimuth is None or zenith is None:
            raise TrackerError(f"Invalid position response: {response}")

        # Cache the position
        self._azimuth_steps = azimuth
        self._zenith_steps = zenith
        self._position_valid = True

        return azimuth, zenith

    def get_position(self) -> tuple[float, float]:
        """
        Get current position in degrees.

        Returns:
            Tuple of (zenith_degrees, azimuth_degrees)

        Raises:
            TrackerError: If query fails
        """
        azi_steps, zen_steps = self.get_position_steps()

        zenith = steps_to_degrees(
            zen_steps,
            self.degrees_per_step,
            self.zenith_home,
        )
        azimuth = steps_to_degrees(
            azi_steps,
            self.degrees_per_step,
            self.azimuth_home,
        )

        return zenith, azimuth

    def get_magnetic_position_steps(self) -> tuple[int, int]:
        """
        Get absolute encoder position (LuftBlickTR1 only).

        Returns:
            Tuple of (azimuth_steps, zenith_steps)

        Raises:
            TrackerError: If not LuftBlickTR1 or query fails
        """
        if not self.is_luftblick:
            raise TrackerError("Magnetic encoder only available on LuftBlickTR1")

        response = self._send_command("TRm", timeout=TIMING_CONFIG["position_query_timeout"])

        azimuth, zenith = parse_position_response(response)

        if azimuth is None or zenith is None:
            raise TrackerError(f"Invalid magnetic position response: {response}")

        return azimuth, zenith

    def move_to_steps(
        self,
        zenith_steps: Optional[int] = None,
        azimuth_steps: Optional[int] = None,
        wait: bool = True,
    ) -> None:
        """
        Move to position specified in steps.

        Args:
            zenith_steps: Target zenith position in steps
            azimuth_steps: Target azimuth position in steps
            wait: If True, wait for movement to complete

        Raises:
            TrackerError: If movement fails
        """
        # Determine which axes to move
        if zenith_steps is not None and azimuth_steps is not None:
            # Move both axes
            command = f"TRb{azimuth_steps},{zenith_steps}"
            timeout = TIMING_CONFIG["movement_timeout"]
        elif azimuth_steps is not None:
            # Pan only (azimuth)
            command = f"TRp{azimuth_steps}"
            timeout = TIMING_CONFIG["movement_timeout"]
        elif zenith_steps is not None:
            # Tilt only (zenith)
            command = f"TRt{zenith_steps}"
            timeout = TIMING_CONFIG["movement_timeout"]
        else:
            self.logger.warning("No position specified for movement")
            return

        self.logger.info(f"Moving tracker: {command}")
        response = self._send_command(command, timeout=timeout)
        self._check_response(response)

        # Update cached position
        if zenith_steps is not None:
            self._zenith_steps = zenith_steps
        if azimuth_steps is not None:
            self._azimuth_steps = azimuth_steps
        self._position_valid = True

        if wait:
            # Small delay for movement
            time.sleep(0.5)
            # Verify position
            self.get_position_steps()

    def move_to(
        self,
        zenith: Optional[float] = None,
        azimuth: Optional[float] = None,
        wait: bool = True,
    ) -> None:
        """
        Move to position specified in degrees.

        Args:
            zenith: Target zenith angle in degrees
            azimuth: Target azimuth angle in degrees
            wait: If True, wait for movement to complete

        Raises:
            PositionError: If position is out of limits
            TrackerError: If movement fails
        """
        zenith_steps = None
        azimuth_steps = None

        if zenith is not None:
            # Validate zenith
            zen_min, zen_max = self.zenith_limits
            if zenith < zen_min or zenith > zen_max:
                raise PositionError(zenith, zen_min, zen_max, axis="Zenith")
            zenith_steps = degrees_to_steps(zenith, self.degrees_per_step, self.zenith_home)

        if azimuth is not None:
            # Normalize and validate azimuth
            azimuth = normalize_azimuth(azimuth)
            azi_min, azi_max = self.azimuth_limits
            if azi_min <= azi_max:
                if azimuth < azi_min or azimuth > azi_max:
                    raise PositionError(azimuth, azi_min, azi_max, axis="Azimuth")
            azimuth_steps = degrees_to_steps(azimuth, self.degrees_per_step, self.azimuth_home)

        self.move_to_steps(
            zenith_steps=zenith_steps,
            azimuth_steps=azimuth_steps,
            wait=wait,
        )

    def move_relative(
        self,
        delta_zenith: float = 0.0,
        delta_azimuth: float = 0.0,
        wait: bool = True,
    ) -> None:
        """
        Move relative to current position.

        Args:
            delta_zenith: Degrees to move in zenith
            delta_azimuth: Degrees to move in azimuth
            wait: If True, wait for movement to complete
        """
        # Get current position
        current_zen, current_azi = self.get_position()

        # Calculate new position
        new_zenith = current_zen + delta_zenith if delta_zenith != 0 else None
        new_azimuth = current_azi + delta_azimuth if delta_azimuth != 0 else None

        self.move_to(zenith=new_zenith, azimuth=new_azimuth, wait=wait)

    def pan(self, azimuth: float, wait: bool = True) -> None:
        """
        Move azimuth only.

        Args:
            azimuth: Target azimuth angle in degrees
            wait: If True, wait for movement to complete
        """
        self.move_to(azimuth=azimuth, wait=wait)

    def tilt(self, zenith: float, wait: bool = True) -> None:
        """
        Move zenith only.

        Args:
            zenith: Target zenith angle in degrees
            wait: If True, wait for movement to complete
        """
        self.move_to(zenith=zenith, wait=wait)

    def home(self, wait: bool = True) -> None:
        """
        Move to home position.

        Args:
            wait: If True, wait for movement to complete
        """
        self.logger.info("Moving to home position")
        self.move_to(
            zenith=self.zenith_home,
            azimuth=self.azimuth_home,
            wait=wait,
        )

    def park(
        self,
        zenith: float = 90.0,
        azimuth: float = 0.0,
        wait: bool = True,
    ) -> None:
        """
        Move to parking position.

        Args:
            zenith: Parking zenith angle (default 90° = straight down)
            azimuth: Parking azimuth angle
            wait: If True, wait for movement to complete
        """
        self.logger.info(f"Parking at zenith={zenith}°, azimuth={azimuth}°")
        self.move_to(zenith=zenith, azimuth=azimuth, wait=wait)

    def reset(self) -> bool:
        """
        Perform soft reset of the tracker.

        Returns:
            True if successful
        """
        self.logger.info("Resetting tracker (soft)")

        timeout = TIMING_CONFIG["soft_reset_timeout"]
        if self.is_luftblick:
            timeout = TIMING_CONFIG["luftblick_soft_reset_wait"]

        response = self._send_command("TRr", timeout=timeout)
        self._check_response(response)

        self._position_valid = False
        return True

    def power_reset(self) -> bool:
        """
        Perform power cycle of the tracker.

        Returns:
            True if successful
        """
        self.logger.info("Power cycling tracker")

        timeout = TIMING_CONFIG["power_reset_timeout"]
        if self.is_luftblick:
            timeout = TIMING_CONFIG["luftblick_power_reset_wait"]

        response = self._send_command("TRs", timeout=timeout)
        self._check_response(response)

        self._position_valid = False
        return True

    def get_motor_temperatures(self) -> dict[str, float]:
        """
        Get motor temperatures (LuftBlickTR1 only).

        Returns:
            Dictionary with motor temperatures:
            - azimuth_driver: Driver temperature
            - azimuth_motor: Motor temperature
            - zenith_driver: Driver temperature
            - zenith_motor: Motor temperature

        Raises:
            TrackerError: If not LuftBlickTR1
        """
        if not self.is_luftblick:
            raise TrackerError("Motor temperatures only available on LuftBlickTR1")

        temps = {}
        factor = SENSOR_CONVERSIONS["motor_temp"]["factor"]
        error_val = SENSOR_CONVERSIONS["motor_temp"]["error_value"]

        # Query each temperature
        for name, protocol in MOTOR_TEMP_COMMANDS.items():
            if "alarm" in name:
                continue

            try:
                response = self._send_command(protocol.command)

                # Parse response: "MA!<value>" or "MZ!<value>"
                if "!" in response:
                    value_str = response.split("!")[1].strip()
                    temps[name] = float(value_str) / factor
                else:
                    temps[name] = error_val
            except Exception as e:
                self.logger.error(f"Failed to read {name}: {e}")
                temps[name] = error_val

        return temps

    def get_motor_alarms(self) -> dict[str, tuple[int, str]]:
        """
        Get motor alarm status (LuftBlickTR1 only).

        Returns:
            Dictionary with alarm status:
            - zenith: (alarm_code, message)
            - azimuth: (alarm_code, message)

        Raises:
            TrackerError: If not LuftBlickTR1
        """
        if not self.is_luftblick:
            raise TrackerError("Motor alarms only available on LuftBlickTR1")

        alarms = {}

        for axis, cmd in [("zenith", "MZa?"), ("azimuth", "MAa?")]:
            try:
                response = self._send_command(cmd)

                # Parse response: "Alarm Code = N" or "MZN" / "MAN"
                if "Alarm Code" in response:
                    code = int(response.split("=")[1].strip())
                else:
                    # Extract code from response like "MZ5"
                    code = int(response[2:]) if len(response) > 2 else 0

                alarms[axis] = (code, get_motor_alarm_message(code))

            except Exception as e:
                self.logger.error(f"Failed to read {axis} alarm: {e}")
                alarms[axis] = (-1, str(e))

        return alarms

    def check_alarms(self) -> None:
        """
        Check for motor alarms and raise exception if any found.

        Raises:
            MotorAlarmError: If any motor has an alarm
        """
        if not self.is_luftblick:
            return

        alarms = self.get_motor_alarms()

        for axis, (code, message) in alarms.items():
            if code != 0:
                raise MotorAlarmError(
                    f"{axis.capitalize()} motor alarm: {message}",
                    alarm_code=code,
                    axis=axis,
                )

    def get_status(self) -> dict[str, Any]:
        """
        Get comprehensive tracker status.

        Returns:
            Dictionary with status information
        """
        status = {
            "tracker_type": self.tracker_type,
            "degrees_per_step": self.degrees_per_step,
            "home_position": {
                "zenith": self.zenith_home,
                "azimuth": self.azimuth_home,
            },
            "limits": {
                "zenith": self.zenith_limits,
                "azimuth": self.azimuth_limits,
            },
        }

        try:
            zen, azi = self.get_position()
            azi_steps, zen_steps = self._azimuth_steps, self._zenith_steps
            status["position"] = {
                "zenith_degrees": zen,
                "azimuth_degrees": azi,
                "zenith_steps": zen_steps,
                "azimuth_steps": azi_steps,
            }
        except Exception as e:
            status["position"] = {"error": str(e)}

        if self.is_luftblick:
            try:
                status["motor_temperatures"] = self.get_motor_temperatures()
            except Exception as e:
                status["motor_temperatures"] = {"error": str(e)}

            try:
                status["motor_alarms"] = self.get_motor_alarms()
            except Exception as e:
                status["motor_alarms"] = {"error": str(e)}

        return status

