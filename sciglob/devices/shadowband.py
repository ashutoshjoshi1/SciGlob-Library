"""Shadowband control interface for SciGlob instruments."""

import logging
from typing import TYPE_CHECKING, Any, Optional

from sciglob.core.connection import parse_response
from sciglob.core.exceptions import DeviceError
from sciglob.core.help_mixin import HelpMixin
from sciglob.core.protocols import get_error_message
from sciglob.core.utils import position_to_shadowband_angle, shadowband_angle_to_position

if TYPE_CHECKING:
    from sciglob.devices.head_sensor import HeadSensor


class Shadowband(HelpMixin):
    """
    Shadowband controller interface.

    Controls the shadowband arm position through the Head Sensor.

    Commands:
    - Move: "SBm<position>" - Move to step position (-1000 to 1000)
    - Reset: "SBr" - Reset shadowband to home position
    - Response: "SB0" (success) or "SB<N>" (error code N)

    Position Limits:
    - Minimum: -1000 steps
    - Maximum: 1000 steps

    Example:
        >>> with HeadSensor(port="/dev/ttyUSB0") as hs:
        ...     sb = hs.shadowband
        ...     sb.move_to_position(500)
        ...     sb.move_to_angle(45.0)
        ...     sb.reset()

    Help:
        >>> sb.help()              # Show full help
    """

    # Position limits (from Blick reference)
    MIN_POSITION = -1000
    MAX_POSITION = 1000

    # HelpMixin properties
    _device_name = "Shadowband"
    _device_description = "Shadowband arm position controller"
    _supported_types = ["SB"]
    _default_config = {
        "resolution": "0.36 degrees/step",
        "ratio": "0.5 (offset/radius)",
        "position_limits": "[-1000, 1000] steps",
    }
    _command_reference = {
        "SBm<pos>": "Move to step position (-1000 to 1000)",
        "SBr": "Reset shadowband to home",
        "SBs": "Power reset shadowband",
    }

    def __init__(
        self,
        head_sensor: "HeadSensor",
        resolution: float = 0.36,
        ratio: float = 0.5,
    ):
        """
        Initialize the Shadowband controller.

        Args:
            head_sensor: Connected HeadSensor instance
            resolution: Degrees per step
            ratio: Shadowband offset / radius ratio
        """
        self._hs = head_sensor
        self._resolution = resolution
        self._ratio = ratio
        self.logger = logging.getLogger("sciglob.Shadowband")

        # Current position in steps
        self._position: int = 0

    @property
    def position(self) -> int:
        """Get current position in steps."""
        return self._position

    @property
    def angle(self) -> float:
        """Get current angle in degrees."""
        return position_to_shadowband_angle(
            self._position,
            self._resolution,
            self._ratio,
        )

    @property
    def resolution(self) -> float:
        """Get degrees per step."""
        return self._resolution

    @property
    def ratio(self) -> float:
        """Get shadowband offset/radius ratio."""
        return self._ratio

    def _send_command(self, command: str, timeout: Optional[float] = None) -> str:
        """Send a command through the Head Sensor."""
        return self._hs.send_command(command, timeout)

    def _check_response(self, response: str) -> None:
        """Check response for errors."""
        success, data, error_code = parse_response(response, "SB")

        if not success and error_code is not None and error_code != 0:
            raise DeviceError(
                f"Shadowband error: {get_error_message(error_code)}",
                error_code=error_code,
            )

    def move_to_position(self, position: int) -> None:
        """
        Move shadowband to step position.

        Args:
            position: Target step position (-1000 to 1000)

        Raises:
            ValueError: If position is out of valid range
            DeviceError: If movement fails
        """
        # Validate position range
        if position < self.MIN_POSITION or position > self.MAX_POSITION:
            raise ValueError(
                f"Position {position} is out of range "
                f"[{self.MIN_POSITION}, {self.MAX_POSITION}]"
            )

        command = f"SBm{position}"
        self.logger.info(f"Moving shadowband to position {position}")

        response = self._send_command(command)
        self._check_response(response)

        self._position = position

    def move_to_angle(self, angle: float) -> None:
        """
        Move shadowband to specified angle.

        Args:
            angle: Target angle in degrees
        """
        position = shadowband_angle_to_position(
            angle,
            self._resolution,
            self._ratio,
        )
        self.move_to_position(position)

    def move_relative(self, delta_steps: int) -> None:
        """
        Move shadowband relative to current position.

        Args:
            delta_steps: Steps to move (positive or negative)
        """
        new_position = self._position + delta_steps
        self.move_to_position(new_position)

    def reset(self) -> None:
        """
        Reset the shadowband to home position.

        Raises:
            DeviceError: If reset fails
        """
        self.logger.info("Resetting shadowband")

        response = self._send_command("SBr")
        self._check_response(response)

        self._position = 0

    def power_reset(self) -> None:
        """
        Perform a power reset on the shadowband.

        This sends a power cycle command through the head sensor.
        Use this when the shadowband is unresponsive or needs reinitialization.

        Raises:
            DeviceError: If power reset fails
        """
        self.logger.info("Power cycling shadowband")

        # Power reset command (same as reset with 's' suffix)
        response = self._send_command("SBs")
        self._check_response(response)

        self._position = 0
        self.logger.info("Shadowband power reset complete")

    def get_status(self) -> dict[str, Any]:
        """Get shadowband status."""
        return {
            "position": self._position,
            "angle": self.angle,
            "resolution": self._resolution,
            "ratio": self._ratio,
            "position_limits": (self.MIN_POSITION, self.MAX_POSITION),
        }

