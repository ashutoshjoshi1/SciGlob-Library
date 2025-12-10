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

    Commands:
    - Set position: "F1<1-9>" or "F2<1-9>"
    - Reset: "F1r" or "F2r"
    - Response: "F10" (success) or "F1N" (error code N)

    Example:
        >>> with HeadSensor(port="/dev/ttyUSB0") as hs:
        ...     fw1 = hs.filter_wheel_1
        ...     # Set by position
        ...     fw1.set_position(5)
        ...     # Set by filter name
        ...     fw1.set_filter("OPEN")
        ...     # Get current filter
        ...     print(f"Current: {fw1.current_filter}")

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
        "F1<1-9>": "Set filter wheel 1 to position 1-9",
        "F2<1-9>": "Set filter wheel 2 to position 1-9",
        "F1r": "Reset filter wheel 1",
        "F2r": "Reset filter wheel 2",
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

        The wheel will rotate to position 1 (home).

        Raises:
            FilterWheelError: If reset fails
        """
        command = f"{self._device_id}r"
        self.logger.info(f"Resetting filter wheel {self._wheel_id}")

        response = self._send_command(command)
        self._check_response(response)

        self._position = 1  # Reset goes to position 1
        self.logger.info(f"Filter wheel {self._wheel_id} reset to position 1")

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

