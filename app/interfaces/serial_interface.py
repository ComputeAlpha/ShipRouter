"""
Serial Interface
Handles unified serial communication with Arduino.
Parses combined JSON format: {"fuel": 0|1, "nmea": "..."}
"""

import json
import logging
import threading
from datetime import datetime
from typing import Optional, Callable

import serial
from serial.tools import list_ports

from .base import BaseSerialInterface, CombinedData
from .gps_interface import GPSInterface
from .sensor_interface import SensorInterface
from ..config import SERIAL_PORT, SERIAL_BAUDRATE, SERIAL_TIMEOUT

logger = logging.getLogger(__name__)


class SerialInterface(BaseSerialInterface):
    """
    Unified Serial Interface for Arduino communication.
    Handles combined JSON packets containing fuel status and NMEA data.
    
    Expected JSON format: {"fuel": 0|1, "nmea": "$GPGGA,..."}
    """
    
    def __init__(
        self,
        port: str = SERIAL_PORT,
        baudrate: int = SERIAL_BAUDRATE,
        timeout: float = SERIAL_TIMEOUT
    ):
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        
        self._serial: Optional[serial.Serial] = None
        self._connected = False
        self._lock = threading.Lock()
        
        # Sub-interfaces for parsing
        self._gps_interface = GPSInterface()
        self._sensor_interface = SensorInterface()
        
        # Callbacks for data updates
        self._on_data_callback: Optional[Callable[[CombinedData], None]] = None
        
        # Statistics
        self._packets_received = 0
        self._parse_errors = 0
    
    def connect(self) -> bool:
        """
        Establish serial connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        with self._lock:
            if self._connected:
                return True
            
            try:
                self._serial = serial.Serial(
                    port=self._port,
                    baudrate=self._baudrate,
                    timeout=self._timeout
                )
                self._connected = True
                logger.info(f"Serial connected: {self._port} @ {self._baudrate} baud")
                return True
                
            except serial.SerialException as e:
                logger.error(f"Serial connection failed: {e}")
                self._connected = False
                return False
    
    def disconnect(self) -> None:
        """Close serial connection"""
        with self._lock:
            if self._serial and self._serial.is_open:
                self._serial.close()
            self._connected = False
            logger.info("Serial disconnected")
    
    def is_connected(self) -> bool:
        """Check if serial port is connected"""
        with self._lock:
            return self._connected and self._serial is not None and self._serial.is_open
    
    def read_data(self) -> Optional[CombinedData]:
        """
        Read and parse incoming JSON data from Arduino.
        
        Expected format: {"fuel": 0|1, "nmea": "$GPGGA,..."}
        
        Returns:
            CombinedData object with parsed sensor and GPS data
        """
        if not self.is_connected():
            return CombinedData(parse_error="Serial not connected")
        
        try:
            with self._lock:
                if not self._serial.in_waiting:
                    return None
                
                line = self._serial.readline().decode('utf-8', errors='ignore').strip()
            
            if not line:
                return None
            
            return self._parse_json_packet(line)
            
        except serial.SerialException as e:
            logger.error(f"Serial read error: {e}")
            self._connected = False
            return CombinedData(parse_error=str(e))
        except Exception as e:
            logger.error(f"Unexpected read error: {e}")
            return CombinedData(parse_error=str(e))
    
    def _parse_json_packet(self, raw_line: str) -> CombinedData:
        """
        Parse JSON packet from Arduino.
        
        Args:
            raw_line: Raw JSON string
        
        Returns:
            CombinedData with parsed components
        """
        result = CombinedData()
        
        try:
            data = json.loads(raw_line)
            self._packets_received += 1
            
            # Parse fuel status
            if 'fuel' in data:
                fuel_value = int(data['fuel'])
                result.sensor = self._sensor_interface.parse_fuel_status(fuel_value)
            
            # Parse NMEA sentence
            if 'nmea' in data and data['nmea']:
                nmea_sentence = data['nmea']
                gps_data = self._gps_interface.parse_nmea(nmea_sentence)
                result.gps = gps_data
            
        except json.JSONDecodeError as e:
            self._parse_errors += 1
            result.parse_error = f"JSON parse error: {e}"
            logger.warning(f"JSON parse error: {e} for line: {raw_line}")
        except (KeyError, ValueError) as e:
            self._parse_errors += 1
            result.parse_error = f"Data format error: {e}"
            logger.warning(f"Data format error: {e}")
        
        # Trigger callback if set
        if self._on_data_callback and (result.sensor or result.gps):
            self._on_data_callback(result)
        
        return result
    
    def set_data_callback(self, callback: Callable[[CombinedData], None]) -> None:
        """Set callback function for data updates"""
        self._on_data_callback = callback
    
    @property
    def gps_interface(self) -> GPSInterface:
        """Access to GPS interface for direct queries"""
        return self._gps_interface
    
    @property
    def sensor_interface(self) -> SensorInterface:
        """Access to sensor interface for direct queries"""
        return self._sensor_interface
    
    @property
    def statistics(self) -> dict:
        """Get communication statistics"""
        return {
            "packets_received": self._packets_received,
            "parse_errors": self._parse_errors,
            "connected": self._connected,
            "port": self._port
        }
    
    @staticmethod
    def list_available_ports() -> list:
        """List all available serial ports"""
        ports = list_ports.comports()
        return [
            {
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid
            }
            for p in ports
        ]