"""Shadowband control interface for SciGlob instruments."""

from typing import Optional, Dict, Any, TYPE_CHECKING
import logging
from sciglob.core.protocols import SHADOWBAND_COMMANDS, get_error_message
from sciglob.core.exceptions import DeviceError
from sciglob.core.connection import parse_response
from sciglob.core.utils import shadowband_angle_to_position, position_to_shadowband_angle

if TYPE_CHECKING:
    from sciglob.devices.head_sensor import HeadSensor


class Shadowband:
    """
    Shadowband controller interface.
    
    Controls the shadowband arm position through the Head Sensor.
    
    Commands:
    - Move: "SBm<position>" - Move to step position
    - Reset: "SBr" - Reset shadowband
    - Response: "SB0" (success) or "SB<N>" (error code N)
    
    Example:
        >>> with HeadSensor(port="/dev/ttyUSB0") as hs:
        ...     sb = hs.shadowband
        ...     sb.move_to_position(500)
        ...     sb.move_to_angle(45.0)
        ...     sb.reset()
    """

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
            position: Target step position
        """
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
        """
        self.logger.info("Resetting shadowband")
        
        response = self._send_command("SBr")
        self._check_response(response)
        
        self._position = 0

    def get_status(self) -> Dict[str, Any]:
        """Get shadowband status."""
        return {
            "position": self._position,
            "angle": self.angle,
            "resolution": self._resolution,
            "ratio": self._ratio,
        }

