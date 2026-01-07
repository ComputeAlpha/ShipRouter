"""
Hardware Interfaces Package
Abstractions for GPS, Sensor, and Serial communication
"""

from .base import (
    GPSData,
    SensorData,
    CombinedData,
    BaseGPSInterface,
    BaseSensorInterface,
    BaseSerialInterface
)
from .gps_interface import GPSInterface
from .sensor_interface import SensorInterface
from .serial_interface import SerialInterface

__all__ = [
    # Data classes
    'GPSData',
    'SensorData', 
    'CombinedData',
    # Base classes
    'BaseGPSInterface',
    'BaseSensorInterface',
    'BaseSerialInterface',
    # Implementations
    'GPSInterface',
    'SensorInterface',
    'SerialInterface'
]