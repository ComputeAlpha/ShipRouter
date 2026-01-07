"""
Abstract Base Classes for Hardware Interfaces
These define contracts that concrete implementations must follow.
Allows swapping hardware without changing core logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class GPSData:
    """Standardized GPS data structure"""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_knots: Optional[float] = None
    heading: Optional[float] = None
    altitude_m: Optional[float] = None
    fix_quality: int = 0  # 0 = no fix, 1 = GPS fix, 2 = DGPS fix
    satellites: int = 0
    timestamp: Optional[datetime] = None
    raw_nmea: str = ""
    
    @property
    def is_valid(self) -> bool:
        """Check if GPS data has a valid fix"""
        return (
            self.latitude is not None 
            and self.longitude is not None 
            and self.fix_quality > 0
        )


@dataclass
class SensorData:
    """Standardized sensor data structure"""
    fuel_status: int  # 1 = normal, 0 = low
    timestamp: datetime
    raw_data: str = ""
    
    @property
    def is_fuel_low(self) -> bool:
        return self.fuel_status == 0


@dataclass
class CombinedData:
    """Combined data from serial port (Arduino sends both)"""
    sensor: Optional[SensorData] = None
    gps: Optional[GPSData] = None
    parse_error: Optional[str] = None


class BaseGPSInterface(ABC):
    """Abstract GPS Interface"""
    
    @abstractmethod
    def parse_nmea(self, nmea_sentence: str) -> GPSData:
        """Parse NMEA sentence and return GPSData"""
        pass
    
    @abstractmethod
    def get_current_position(self) -> Optional[GPSData]:
        """Get the latest GPS position"""
        pass


class BaseSensorInterface(ABC):
    """Abstract Sensor Interface"""
    
    @abstractmethod
    def parse_fuel_status(self, raw_value: int) -> SensorData:
        """Parse raw fuel status value"""
        pass
    
    @abstractmethod
    def get_current_status(self) -> Optional[SensorData]:
        """Get the latest sensor status"""
        pass


class BaseSerialInterface(ABC):
    """Abstract Serial Communication Interface"""
    
    @abstractmethod
    def connect(self) -> bool:
        """Establish serial connection"""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close serial connection"""
        pass
    
    @abstractmethod
    def read_data(self) -> Optional[CombinedData]:
        """Read and parse incoming data"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if serial port is connected"""
        pass