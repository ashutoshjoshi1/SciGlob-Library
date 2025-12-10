"""Configuration settings management."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from sciglob.core.exceptions import ConfigurationError


@dataclass
class SerialSettings:
    """Serial port configuration."""

    port: Optional[str] = None
    baudrate: int = 9600
    timeout: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SerialSettings":
        return cls(
            port=data.get("port"),
            baudrate=data.get("baudrate", 9600),
            timeout=data.get("timeout", 1.0),
        )


@dataclass
class MotorSettings:
    """Motor configuration settings."""

    serial: SerialSettings = field(default_factory=SerialSettings)
    min_position: float = 0.0
    max_position: float = 360.0
    home_position: float = 0.0
    steps_per_degree: float = 100.0
    slave_id: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MotorSettings":
        serial_data = {
            "port": data.get("port"),
            "baudrate": data.get("baudrate", 115200),
            "timeout": data.get("timeout", 2.0),
        }
        return cls(
            serial=SerialSettings.from_dict(serial_data),
            min_position=data.get("min_position", 0.0),
            max_position=data.get("max_position", 360.0),
            home_position=data.get("home_position", 0.0),
            steps_per_degree=data.get("steps_per_degree", 100.0),
            slave_id=data.get("slave_id", 1),
        )


@dataclass
class FilterSettings:
    """Filter configuration."""

    position: int
    name: str
    wavelength: Optional[float] = None
    bandwidth: Optional[float] = None


@dataclass
class FilterWheelSettings:
    """Filter wheel configuration."""

    num_positions: int = 6
    filters: list[FilterSettings] = field(default_factory=list)
    home_position: int = 1


@dataclass
class SensorHeadSettings:
    """Sensor head configuration."""

    serial: SerialSettings = field(default_factory=SerialSettings)
    filter_wheel: FilterWheelSettings = field(default_factory=FilterWheelSettings)


@dataclass
class Settings:
    """
    Main settings container for SciGlob configuration.

    Can be loaded from YAML/JSON files or created programmatically.

    Example:
        >>> settings = Settings.from_yaml("config.yaml")
        >>> print(settings.motors.azimuth.serial.port)
    """

    sensor_head: SensorHeadSettings = field(default_factory=SensorHeadSettings)
    azimuth: MotorSettings = field(default_factory=MotorSettings)
    zenith: MotorSettings = field(default_factory=MotorSettings)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        """Create settings from dictionary."""
        settings = cls()

        # Load sensor head settings
        if "sensor_head" in data:
            sh_data = data["sensor_head"]
            settings.sensor_head.serial = SerialSettings.from_dict(sh_data)

        # Load motor settings
        motors = data.get("motors", {})
        if "azimuth" in motors:
            settings.azimuth = MotorSettings.from_dict(motors["azimuth"])
        if "zenith" in motors:
            settings.zenith = MotorSettings.from_dict(motors["zenith"])

        return settings

    @classmethod
    def from_yaml(cls, path: str) -> "Settings":
        """
        Load settings from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            Settings instance

        Raises:
            ConfigurationError: If file cannot be loaded
        """
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            return cls.from_dict(data or {})
        except FileNotFoundError as e:
            raise ConfigurationError(f"Configuration file not found: {path}") from e
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in {path}: {e}") from e

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            "sensor_head": {
                "port": self.sensor_head.serial.port,
                "baudrate": self.sensor_head.serial.baudrate,
                "timeout": self.sensor_head.serial.timeout,
            },
            "motors": {
                "azimuth": {
                    "port": self.azimuth.serial.port,
                    "baudrate": self.azimuth.serial.baudrate,
                    "min_position": self.azimuth.min_position,
                    "max_position": self.azimuth.max_position,
                },
                "zenith": {
                    "port": self.zenith.serial.port,
                    "baudrate": self.zenith.serial.baudrate,
                    "min_position": self.zenith.min_position,
                    "max_position": self.zenith.max_position,
                },
            },
        }

    def save_yaml(self, path: str) -> None:
        """Save settings to YAML file."""
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)


def load_config(path: Optional[str] = None) -> Settings:
    """
    Load configuration from file or return defaults.

    Args:
        path: Optional path to config file. If None, returns defaults.

    Returns:
        Settings instance
    """
    if path is None:
        return Settings()

    path_obj = Path(path)

    if not path_obj.exists():
        # Return defaults if file doesn't exist
        return Settings()

    if path_obj.suffix in (".yaml", ".yml"):
        return Settings.from_yaml(str(path_obj))
    else:
        raise ConfigurationError(f"Unsupported config format: {path_obj.suffix}")
