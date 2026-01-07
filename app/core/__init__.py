"""
Core Algorithms Package
Pure computational logic without hardware dependencies
"""

from .navigation import (
    NavigationResult,
    haversine_distance,
    calculate_bearing,
    bearing_to_cardinal,
    calculate_navigation,
    calculate_eta_hours,
    format_eta,
    km_to_nautical_miles,
    nautical_miles_to_km
)
from .harbor_manager import (
    Harbor,
    HarborWithDistance,
    HarborManager
)
from .fuel_monitor import (
    EmergencyState,
    FuelMonitorState,
    FuelMonitor
)

__all__ = [
    # Navigation
    'NavigationResult',
    'haversine_distance',
    'calculate_bearing',
    'bearing_to_cardinal',
    'calculate_navigation',
    'calculate_eta_hours',
    'format_eta',
    'km_to_nautical_miles',
    'nautical_miles_to_km',
    # Harbor
    'Harbor',
    'HarborWithDistance',
    'HarborManager',
    # Fuel
    'EmergencyState',
    'FuelMonitorState',
    'FuelMonitor'
]