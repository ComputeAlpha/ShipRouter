"""
SeaRouter Service
High-level service that integrates geo classification, grid generation, and route planning.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass

from .geo_classifier import GeoClassifier, ClassificationResult
from .navigation_grid import NavigationGrid, GridGenerator, GRID_CACHE_FILE
from .route_engine import RouteEngine, SeaRoute, RouteWaypoint
from .navigation import haversine_distance, calculate_bearing, bearing_to_cardinal
from ..config import DATASET_DIR

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_SHAPEFILE = DATASET_DIR / "geodata" / "ne_10m_land.shp"

# South Asia region defaults
SOUTH_ASIA_BOUNDS = {
    "min_lat": -5.0,
    "max_lat": 23.0,
    "min_lon": 68.0,
    "max_lon": 95.0
}


@dataclass
class NavigationGuidance:
    """Real-time navigation guidance to next waypoint"""
    has_route: bool = False
    
    # Current status
    current_lat: Optional[float] = None
    current_lon: Optional[float] = None
    is_on_sea: bool = True
    terrain_type: str = "unknown"
    
    # Next waypoint
    next_waypoint: Optional[RouteWaypoint] = None
    distance_to_next_km: float = 0.0
    distance_to_next_nm: float = 0.0
    bearing_to_next: float = 0.0
    cardinal_to_next: str = ""
    
    # Destination
    destination_name: str = ""
    total_remaining_km: float = 0.0
    total_remaining_nm: float = 0.0
    
    # Progress
    waypoints_remaining: int = 0
    progress_percent: float = 0.0
    
    # Route type
    is_direct_route: bool = False  # True if straight line, False if via waypoints
    
    def to_dict(self) -> dict:
        return {
            "has_route": self.has_route,
            "current_position": {
                "lat": self.current_lat,
                "lon": self.current_lon,
                "is_on_sea": self.is_on_sea,
                "terrain": self.terrain_type
            },
            "next_waypoint": self.next_waypoint.to_dict() if self.next_waypoint else None,
            "navigation": {
                "distance_km": round(self.distance_to_next_km, 2),
                "distance_nm": round(self.distance_to_next_nm, 2),
                "bearing": round(self.bearing_to_next, 1),
                "cardinal": self.cardinal_to_next
            },
            "destination": {
                "name": self.destination_name,
                "remaining_km": round(self.total_remaining_km, 2),
                "remaining_nm": round(self.total_remaining_nm, 2)
            },
            "progress": {
                "waypoints_remaining": self.waypoints_remaining,
                "percent": round(self.progress_percent, 1)
            },
            "is_direct_route": self.is_direct_route
        }


class SeaRouter:
    """
    High-level sea routing service.
    
    Provides:
    - Land/sea detection
    - Sea route planning
    - Real-time navigation guidance
    """
    
    def __init__(
        self,
        shapefile_path: Optional[Path] = None,
        grid_resolution_km: float = 10.0,
        auto_load: bool = True
    ):
        """
        Initialize SeaRouter.
        
        Args:
            shapefile_path: Path to land polygons shapefile
            grid_resolution_km: Navigation grid resolution
            auto_load: Automatically load data on init
        """
        self._shapefile_path = shapefile_path or DEFAULT_SHAPEFILE
        self._grid_resolution = grid_resolution_km
        
        self._classifier: Optional[GeoClassifier] = None
        self._grid: Optional[NavigationGrid] = None
        self._route_engine: Optional[RouteEngine] = None
        
        self._current_route: Optional[SeaRoute] = None
        self._initialized = False
        
        if auto_load:
            self.initialize()
    
    def initialize(self) -> bool:
        """
        Initialize all routing components.
        
        Returns:
            True if initialized successfully
        """
        logger.info("Initializing SeaRouter...")
        
        # Check if geodata directory exists
        geodata_dir = DATASET_DIR / "geodata"
        if not geodata_dir.exists():
            logger.warning(f"Geodata directory not found: {geodata_dir}")
            logger.info("Sea routing will be disabled until geodata is installed")
            logger.info("Download from: https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip")
            return False
        
        # Initialize geo classifier
        self._classifier = GeoClassifier(self._shapefile_path)
        if not self._classifier.load():
            logger.warning("Failed to load geo classifier - sea routing disabled")
            return False
        
        # Try to load cached grid, or generate new one
        generator = GridGenerator(self._classifier)
        self._grid = generator.load_grid()
        
        if not self._grid:
            logger.info("No cached grid found, generating new grid...")
            logger.info("This may take a few minutes for first-time setup...")
            
            self._grid = generator.generate(
                min_lat=SOUTH_ASIA_BOUNDS["min_lat"],
                max_lat=SOUTH_ASIA_BOUNDS["max_lat"],
                min_lon=SOUTH_ASIA_BOUNDS["min_lon"],
                max_lon=SOUTH_ASIA_BOUNDS["max_lon"],
                resolution_km=self._grid_resolution
            )
            
            # Save for next time
            generator.save_grid()
        
        # Initialize route engine
        self._route_engine = RouteEngine(self._grid)
        
        self._initialized = True
        logger.info(f"SeaRouter initialized: {self._grid.node_count} navigation nodes")
        return True
    
    def is_on_sea(self, lat: float, lon: float) -> bool:
        """Check if position is on sea"""
        if not self._classifier or not self._classifier.is_loaded:
            return True  # Assume sea if not loaded
        return self._classifier.is_on_sea(lat, lon)
    
    def is_on_land(self, lat: float, lon: float) -> bool:
        """Check if position is on land"""
        return not self.is_on_sea(lat, lon)
    
    def classify_position(self, lat: float, lon: float) -> ClassificationResult:
        """Get detailed classification of position"""
        if not self._classifier or not self._classifier.is_loaded:
            return ClassificationResult(is_sea=True, is_land=False, confidence=0.0)
        return self._classifier.classify(lat, lon)
    
    def plan_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        dest_name: str = "Destination"
    ) -> SeaRoute:
        """
        Plan a sea route from origin to destination.
        
        Args:
            origin_lat, origin_lon: Starting position
            dest_lat, dest_lon: Destination position
            dest_name: Name of destination
        
        Returns:
            SeaRoute with waypoints
        """
        if not self._initialized or not self._route_engine:
            # Return direct route if not initialized
            route = SeaRoute(
                origin=(origin_lat, origin_lon),
                destination=(dest_lat, dest_lon),
                destination_name=dest_name
            )
            
            # Create simple direct route
            direct_distance = haversine_distance(
                origin_lat, origin_lon, dest_lat, dest_lon
            )
            bearing = calculate_bearing(
                origin_lat, origin_lon, dest_lat, dest_lon
            )
            
            route.waypoints = [
                RouteWaypoint(
                    lat=origin_lat, lon=origin_lon,
                    is_origin=True,
                    bearing_to_next=bearing,
                    cardinal_to_next=bearing_to_cardinal(bearing)
                ),
                RouteWaypoint(
                    lat=dest_lat, lon=dest_lon,
                    is_destination=True,
                    distance_from_prev_km=direct_distance,
                    cumulative_distance_km=direct_distance
                )
            ]
            route.total_distance_km = direct_distance
            route.total_distance_nm = direct_distance / 1.852
            route.is_valid = True
            route.error_message = "Direct route (sea routing not initialized)"
            
            return route
        
        route = self._route_engine.find_route(
            origin_lat, origin_lon,
            dest_lat, dest_lon,
            dest_name
        )
        
        self._current_route = route
        return route
    
    def get_guidance(
        self,
        current_lat: float,
        current_lon: float,
        route: Optional[SeaRoute] = None
    ) -> NavigationGuidance:
        """
        Get real-time navigation guidance.
        
        Args:
            current_lat, current_lon: Current position
            route: Route to follow (uses current route if None)
        
        Returns:
            NavigationGuidance with next waypoint info
        """
        route = route or self._current_route
        
        guidance = NavigationGuidance(
            current_lat=current_lat,
            current_lon=current_lon
        )
        
        # Classify current position
        if self._classifier and self._classifier.is_loaded:
            classification = self._classifier.classify(current_lat, current_lon)
            guidance.is_on_sea = classification.is_sea
            guidance.terrain_type = classification.terrain_type
        
        if not route or not route.is_valid:
            return guidance
        
        guidance.has_route = True
        guidance.destination_name = route.destination_name
        guidance.is_direct_route = len(route.waypoints) <= 2
        
        # Find next waypoint
        next_wp = None
        waypoints_remaining = 0
        
        for i, wp in enumerate(route.waypoints):
            if wp.is_origin:
                continue
            
            dist = haversine_distance(current_lat, current_lon, wp.lat, wp.lon)
            
            # Consider waypoint "reached" if within 500m
            if dist > 0.5:
                if next_wp is None:
                    next_wp = wp
                    guidance.distance_to_next_km = dist
                    guidance.distance_to_next_nm = dist / 1.852
                    
                    # Calculate bearing to next waypoint
                    guidance.bearing_to_next = calculate_bearing(
                        current_lat, current_lon, wp.lat, wp.lon
                    )
                    guidance.cardinal_to_next = bearing_to_cardinal(guidance.bearing_to_next)
                
                waypoints_remaining += 1
        
        guidance.next_waypoint = next_wp
        guidance.waypoints_remaining = waypoints_remaining
        
        # Calculate remaining distance
        if next_wp:
            # Distance to next + remaining waypoints
            remaining = guidance.distance_to_next_km
            
            found_next = False
            for i, wp in enumerate(route.waypoints):
                if wp == next_wp:
                    found_next = True
                    continue
                if found_next and i < len(route.waypoints) - 1:
                    next_i = route.waypoints[i + 1]
                    remaining += haversine_distance(wp.lat, wp.lon, next_i.lat, next_i.lon)
            
            guidance.total_remaining_km = remaining
            guidance.total_remaining_nm = remaining / 1.852
            
            # Calculate progress
            if route.total_distance_km > 0:
                completed = route.total_distance_km - remaining
                guidance.progress_percent = (completed / route.total_distance_km) * 100
        
        return guidance
    
    def clear_route(self) -> None:
        """Clear current route"""
        self._current_route = None
    
    @property
    def current_route(self) -> Optional[SeaRoute]:
        """Get current active route"""
        return self._current_route
    
    @property
    def is_initialized(self) -> bool:
        """Check if sea routing is available"""
        return self._initialized
    
    @property
    def grid_node_count(self) -> int:
        """Number of navigation grid nodes"""
        return self._grid.node_count if self._grid else 0
    
    def regenerate_grid(self, resolution_km: float = 10.0) -> bool:
        """
        Regenerate navigation grid with new resolution.
        
        Args:
            resolution_km: New grid resolution
        
        Returns:
            True if regeneration successful
        """
        if not self._classifier or not self._classifier.is_loaded:
            return False
        
        logger.info(f"Regenerating grid with {resolution_km}km resolution...")
        
        generator = GridGenerator(self._classifier)
        self._grid = generator.generate(
            min_lat=SOUTH_ASIA_BOUNDS["min_lat"],
            max_lat=SOUTH_ASIA_BOUNDS["max_lat"],
            min_lon=SOUTH_ASIA_BOUNDS["min_lon"],
            max_lon=SOUTH_ASIA_BOUNDS["max_lon"],
            resolution_km=resolution_km
        )
        
        generator.save_grid()
        
        self._route_engine = RouteEngine(self._grid)
        self._grid_resolution = resolution_km
        
        return True


# Singleton instance
_sea_router: Optional[SeaRouter] = None


def get_sea_router() -> SeaRouter:
    """Get or create the singleton SeaRouter instance"""
    global _sea_router
    if _sea_router is None:
        _sea_router = SeaRouter(auto_load=True)
    return _sea_router


def initialize_sea_router(**kwargs) -> SeaRouter:
    """Initialize SeaRouter with custom parameters"""
    global _sea_router
    _sea_router = SeaRouter(**kwargs)
    return _sea_router