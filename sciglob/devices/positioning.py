"""GPS/Positioning system interfaces."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import logging
from sciglob.core.base import BaseDevice
from sciglob.core.connection import SerialConnection
from sciglob.core.protocols import SerialConfig, GPS_PROTOCOL, TIMING_CONFIG
from sciglob.core.exceptions import ConnectionError, DeviceError
from sciglob.core.utils import nmea_to_decimal
from sciglob.core.help_mixin import HelpMixin


class PositioningSystem(BaseDevice, ABC, HelpMixin):
    """
    Abstract base class for GPS/positioning systems.
    
    Supported systems:
    - GlobalSat: Simple GPS receiver
    - Novatel: GPS + Gyroscope for orientation sensing
    """
    
    # HelpMixin properties
    _device_name = "PositioningSystem"
    _device_description = "GPS/Positioning system base class"
    _supported_types = ["GlobalSat", "Novatel"]
    _default_config = {
        "baudrate": 9600,
    }

    @abstractmethod
    def get_position(self) -> Dict[str, Any]:
        """
        Get current position.
        
        Returns:
            Dictionary with latitude, longitude, altitude, etc.
        """
        pass

    @abstractmethod
    def configure(self) -> bool:
        """Configure the device for operation."""
        pass


class GlobalSatGPS(PositioningSystem):
    """
    GlobalSat GPS receiver interface.
    
    Uses NMEA protocol with GPGGA messages for position data.
    
    Example:
        >>> gps = GlobalSatGPS(port="/dev/ttyUSB0")
        >>> gps.connect()
        >>> position = gps.get_position()
        >>> print(f"Lat: {position['latitude']}, Lon: {position['longitude']}")
        >>> gps.disconnect()
        
    Help:
        >>> gps.help()              # Show full help
    """
    
    # HelpMixin properties
    _device_name = "GlobalSatGPS"
    _device_description = "GlobalSat GPS receiver (NMEA GPGGA protocol)"
    _supported_types = ["GlobalSat"]
    _default_config = {
        "baudrate": 9600,
        "protocol": "NMEA 0183",
        "message_type": "GPGGA",
    }
    _command_reference = {
        "GPGGA": "Position fix data (lat, lon, alt, quality, satellites)",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 2.0,
        name: str = "GlobalSatGPS",
        config: Optional['GPSConfig'] = None,
        serial_config: Optional[SerialConfig] = None,
    ):
        """
        Initialize the GlobalSat GPS.
        
        Args:
            port: Serial port path
            baudrate: Communication speed (default 9600)
            timeout: Command timeout
            name: Device name for logging
            config: GPSConfig object
            serial_config: SerialConfig object for port settings
        """
        # If config object provided, use its values
        if config is not None:
            port = config.serial.port or port
            baudrate = config.serial.baudrate
            timeout = config.serial.timeout or timeout
        
        # If serial_config provided, use its values
        if serial_config is not None:
            port = serial_config.port or port
            baudrate = serial_config.baudrate
            timeout = serial_config.timeout or timeout
        
        super().__init__(port=port, baudrate=baudrate, timeout=timeout, name=name)
        self._protocol = GPS_PROTOCOL["GlobalSat"]
        self._configured = False

    def connect(self) -> None:
        """Connect to the GPS receiver."""
        if self._connected:
            self.logger.warning("Already connected")
            return
            
        if self.port is None:
            raise ConnectionError("No port specified")
            
        try:
            config = SerialConfig(baudrate=self.baudrate)
            self._connection = SerialConnection(port=self.port, config=config)
            self._connection.open()
            
            # Configure device
            self.configure()
            
            self._connected = True
            self.logger.info(f"Connected to GlobalSat GPS on {self.port}")
            
        except Exception as e:
            self.disconnect()
            raise ConnectionError(f"Failed to connect: {e}") from e

    def disconnect(self) -> None:
        """Disconnect from the GPS receiver."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
            finally:
                self._connection = None
                self._connected = False
                self._configured = False

    def _query(self, command: str) -> str:
        """Send command and get response."""
        if self._connection is None:
            raise DeviceError("Not connected")
            
        end_char = self._protocol["end_char"]
        response_end = self._protocol["response_end_char"]
        
        self._connection.send_command(command, end_char="")  # Command includes end char
        
        response = self._connection.read_until(
            terminator=response_end.encode(),
            timeout=self.timeout,
        )
        
        return response.decode().strip()

    def send_command(self, command: str) -> Optional[str]:
        """Send raw command."""
        return self._query(command)

    def configure(self) -> bool:
        """
        Configure the GPS by disabling automatic messages.
        
        Returns:
            True if successful
        """
        commands = self._protocol["commands"]
        
        try:
            # Disable automatic NMEA messages
            for cmd_name in ["disable_rmc", "disable_gsa", "disable_gsv", "disable_gga"]:
                cmd = commands[cmd_name]
                self._connection.send_command(cmd + "\r\n", end_char="")
                # Small delay between commands
                import time
                time.sleep(0.2)
                
            self._configured = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to configure GPS: {e}")
            return False

    def get_position(self) -> Dict[str, Any]:
        """
        Get current GPS position.
        
        Returns:
            Dictionary with:
            - latitude: Decimal degrees (+ = North)
            - longitude: Decimal degrees (+ = East)
            - altitude: Meters above sea level
            - quality: GPS fix quality (0 = no fix)
            - satellites: Number of satellites
        """
        if not self._connected:
            raise DeviceError("Not connected")
            
        # Query GGA message
        query_cmd = self._protocol["commands"]["query_gga"]
        
        self._connection.flush_buffers()
        self._connection.send_command(query_cmd + "\r\n", end_char="")
        
        # Read response
        import time
        time.sleep(1.0)
        
        response = self._connection.read_until(
            terminator=b"\r\n",
            timeout=self.timeout,
            max_bytes=256,
        ).decode()
        
        return self._parse_gpgga(response)

    def _parse_gpgga(self, response: str) -> Dict[str, Any]:
        """
        Parse GPGGA NMEA message.
        
        Format: $GPGGA,time,lat,N/S,lon,E/W,quality,sats,hdop,alt,M,geoid,M,age,refid*checksum
        """
        result = {
            "latitude": 0.0,
            "longitude": 0.0,
            "altitude": 0.0,
            "quality": 0,
            "satellites": 0,
            "raw": response,
        }
        
        if "$GPGGA" not in response:
            result["error"] = "No GPGGA message received"
            return result
            
        try:
            # Extract GPGGA data
            gga_start = response.index("$GPGGA")
            gga_line = response[gga_start:].split("\r")[0].split("\n")[0]
            
            # Remove checksum
            if "*" in gga_line:
                gga_line = gga_line[:gga_line.index("*")]
                
            parts = gga_line.split(",")
            
            if len(parts) >= 10:
                # Quality (field 6)
                quality = int(parts[6]) if parts[6] else 0
                result["quality"] = quality
                
                if quality > 0:
                    # Latitude (fields 2, 3)
                    if parts[2] and parts[3]:
                        result["latitude"] = nmea_to_decimal(parts[2], parts[3])
                        
                    # Longitude (fields 4, 5)
                    if parts[4] and parts[5]:
                        result["longitude"] = nmea_to_decimal(parts[4], parts[5])
                        
                    # Altitude (field 9)
                    if parts[9]:
                        result["altitude"] = float(parts[9])
                        
                    # Satellites (field 7)
                    if parts[7]:
                        result["satellites"] = int(parts[7])
                else:
                    result["error"] = "No GPS fix"
                    
        except Exception as e:
            result["error"] = f"Parse error: {e}"
            
        return result

    def get_status(self) -> Dict[str, Any]:
        """Get GPS status."""
        status = {
            "connected": self._connected,
            "configured": self._configured,
            "port": self.port,
        }
        
        if self._connected:
            try:
                status["position"] = self.get_position()
            except Exception as e:
                status["error"] = str(e)
                
        return status


