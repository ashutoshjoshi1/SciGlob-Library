"""Filter Wheel control interface for SciGlob instruments."""

import logging
from typing import TYPE_CHECKING, Any, Optional

from sciglob.core.connection import parse_response
from sciglob.core.exceptions import FilterWheelError
from sciglob.core.help_mixin import HelpMixin
from sciglob.core.protocols import (
    VALID_FILTERS,
    get_error_message,
)

if TYPE_CHECKING:
    from sciglob.devices.head_sensor import HeadSensor


class FilterWheel(HelpMixin):
    """
    Filter Wheel controller interface.

    Controls filter wheel selection through the Head Sensor.
    Supports FW1 and FW2 with 9 positions each.

    Available Commands (from Firmware V7):
        Position Control:
        - set_position(1-9): Move to specific position
        - set_filter(name): Move to position by filter name
        - reset(): Reset to home position (OPEN)
        - move_to_mirror(): Move to mirror position

        Fine Movement:
        - move_forward(): Move forward by configured step count
        - move_backward(): Move backward by configured step count
        - move_forward_steps(n): Move forward by n steps
        - move_backward_steps(n): Move backward by n steps

        Calibration:
        - get_offset(): Read offset between mirror and home
        - set_offset(value): Set offset value (use 0 to reset)
        - save_offset(): Save current position as offset

        Testing:
        - test_movement(): Test movement in both directions

    Example:
        >>> with HeadSensor(port="/dev/ttyUSB0") as hs:
        ...     fw1 = hs.filter_wheel_1
        ...     # Set by position
        ...     fw1.set_position(5)
        ...     # Set by filter name
        ...     fw1.set_filter("OPEN")
        ...     # Get current filter
        ...     print(f"Current: {fw1.current_filter}")
        ...     # Fine adjustment
        ...     fw1.move_forward_steps(10)

    Help:
        >>> fw1.help()              # Show full help
        >>> fw1.list_methods()      # List all methods
    """

    # HelpMixin properties
    _device_name = "FilterWheel"
    _device_description = "Filter wheel controller (9 positions per wheel)"
    _supported_types = ["FW1", "FW2"]
    _default_config = {
        "positions": 9,
        "valid_filters": "OPEN, OPAQUE, U340, BP300, LPNIR, ND1-ND5, DIFF, etc.",
    }
    _command_reference = {
        "F*<1-9>": "Move to position 1-9",
        "F*r": "Reset to home (OPEN position)",
        "F*b": "Move backward by FWn steps",
        "F*B<n>": "Move backward by n integer steps",
        "F*f": "Move forward by FWn steps",
        "F*F<n>": "Move forward by n integer steps",
        "F*M": "Move to mirror position",
        "F*m": "Test movement (both directions)",
        "F*o": "Save current position as offset",
        "F*o?": "Read offset value",
        "F*o<n>": "Set offset value (0 to reset)",
    }

    def __init__(
        self,
        head_sensor: "HeadSensor",
        wheel_id: int = 1,
    ):
        """
        Initialize the Filter Wheel controller.

        Args:
            head_sensor: Connected HeadSensor instance
            wheel_id: Wheel identifier (1 for FW1, 2 for FW2)
        """
        if wheel_id not in (1, 2):
            raise ValueError("wheel_id must be 1 or 2")

        self._hs = head_sensor
        self._wheel_id = wheel_id
        self._device_id = f"F{wheel_id}"
        self.logger = logging.getLogger(f"sciglob.FilterWheel{wheel_id}")

        # Current position (1-9), 0 = unknown
        self._position: int = 0

    @property
    def wheel_id(self) -> int:
        """Get the wheel identifier (1 or 2)."""
        return self._wheel_id

    @property
    def device_id(self) -> str:
        """Get the device ID string (F1 or F2)."""
        return self._device_id

    @property
    def position(self) -> int:
        """Get the current position (1-9, or 0 if unknown)."""
        return self._position

    @property
    def filter_names(self) -> list[str]:
        """Get the list of filter names for this wheel."""
        if self._wheel_id == 1:
            return self._hs.fw1_filters
        else:
            return self._hs.fw2_filters

    @property
    def current_filter(self) -> Optional[str]:
        """Get the name of the current filter."""
        if self._position == 0:
            return None
        names = self.filter_names
        if 0 < self._position <= len(names):
            return names[self._position - 1]
        return None

    @property
    def num_positions(self) -> int:
        """Get the number of positions (always 9)."""
        return 9

    def _send_command(self, command: str, timeout: Optional[float] = None) -> str:
        """Send a command through the Head Sensor."""
        return self._hs.send_command(command, timeout)

    def _check_response(self, response: str) -> None:
        """
        Check response for errors.

        Raises:
            FilterWheelError: If response indicates an error
        """
        expected_prefix = self._device_id
        success, data, error_code = parse_response(response, expected_prefix)

        if not success and error_code is not None and error_code != 0:
            raise FilterWheelError(
                f"Filter wheel error: {get_error_message(error_code)}",
                error_code=error_code,
            )

    def set_position(self, position: int) -> None:
        """
        Set the filter wheel to a specific position.

        Args:
            position: Target position (1-9)

        Raises:
            ValueError: If position is invalid
            FilterWheelError: If movement fails
        """
        if position < 1 or position > 9:
            raise ValueError(f"Position must be 1-9, got {position}")

        command = f"{self._device_id}{position}"
        self.logger.info(f"Setting filter wheel {self._wheel_id} to position {position}")

        response = self._send_command(command)
        self._check_response(response)

        self._position = position
        self.logger.info(f"Filter wheel {self._wheel_id} now at position {position}")

    def set_filter(self, filter_name: str) -> None:
        """
        Set the filter wheel to the position containing the specified filter.

        Args:
            filter_name: Filter name (case-insensitive)

        Raises:
            FilterWheelError: If filter not found or movement fails
        """
        names = self.filter_names

        # Find the position for this filter name
        filter_name_lower = filter_name.lower()
        position = None

        for i, name in enumerate(names):
            if name.lower() == filter_name_lower:
                position = i + 1  # Positions are 1-indexed
                break

        if position is None:
            raise FilterWheelError(
                f"Filter '{filter_name}' not found in wheel {self._wheel_id}. "
                f"Available filters: {names}"
            )

        self.set_position(position)

    def reset(self) -> None:
        """
        Reset the filter wheel to its home position.

        The wheel will rotate to position 1 (home/OPEN).

        Raises:
            FilterWheelError: If reset fails
        """
        command = f"{self._device_id}r"
        self.logger.info(f"Resetting filter wheel {self._wheel_id}")

        response = self._send_command(command, timeout=10.0)
        self._check_response(response)

        self._position = 1  # Reset goes to position 1
        self.logger.info(f"Filter wheel {self._wheel_id} reset to position 1")

    def home(self) -> None:
        """
        Alias for reset() - move to home position.

        Raises:
            FilterWheelError: If reset fails
        """
        self.reset()

    def move_forward(self) -> None:
        """
        Move filter wheel forward by the configured step amount (FWn).

        Raises:
            FilterWheelError: If movement fails
        """
        command = f"{self._device_id}f"
        self.logger.debug(f"Moving filter wheel {self._wheel_id} forward")

        response = self._send_command(command)
        self._check_response(response)
        self._position = 0  # Position now unknown

    def move_backward(self) -> None:
        """
        Move filter wheel backward by the configured step amount (FWn).

        Raises:
            FilterWheelError: If movement fails
        """
        command = f"{self._device_id}b"
        self.logger.debug(f"Moving filter wheel {self._wheel_id} backward")

        response = self._send_command(command)
        self._check_response(response)
        self._position = 0  # Position now unknown

    def move_forward_steps(self, steps: int) -> None:
        """
        Move filter wheel forward by a specific number of steps.

        Args:
            steps: Number of steps to move forward

        Raises:
            FilterWheelError: If movement fails
        """
        if steps < 0:
            raise ValueError("Steps must be positive (use move_backward_steps for reverse)")

        command = f"{self._device_id}F{steps}"
        self.logger.debug(f"Moving filter wheel {self._wheel_id} forward {steps} steps")

        response = self._send_command(command)
        self._check_response(response)
        self._position = 0  # Position now unknown

    def move_backward_steps(self, steps: int) -> None:
        """
        Move filter wheel backward by a specific number of steps.

        Args:
            steps: Number of steps to move backward

        Raises:
            FilterWheelError: If movement fails
        """
        if steps < 0:
            raise ValueError("Steps must be positive")

        command = f"{self._device_id}B{steps}"
        self.logger.debug(f"Moving filter wheel {self._wheel_id} backward {steps} steps")

        response = self._send_command(command)
        self._check_response(response)
        self._position = 0  # Position now unknown

    def move_to_mirror(self) -> None:
        """
        Move filter wheel to the mirror position.

        Raises:
            FilterWheelError: If movement fails
        """
        command = f"{self._device_id}M"
        self.logger.info(f"Moving filter wheel {self._wheel_id} to mirror position")

        response = self._send_command(command)
        self._check_response(response)
        self._position = 0  # Mirror position is not a numbered position

    def test_movement(self) -> None:
        """
        Test filter wheel movement in both directions.

        This command moves the wheel forward and backward to verify
        proper operation.

        Raises:
            FilterWheelError: If test fails
        """
        command = f"{self._device_id}m"
        self.logger.info(f"Testing filter wheel {self._wheel_id} movement")

        response = self._send_command(command, timeout=5.0)
        self._check_response(response)

    def get_offset(self) -> int:
        """
        Read the offset value between mirror and home position.

        Returns:
            Offset value as integer

        Raises:
            FilterWheelError: If query fails
        """
        command = f"{self._device_id}o?"
        response = self._send_command(command)

        # Parse response: F1!<value> or F2!<value>
        if "!" in response:
            try:
                value_str = response.split("!")[1].strip()
                return int(value_str)
            except (IndexError, ValueError) as e:
                raise FilterWheelError(f"Failed to parse offset response: {response}") from e

        self._check_response(response)
        return 0

    def set_offset(self, value: int) -> None:
        """
        Set the offset value between mirror and home position.

        Args:
            value: New offset value (use 0 to reset)

        Raises:
            FilterWheelError: If setting fails
        """
        command = f"{self._device_id}o{value}"
        self.logger.info(f"Setting filter wheel {self._wheel_id} offset to {value}")

        response = self._send_command(command)
        self._check_response(response)

    def save_offset(self) -> None:
        """
        Save current position as the offset position.

        This sets the current physical position as the reference offset
        for the mirror position.

        Raises:
            FilterWheelError: If save fails
        """
        command = f"{self._device_id}o"
        self.logger.info(f"Saving filter wheel {self._wheel_id} offset position")

        response = self._send_command(command)
        self._check_response(response)

    def get_filter_map(self) -> dict[int, str]:
        """
        Get mapping of positions to filter names.

        Returns:
            Dictionary {position: filter_name}
        """
        names = self.filter_names
        return {i + 1: name for i, name in enumerate(names)}

    def get_position_for_filter(self, filter_name: str) -> Optional[int]:
        """
        Get the position for a specific filter name.

        Args:
            filter_name: Filter name to look up

        Returns:
            Position (1-9) or None if not found
        """
        names = self.filter_names
        filter_name_lower = filter_name.lower()

        for i, name in enumerate(names):
            if name.lower() == filter_name_lower:
                return i + 1

        return None

    def get_available_filters(self) -> list[str]:
        """
        Get list of all configured filter names.

        Returns:
            List of filter names
        """
        return self.filter_names.copy()

    def is_valid_filter(self, filter_name: str) -> bool:
        """
        Check if a filter name is valid (in the global valid list).

        Args:
            filter_name: Filter name to check

        Returns:
            True if valid
        """
        return filter_name.upper() in [f.upper() for f in VALID_FILTERS]

    def get_status(self) -> dict[str, Any]:
        """
        Get filter wheel status.

        Returns:
            Dictionary with status information
        """
        return {
            "wheel_id": self._wheel_id,
            "device_id": self._device_id,
            "position": self._position,
            "current_filter": self.current_filter,
            "filter_map": self.get_filter_map(),
        }

    def __repr__(self) -> str:
        current = self.current_filter or "Unknown"
        return f"<FilterWheel{self._wheel_id}(position={self._position}, filter={current})>"
