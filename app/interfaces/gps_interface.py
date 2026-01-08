"""
GPS Interface
Handles NMEA sentence parsing and GPS data management
"""

import logging
from datetime import datetime
from typing import Optional

import pynmea2

from .base import BaseGPSInterface, GPSData

logger = logging.getLogger(__name__)


class GPSInterface(BaseGPSInterface):
    """
    GPS Interface implementation using pynmea2 for NMEA parsing.
    Supports GPGGA, GPRMC, and GPVTG sentences.
    """
    
    def __init__(self):
        self._current_data = GPSData()
        self._last_update: Optional[datetime] = None
    
    def parse_nmea(self, nmea_sentence: str) -> GPSData:
        """
        Parse NMEA sentence and update internal GPS data.
        Merges data from different sentence types.
        
        Args:
            nmea_sentence: Raw NMEA sentence string (e.g., "$GPGGA,...")
        
        Returns:
            Updated GPSData object
        """
        if not nmea_sentence or not nmea_sentence.startswith('$'):
            return self._current_data
        
        try:
            # Try parsing with checksum validation
            msg = pynmea2.parse(nmea_sentence.strip())
            self._update_from_message(msg)
            self._current_data.raw_nmea = nmea_sentence
            self._last_update = datetime.now()
            
        except pynmea2.ChecksumError as e:
            # Log checksum errors but don't spam - common with noisy serial
            logger.debug(f"NMEA checksum error: {e}")
        except pynmea2.ParseError as e:
            logger.warning(f"NMEA parse error: {e} for sentence: {nmea_sentence}")
        except Exception as e:
            logger.error(f"Unexpected error parsing NMEA: {e}")
        
        return self._current_data
    
    def _update_from_message(self, msg) -> None:
        """Update internal data from parsed NMEA message"""
        
        # GGA - Global Positioning System Fix Data
        if isinstance(msg, pynmea2.GGA):
            self._parse_gga(msg)
        
        # RMC - Recommended Minimum Navigation Information
        elif isinstance(msg, pynmea2.RMC):
            self._parse_rmc(msg)
        
        # VTG - Track Made Good and Ground Speed
        elif isinstance(msg, pynmea2.VTG):
            self._parse_vtg(msg)
        
        # GLL - Geographic Position (Latitude/Longitude)
        elif isinstance(msg, pynmea2.GLL):
            self._parse_gll(msg)
    
    def _parse_gga(self, msg: pynmea2.GGA) -> None:
        """Parse GGA sentence for position and fix quality"""
        try:
            if msg.latitude and msg.longitude:
                self._current_data.latitude = msg.latitude
                self._current_data.longitude = msg.longitude
            
            if msg.gps_qual is not None:
                self._current_data.fix_quality = int(msg.gps_qual)
            
            if msg.num_sats:
                self._current_data.satellites = int(msg.num_sats)
            
            if msg.altitude:
                self._current_data.altitude_m = float(msg.altitude)
            
            if msg.timestamp:
                self._current_data.timestamp = datetime.combine(
                    datetime.now().date(),
                    msg.timestamp
                )
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing GGA fields: {e}")
    
    def _parse_rmc(self, msg: pynmea2.RMC) -> None:
        """Parse RMC sentence for position, speed, and heading"""
        try:
            # Only update position if status is valid ('A')
            if msg.status == 'A':
                if msg.latitude and msg.longitude:
                    self._current_data.latitude = msg.latitude
                    self._current_data.longitude = msg.longitude
                
                if msg.spd_over_grnd is not None:
                    self._current_data.speed_knots = float(msg.spd_over_grnd)
                
                if msg.true_course is not None:
                    self._current_data.heading = float(msg.true_course)
                
                # Set fix quality to 1 if valid
                if self._current_data.fix_quality == 0:
                    self._current_data.fix_quality = 1
            else:
                # Invalid fix
                self._current_data.fix_quality = 0
                
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing RMC fields: {e}")
    
    def _parse_vtg(self, msg: pynmea2.VTG) -> None:
        """Parse VTG sentence for speed and heading"""
        try:
            if msg.true_track is not None:
                self._current_data.heading = float(msg.true_track)
            
            if msg.spd_over_grnd_kts is not None:
                self._current_data.speed_knots = float(msg.spd_over_grnd_kts)
                
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing VTG fields: {e}")
    
    def _parse_gll(self, msg: pynmea2.GLL) -> None:
        """Parse GLL sentence for geographic position"""
        try:
            # Only update position if status is valid ('A')
            if hasattr(msg, 'status') and msg.status == 'A':
                if msg.latitude and msg.longitude:
                    self._current_data.latitude = msg.latitude
                    self._current_data.longitude = msg.longitude
                
                # Set fix quality to 1 if valid and not already set
                if self._current_data.fix_quality == 0:
                    self._current_data.fix_quality = 1
                    
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing GLL fields: {e}")
    
    def get_current_position(self) -> Optional[GPSData]:
        """
        Get the latest GPS position.
        
        Returns:
            GPSData object or None if no valid fix
        """
        if self._current_data.is_valid:
            return self._current_data
        return None
    
    def get_raw_data(self) -> GPSData:
        """Get current GPS data regardless of fix validity"""
        return self._current_data
    
    def reset(self) -> None:
        """Reset GPS data to default state"""
        self._current_data = GPSData()
        self._last_update = None
    
    @property
    def last_update(self) -> Optional[datetime]:
        """Get timestamp of last successful update"""
        return self._last_update