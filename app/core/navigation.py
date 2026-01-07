"""
Navigation Module
Pure mathematical calculations for distance and bearing.
No hardware dependencies.
"""

import math
from dataclasses import dataclass
from typing import Tuple

from ..config import EARTH_RADIUS_KM


@dataclass
class NavigationResult:
    """Result of navigation calculation between two points"""
    distance_km: float
    distance_nm: float  # Nautical miles
    bearing: float  # Degrees from north (0-360)
    cardinal_direction: str  # N, NE, E, SE, S, SW, W, NW
    
    @property
    def distance_m(self) -> float:
        """Distance in meters"""
        return self.distance_km * 1000


def haversine_distance(
    lat1: float, 
    lon1: float, 
    lat2: float, 
    lon2: float
) -> float:
    """
    Calculate the great-circle distance between two points on Earth
    using the Haversine formula.
    
    Args:
        lat1, lon1: Origin coordinates in decimal degrees
        lat2, lon2: Destination coordinates in decimal degrees
    
    Returns:
        Distance in kilometers
    """
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    # Haversine formula
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return EARTH_RADIUS_KM * c


def calculate_bearing(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calculate the initial bearing (forward azimuth) from point 1 to point 2.
    
    Args:
        lat1, lon1: Origin coordinates in decimal degrees
        lat2, lon2: Destination coordinates in decimal degrees
    
    Returns:
        Bearing in degrees from north (0-360)
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon_rad = math.radians(lon2 - lon1)
    
    x = math.sin(dlon_rad) * math.cos(lat2_rad)
    y = (
        math.cos(lat1_rad) * math.sin(lat2_rad) -
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad)
    )
    
    initial_bearing = math.atan2(x, y)
    
    # Convert to degrees and normalize to 0-360
    bearing_deg = math.degrees(initial_bearing)
    return (bearing_deg + 360) % 360


def bearing_to_cardinal(bearing: float) -> str:
    """
    Convert bearing in degrees to cardinal direction.
    
    Args:
        bearing: Bearing in degrees (0-360)
    
    Returns:
        Cardinal direction string (N, NE, E, SE, S, SW, W, NW)
    """
    # Define direction ranges (centered on each direction)
    directions = [
        (0, 22.5, 'N'),
        (22.5, 67.5, 'NE'),
        (67.5, 112.5, 'E'),
        (112.5, 157.5, 'SE'),
        (157.5, 202.5, 'S'),
        (202.5, 247.5, 'SW'),
        (247.5, 292.5, 'W'),
        (292.5, 337.5, 'NW'),
        (337.5, 360, 'N')
    ]
    
    for min_angle, max_angle, direction in directions:
        if min_angle <= bearing < max_angle:
            return direction
    
    return 'N'  # Default fallback


def km_to_nautical_miles(km: float) -> float:
    """Convert kilometers to nautical miles"""
    return km / 1.852


def nautical_miles_to_km(nm: float) -> float:
    """Convert nautical miles to kilometers"""
    return nm * 1.852


def calculate_navigation(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float
) -> NavigationResult:
    """
    Calculate complete navigation data between two points.
    
    Args:
        from_lat, from_lon: Origin coordinates
        to_lat, to_lon: Destination coordinates
    
    Returns:
        NavigationResult with distance and bearing information
    """
    distance_km = haversine_distance(from_lat, from_lon, to_lat, to_lon)
    bearing = calculate_bearing(from_lat, from_lon, to_lat, to_lon)
    cardinal = bearing_to_cardinal(bearing)
    distance_nm = km_to_nautical_miles(distance_km)
    
    return NavigationResult(
        distance_km=round(distance_km, 3),
        distance_nm=round(distance_nm, 3),
        bearing=round(bearing, 1),
        cardinal_direction=cardinal
    )


def calculate_eta_hours(distance_km: float, speed_knots: float) -> float:
    """
    Calculate estimated time of arrival.
    
    Args:
        distance_km: Distance in kilometers
        speed_knots: Speed in knots
    
    Returns:
        ETA in hours, or -1 if speed is 0
    """
    if speed_knots <= 0:
        return -1
    
    distance_nm = km_to_nautical_miles(distance_km)
    return distance_nm / speed_knots


def format_eta(hours: float) -> str:
    """
    Format ETA hours into human-readable string.
    
    Args:
        hours: Time in hours
    
    Returns:
        Formatted string like "2h 30m" or "45m"
    """
    if hours < 0:
        return "N/A"
    
    total_minutes = int(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60
    
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"