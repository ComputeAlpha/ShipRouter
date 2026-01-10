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

# Sea routing (may not be available if geodata not installed)
try:
    from .geo_classifier import GeoClassifier, ClassificationResult
    from .navigation_grid import NavigationGrid, GridNode, GridGenerator
    from .route_engine import RouteEngine, SeaRoute, RouteWaypoint
    from .sea_router import SeaRouter, NavigationGuidance, get_sea_router
    HAS_SEA_ROUTING = True
except ImportError:
    HAS_SEA_ROUTING = False

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
    'FuelMonitor',
    # Sea routing flag
    'HAS_SEA_ROUTING',
]

# Add sea routing exports if available
if HAS_SEA_ROUTING:
    __all__.extend([
        'GeoClassifier',
        'ClassificationResult',
        'NavigationGrid',
        'GridNode',
        'GridGenerator',
        'RouteEngine',
        'SeaRoute',
        'RouteWaypoint',
        'SeaRouter',
        'NavigationGuidance',
        'get_sea_router',
    ])