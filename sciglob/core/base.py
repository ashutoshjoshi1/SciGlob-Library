"""Abstract base classes for all SciGlob devices."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseDevice(ABC):
    """
    Abstract base class for all controllable devices.

    Provides common interface for connection management,
    communication, and resource cleanup.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 1.0,
        name: Optional[str] = None,
    ):
        """
        Initialize the base device.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0' or 'COM3')
            baudrate: Communication baud rate
            timeout: Read/write timeout in seconds
            name: Optional device name for logging
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.name = name or self.__class__.__name__
        self._connected = False
        self._connection: Any = None

        # Set up logging
        self.logger = logging.getLogger(f"sciglob.{self.name}")

    @property
    def is_connected(self) -> bool:
        """Check if the device is currently connected."""
        return self._connected

    @abstractmethod
    def connect(self) -> None:
        """
        Establish connection to the device.

        Raises:
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """
        Close connection to the device.

        Should be safe to call even if not connected.
        """
        pass

    @abstractmethod
    def send_command(self, command: str) -> Optional[str]:
        """
        Send a command to the device.

        Args:
            command: Command string to send

        Returns:
            Response from device, or None if no response expected

        Raises:
            DeviceError: If command fails
            TimeoutError: If response times out
        """
        pass

    def __enter__(self) -> "BaseDevice":
        """Context manager entry - connect to device."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - disconnect from device."""
        self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"<{self.name}(port={self.port}, {status})>"