class NovatelGPS(PositioningSystem):
    """
    Novatel GPS + Gyroscope interface.
    
    Provides position and orientation (roll, pitch, yaw) data
    using the INSPVA message format.
    
    Example:
        >>> gps = NovatelGPS(port="/dev/ttyUSB0")
        >>> gps.connect()
        >>> position = gps.get_position()
        >>> orientation = gps.get_orientation()
        >>> print(f"Yaw: {orientation['yaw']}°")
        >>> gps.disconnect()
        
    Help:
        >>> gps.help()              # Show full help
    """
    
    # HelpMixin properties
    _device_name = "NovatelGPS"
    _device_description = "Novatel GPS + Gyroscope for position and orientation"
    _supported_types = ["Novatel"]
    _default_config = {
        "baudrate": 9600,
        "protocol": "INSPVA",
    }
    _command_reference = {
        "INSPVA": "Position + orientation (lat, lon, alt, roll, pitch, yaw)",
        "unlogall": "Clear all logs",
        "log inspvaa ontime 1": "Start logging at 1Hz",
    }

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 2.0,
        name: str = "NovatelGPS",
        config: Optional['GPSConfig'] = None,
        serial_config: Optional[SerialConfig] = None,
    ):
        """
        Initialize the Novatel GPS.
        
        Args:
            port: Serial port path
            baudrate: Communication speed (default 9600)
            timeout: Command timeout
            name: Device name for logging
            config: GPSConfig object
            serial_config: SerialConfig object for port settings
        """
        # If config object provided, use its values
        if config is not None:
            port = config.serial.port or port
            baudrate = config.serial.baudrate
            timeout = config.serial.timeout or timeout
        
        # If serial_config provided, use its values
        if serial_config is not None:
            port = serial_config.port or port
            baudrate = serial_config.baudrate
            timeout = serial_config.timeout or timeout
        
        super().__init__(port=port, baudrate=baudrate, timeout=timeout, name=name)
        self._protocol = GPS_PROTOCOL["Novatel"]
        self._configured = False
        self._last_inspva: Optional[Dict] = None

    def connect(self) -> None:
        """Connect to the Novatel system."""
        if self._connected:
            self.logger.warning("Already connected")
            return
            
        if self.port is None:
            raise ConnectionError("No port specified")
            
        try:
            config = SerialConfig(baudrate=self.baudrate)
            self._connection = SerialConnection(port=self.port, config=config)
            self._connection.open()
            
            # Configure device
            self.configure()
            
            self._connected = True
            self.logger.info(f"Connected to Novatel on {self.port}")
            
        except Exception as e:
            self.disconnect()
            raise ConnectionError(f"Failed to connect: {e}") from e

    def disconnect(self) -> None:
        """Disconnect from the Novatel system."""
        if self._connection is not None:
            try:
                # Stop logging
                self.stop_logging()
            except:
                pass
                
            try:
                self._connection.close()
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
            finally:
                self._connection = None
                self._connected = False

    def _send_command(self, command: str) -> str:
        """Send command and get response."""
        if self._connection is None:
            raise DeviceError("Not connected")
            
        end_char = self._protocol["end_char"]
        response_end = self._protocol["response_end_char"]
        
        self._connection.send_command(command, end_char=end_char)
        
        response = self._connection.read_until(
            terminator=response_end.encode(),
            timeout=self.timeout,
            max_bytes=1024,
        )
        
        return response.decode().strip()

    def send_command(self, command: str) -> Optional[str]:
        """Send raw command."""
        return self._send_command(command)

    def configure(self) -> bool:
        """
        Configure the Novatel by clearing existing logs.
        
        Returns:
            True if successful
        """
        try:
            clear_cmd = self._protocol["commands"]["clear_logs"]
            self._send_command(clear_cmd)
            self._configured = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to configure Novatel: {e}")
            return False

    def start_logging(self, interval: float = 1.0) -> bool:
        """
        Start continuous INSPVA logging.
        
        Args:
            interval: Logging interval in seconds
            
        Returns:
            True if successful
        """
        try:
            cmd = self._protocol["commands"]["start_logging"].format(interval=int(interval))
            self._send_command(cmd)
            return True
        except Exception as e:
            self.logger.error(f"Failed to start logging: {e}")
            return False

    def stop_logging(self) -> bool:
        """
        Stop INSPVA logging.
        
        Returns:
            True if successful
        """
        try:
            self._send_command(self._protocol["commands"]["clear_logs"])
            return True
        except Exception:
            return False

    def read_inspva(self) -> Optional[Dict[str, Any]]:
        """
        Read single INSPVA message.
        
        Returns:
            Parsed INSPVA data or None if failed
        """
        try:
            # Request single reading
            cmd = self._protocol["commands"]["read_once"]
            response = self._send_command(cmd)
            
            # Wait for INSPVA data
            import time
            time.sleep(0.5)
            
            # Read additional data
            more_data = self._connection.read_until(
                terminator=b"\n",
                timeout=2.0,
                max_bytes=512,
            ).decode()
            
            full_response = response + more_data
            
            return self._parse_inspva(full_response)
        except Exception as e:
            self.logger.error(f"Failed to read INSPVA: {e}")
            return None

    def _parse_inspva(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Parse INSPVA message.
        
        Format: <INSPVA ... week seconds lat lon alt vn ve vu roll pitch yaw status
        """
        result = {
            "latitude": 0.0,
            "longitude": 0.0,
            "altitude": 0.0,
            "velocity_north": 0.0,
            "velocity_east": 0.0,
            "velocity_up": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "status": "UNKNOWN",
        }
        
        if "INSPVA" not in response:
            return None
            
        try:
            # Find the data line (starts with "<")
            for line in response.split("\n"):
                line = line.strip()
                if line.startswith("<") and "INSPVA" not in line:
                    parts = line.split()
                    
                    if len(parts) >= 12:
                        # week = parts[1]
                        # seconds = parts[2]
                        result["latitude"] = float(parts[3])
                        result["longitude"] = float(parts[4])
                        result["altitude"] = float(parts[5])
                        result["velocity_north"] = float(parts[6])
                        result["velocity_east"] = float(parts[7])
                        result["velocity_up"] = float(parts[8])
                        result["roll"] = float(parts[9])
                        result["pitch"] = float(parts[10])
                        result["yaw"] = float(parts[11])
                        
                        if len(parts) >= 13:
                            result["status"] = parts[12]
                            
                        break
                        
            self._last_inspva = result
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to parse INSPVA: {e}")
            return None

    def get_position(self) -> Dict[str, Any]:
        """
        Get current GPS position.
        
        Returns:
            Dictionary with latitude, longitude, altitude
        """
        inspva = self.read_inspva()
        
        if inspva is None:
            inspva = self._last_inspva or {}
            inspva["error"] = "No INSPVA data available"
            
        return {
            "latitude": inspva.get("latitude", 0.0),
            "longitude": inspva.get("longitude", 0.0),
            "altitude": inspva.get("altitude", 0.0),
            "status": inspva.get("status", "UNKNOWN"),
        }

    def get_orientation(self) -> Dict[str, float]:
        """
        Get current orientation from gyroscope.
        
        Returns:
            Dictionary with roll, pitch, yaw in degrees
        """
        inspva = self.read_inspva()
        
        if inspva is None:
            inspva = self._last_inspva or {}
            
        return {
            "roll": inspva.get("roll", 0.0),
            "pitch": inspva.get("pitch", 0.0),
            "yaw": inspva.get("yaw", 0.0),
        }

    def get_status(self) -> Dict[str, Any]:
        """Get Novatel status."""
        status = {
            "connected": self._connected,
            "configured": self._configured,
            "port": self.port,
        }
        
        if self._connected:
            try:
                inspva = self.read_inspva()
                if inspva:
                    status["position"] = {
                        "latitude": inspva["latitude"],
                        "longitude": inspva["longitude"],
                        "altitude": inspva["altitude"],
                    }
                    status["orientation"] = {
                        "roll": inspva["roll"],
                        "pitch": inspva["pitch"],
                        "yaw": inspva["yaw"],
                    }
                    status["ins_status"] = inspva["status"]
            except Exception as e:
                status["error"] = str(e)
                
        return status

