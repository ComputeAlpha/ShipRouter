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
    
    # Land-to-sea routing
    requires_embarkation: bool = False
    embarkation_harbor: Optional[str] = None
    distance_to_embarkation_km: float = 0.0
    bearing_to_embarkation: float = 0.0
    cardinal_to_embarkation: str = ""
    
    # Next waypoint (for sea portion)
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
    route_type: str = "direct"  # "direct", "sea", "land_to_sea"
    
    def to_dict(self) -> dict:
        return {
            "has_route": self.has_route,
            "current_position": {
                "lat": self.current_lat,
                "lon": self.current_lon,
                "is_on_sea": self.is_on_sea,
                "terrain": self.terrain_type
            },
            "embarkation": {
                "required": self.requires_embarkation,
                "harbor": self.embarkation_harbor,
                "distance_km": round(self.distance_to_embarkation_km, 2),
                "bearing": round(self.bearing_to_embarkation, 1),
                "cardinal": self.cardinal_to_embarkation
            } if self.requires_embarkation else None,
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
            "route_type": self.route_type,
            "is_direct_route": self.is_direct_route
        }


class SeaRouter:
    """
    High-level sea routing service.
    
    Provides:
    - Land/sea detection
    - Sea route planning
    - Land-to-sea routing (via nearest harbor)
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
        
        # Route state - persistent until explicitly changed
        self._current_route: Optional[SeaRoute] = None
        self._embarkation_harbor: Optional[Tuple[str, float, float]] = None  # (name, lat, lon)
        self._last_terrain_was_land: Optional[bool] = None  # Track terrain changes
        self._last_destination: Optional[str] = None  # Track destination changes
        self._initialized = False
        
        # Harbor data for land-to-sea routing
        self._harbors: List[Tuple[str, float, float]] = []  # (name, lat, lon)
        
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
    
    def set_harbors(self, harbors: List[Tuple[str, float, float]]) -> None:
        """
        Set harbor data for land-to-sea routing.
        
        Args:
            harbors: List of (name, latitude, longitude) tuples
        """
        self._harbors = harbors
        logger.info(f"SeaRouter: Loaded {len(harbors)} harbors for land-to-sea routing")
    
    def find_nearest_harbor(self, lat: float, lon: float) -> Optional[Tuple[str, float, float, float]]:
        """
        Find the nearest harbor to a position.
        
        Args:
            lat, lon: Position to search from
        
        Returns:
            Tuple of (name, harbor_lat, harbor_lon, distance_km) or None
        """
        if not self._harbors:
            return None
        
        nearest = None
        min_dist = float('inf')
        
        for name, h_lat, h_lon in self._harbors:
            dist = haversine_distance(lat, lon, h_lat, h_lon)
            if dist < min_dist:
                min_dist = dist
                nearest = (name, h_lat, h_lon, dist)
        
        return nearest
    
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
        
        Handles three cases:
        1. Origin on sea → Direct sea routing
        2. Origin on land → Land to nearest harbor, then sea route
        3. Sea routing not available → Direct line
        
        Args:
            origin_lat, origin_lon: Starting position
            dest_lat, dest_lon: Destination position
            dest_name: Name of destination
        
        Returns:
            SeaRoute with waypoints
        """
        if not self._initialized or not self._route_engine:
            return self._create_direct_route(
                origin_lat, origin_lon, dest_lat, dest_lon, dest_name,
                "Direct route (sea routing not initialized)"
            )
        
        # Check current terrain
        currently_on_land = self.is_on_land(origin_lat, origin_lon)
        
        # Determine if we need to recalculate the route
        terrain_changed = (self._last_terrain_was_land != currently_on_land)
        destination_changed = (self._last_destination != dest_name)
        needs_recalculation = terrain_changed or destination_changed or self._current_route is None
        
        # If nothing changed and we have a valid route, just return it
        if not needs_recalculation and self._current_route and self._current_route.is_valid:
            return self._current_route
        
        # Update tracking state
        self._last_terrain_was_land = currently_on_land
        self._last_destination = dest_name
        
        if currently_on_land:
            # LAND-TO-SEA ROUTING
            logger.info(f"Planning land-to-sea route (terrain_changed={terrain_changed}, dest_changed={destination_changed})")
            return self._plan_land_to_sea_route(
                origin_lat, origin_lon, dest_lat, dest_lon, dest_name
            )
        else:
            # NORMAL SEA ROUTING - clear embarkation when on sea
            if self._embarkation_harbor is not None:
                logger.info("Cleared embarkation harbor (now on sea)")
            self._embarkation_harbor = None
            
            route = self._route_engine.find_route(
                origin_lat, origin_lon,
                dest_lat, dest_lon,
                dest_name
            )
            
            self._current_route = route
            return route
    
    def _plan_land_to_sea_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        dest_name: str
    ) -> SeaRoute:
        """
        Plan a route from land to sea destination.
        
        1. Find nearest harbor to origin (embarkation point)
        2. Route from that harbor to destination via sea
        3. Prepend land leg to the route
        """
        # Find nearest harbor for embarkation
        nearest = self.find_nearest_harbor(origin_lat, origin_lon)
        
        if not nearest:
            logger.warning("No harbors available for land-to-sea routing")
            return self._create_direct_route(
                origin_lat, origin_lon, dest_lat, dest_lon, dest_name,
                "No harbors available for land-to-sea routing"
            )
        
        embark_name, embark_lat, embark_lon, embark_dist = nearest
        self._embarkation_harbor = (embark_name, embark_lat, embark_lon)
        
        logger.info(f"Embarkation point: {embark_name} ({embark_dist:.1f} km)")
        
        # Check if destination is the embarkation harbor itself
        dist_to_dest = haversine_distance(embark_lat, embark_lon, dest_lat, dest_lon)
        if dist_to_dest < 1.0:  # Within 1km - same harbor
            logger.info("Destination is the embarkation harbor - direct route")
            return self._create_direct_route(
                origin_lat, origin_lon, dest_lat, dest_lon, dest_name,
                None  # No error, just direct route
            )
        
        # Get sea route from embarkation harbor to destination
        sea_route = self._route_engine.find_route(
            embark_lat, embark_lon,
            dest_lat, dest_lon,
            dest_name
        )
        
        if not sea_route.is_valid:
            # Sea routing failed, fall back to direct
            logger.warning(f"Sea routing failed: {sea_route.error_message}")
            return self._create_direct_route(
                origin_lat, origin_lon, dest_lat, dest_lon, dest_name,
                f"Sea route unavailable: {sea_route.error_message}"
            )
        
        # Build combined route: Land origin → Embarkation → Sea route → Destination
        combined_waypoints = []
        
        # Add land origin
        bearing_to_embark = calculate_bearing(origin_lat, origin_lon, embark_lat, embark_lon)
        combined_waypoints.append(RouteWaypoint(
            lat=origin_lat,
            lon=origin_lon,
            is_origin=True,
            bearing_to_next=bearing_to_embark,
            cardinal_to_next=bearing_to_cardinal(bearing_to_embark)
        ))
        
        # Add embarkation point (mark it specially)
        embark_waypoint = RouteWaypoint(
            lat=embark_lat,
            lon=embark_lon,
            node_id=f"EMBARK_{embark_name}",
            distance_from_prev_km=embark_dist,
            cumulative_distance_km=embark_dist
        )
        combined_waypoints.append(embark_waypoint)
        
        # Add sea route waypoints (skip the first one if it's the embarkation point)
        cumulative = embark_dist
        for i, wp in enumerate(sea_route.waypoints):
            if wp.is_origin:
                continue  # Skip sea route origin (it's our embarkation)
            
            # Update cumulative distance
            cumulative += wp.distance_from_prev_km
            
            new_wp = RouteWaypoint(
                lat=wp.lat,
                lon=wp.lon,
                node_id=wp.node_id,
                distance_from_prev_km=wp.distance_from_prev_km,
                cumulative_distance_km=cumulative,
                bearing_to_next=wp.bearing_to_next,
                cardinal_to_next=wp.cardinal_to_next,
                is_destination=wp.is_destination
            )
            combined_waypoints.append(new_wp)
        
        # Create combined route
        combined_route = SeaRoute(
            origin=(origin_lat, origin_lon),
            destination=(dest_lat, dest_lon),
            destination_name=dest_name,
            waypoints=combined_waypoints,
            total_distance_km=embark_dist + sea_route.total_distance_km,
            total_distance_nm=(embark_dist + sea_route.total_distance_km) / 1.852,
            is_valid=True,
            error_message=None
        )
        
        self._current_route = combined_route
        return combined_route
    
    def _create_direct_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        dest_name: str,
        error_message: Optional[str]
    ) -> SeaRoute:
        """Create a simple direct route (straight line)"""
        direct_distance = haversine_distance(
            origin_lat, origin_lon, dest_lat, dest_lon
        )
        bearing = calculate_bearing(
            origin_lat, origin_lon, dest_lat, dest_lon
        )
        
        route = SeaRoute(
            origin=(origin_lat, origin_lon),
            destination=(dest_lat, dest_lon),
            destination_name=dest_name
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
        route.error_message = error_message
        
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
        
        # Check if this is a land-to-sea route
        if self._embarkation_harbor and not guidance.is_on_sea:
            guidance.requires_embarkation = True
            embark_name, embark_lat, embark_lon = self._embarkation_harbor
            guidance.embarkation_harbor = embark_name
            guidance.distance_to_embarkation_km = haversine_distance(
                current_lat, current_lon, embark_lat, embark_lon
            )
            guidance.bearing_to_embarkation = calculate_bearing(
                current_lat, current_lon, embark_lat, embark_lon
            )
            guidance.cardinal_to_embarkation = bearing_to_cardinal(guidance.bearing_to_embarkation)
            guidance.route_type = "land_to_sea"
        elif len(route.waypoints) > 2:
            guidance.route_type = "sea"
        else:
            guidance.route_type = "direct"
        
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
        """Clear current route and all tracking state"""
        self._current_route = None
        self._embarkation_harbor = None
        self._last_terrain_was_land = None
        self._last_destination = None
        logger.info("Route cleared")
    
    @property
    def current_route(self) -> Optional[SeaRoute]:
        """Get current active route"""
        return self._current_route
    
    @property
    def embarkation_harbor(self) -> Optional[Tuple[str, float, float]]:
        """Get current embarkation harbor (for land-to-sea routes)"""
        return self._embarkation_harbor
    
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