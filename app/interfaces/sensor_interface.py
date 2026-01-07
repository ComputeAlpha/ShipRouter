"""
Sensor Interface
Handles fuel sensor data parsing and management
"""

import logging
from datetime import datetime
from typing import Optional

from .base import BaseSensorInterface, SensorData
from ..config import FuelStatus

logger = logging.getLogger(__name__)


class SensorInterface(BaseSensorInterface):
    """
    Sensor Interface implementation for fuel level sensor.
    Handles binary fuel status (1 = normal, 0 = low).
    """
    
    def __init__(self):
        self._current_data: Optional[SensorData] = None
        self._last_update: Optional[datetime] = None
    
    def parse_fuel_status(self, raw_value: int) -> SensorData:
        """
        Parse raw fuel status value from Arduino.
        
        Args:
            raw_value: Integer fuel status (1 = normal, 0 = low)
        
        Returns:
            SensorData object with parsed status
        """
        # Validate and normalize the value
        if raw_value not in (0, 1):
            logger.warning(f"Invalid fuel status value: {raw_value}, defaulting to LOW")
            fuel_status = FuelStatus.LOW
        else:
            fuel_status = raw_value
        
        timestamp = datetime.now()
        
        self._current_data = SensorData(
            fuel_status=fuel_status,
            timestamp=timestamp,
            raw_data=str(raw_value)
        )
        self._last_update = timestamp
        
        return self._current_data
    
    def get_current_status(self) -> Optional[SensorData]:
        """
        Get the latest sensor status.
        
        Returns:
            SensorData object or None if no data received yet
        """
        return self._current_data
    
    def reset(self) -> None:
        """Reset sensor data to default state"""
        self._current_data = None
        self._last_update = None
    
    @property
    def last_update(self) -> Optional[datetime]:
        """Get timestamp of last successful update"""
        return self._last_update
    
    @property
    def is_fuel_normal(self) -> bool:
        """Check if fuel level is normal"""
        if self._current_data is None:
            return True  # Assume normal if no data
        return self._current_data.fuel_status == FuelStatus.NORMAL
    
    @property
    def is_fuel_low(self) -> bool:
        """Check if fuel level is low"""
        if self._current_data is None:
            return False  # Assume not low if no data
        return self._current_data.fuel_status == FuelStatus.LOW