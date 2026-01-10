"""
RouteEngine Module
A* pathfinding for sea routes avoiding land.
"""

import logging
import heapq
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass, field

from .navigation import haversine_distance, calculate_bearing, bearing_to_cardinal
from .navigation_grid import NavigationGrid, GridNode

logger = logging.getLogger(__name__)


@dataclass
class RouteWaypoint:
    """A waypoint in a sea route"""
    lat: float
    lon: float
    node_id: Optional[str] = None
    distance_from_prev_km: float = 0.0
    cumulative_distance_km: float = 0.0
    bearing_to_next: Optional[float] = None
    cardinal_to_next: Optional[str] = None
    is_origin: bool = False
    is_destination: bool = False
    
    def to_dict(self) -> dict:
        return {
            "lat": self.lat,
            "lon": self.lon,
            "node_id": self.node_id,
            "distance_from_prev_km": round(self.distance_from_prev_km, 2),
            "cumulative_distance_km": round(self.cumulative_distance_km, 2),
            "bearing_to_next": round(self.bearing_to_next, 1) if self.bearing_to_next else None,
            "cardinal_to_next": self.cardinal_to_next,
            "is_origin": self.is_origin,
            "is_destination": self.is_destination
        }


@dataclass
class SeaRoute:
    """A complete sea route from origin to destination"""
    origin: Tuple[float, float]  # (lat, lon)
    destination: Tuple[float, float]  # (lat, lon)
    destination_name: str
    waypoints: List[RouteWaypoint] = field(default_factory=list)
    total_distance_km: float = 0.0
    total_distance_nm: float = 0.0
    is_valid: bool = False
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "origin": {"lat": self.origin[0], "lon": self.origin[1]},
            "destination": {"lat": self.destination[0], "lon": self.destination[1]},
            "destination_name": self.destination_name,
            "waypoints": [w.to_dict() for w in self.waypoints],
            "total_distance_km": round(self.total_distance_km, 2),
            "total_distance_nm": round(self.total_distance_nm, 2),
            "waypoint_count": len(self.waypoints),
            "is_valid": self.is_valid,
            "error_message": self.error_message
        }
    
    @property
    def simplified_waypoints(self) -> List[Tuple[float, float]]:
        """Get just the coordinates for map display"""
        return [(w.lat, w.lon) for w in self.waypoints]


class RouteEngine:
    """
    Sea route planning engine using A* pathfinding.
    
    Finds optimal paths over water while avoiding land masses.
    """
    
    def __init__(self, grid: NavigationGrid):
        """
        Initialize route engine.
        
        Args:
            grid: NavigationGrid with sea nodes
        """
        self._grid = grid
        self._node_coords: Dict[str, Tuple[float, float]] = {}
        
        # Cache node coordinates for faster lookup
        for node_id, node in grid.nodes.items():
            self._node_coords[node_id] = (node.lat, node.lon)
    
    def find_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        dest_name: str = "Destination"
    ) -> SeaRoute:
        """
        Find a sea route from origin to destination.
        
        Args:
            origin_lat, origin_lon: Starting position
            dest_lat, dest_lon: Destination position
            dest_name: Name of destination (for display)
        
        Returns:
            SeaRoute with waypoints and distance
        """
        route = SeaRoute(
            origin=(origin_lat, origin_lon),
            destination=(dest_lat, dest_lon),
            destination_name=dest_name
        )
        
        # Find nearest grid nodes to origin and destination
        origin_node = self._grid.get_nearest_node(origin_lat, origin_lon)
        dest_node = self._grid.get_nearest_node(dest_lat, dest_lon)
        
        if not origin_node:
            route.error_message = "No navigable water near origin"
            return route
        
        if not dest_node:
            route.error_message = "No navigable water near destination"
            return route
        
        # Check if origin and destination are the same node
        if origin_node.id == dest_node.id:
            # Direct route
            route.waypoints = [
                RouteWaypoint(
                    lat=origin_lat, lon=origin_lon,
                    is_origin=True
                ),
                RouteWaypoint(
                    lat=dest_lat, lon=dest_lon,
                    is_destination=True
                )
            ]
            route.total_distance_km = haversine_distance(
                origin_lat, origin_lon, dest_lat, dest_lon
            )
            route.total_distance_nm = route.total_distance_km / 1.852
            route.is_valid = True
            self._calculate_bearings(route)
            return route
        
        # Run A* pathfinding
        path_node_ids = self._astar(origin_node.id, dest_node.id)
        
        if not path_node_ids:
            route.error_message = "No route found (path blocked by land)"
            return route
        
        # Build waypoint list
        waypoints = []
        
        # Add actual origin
        waypoints.append(RouteWaypoint(
            lat=origin_lat,
            lon=origin_lon,
            is_origin=True
        ))
        
        # Add path nodes (skip first if very close to origin)
        for node_id in path_node_ids:
            node = self._grid.get_node(node_id)
            if node:
                waypoints.append(RouteWaypoint(
                    lat=node.lat,
                    lon=node.lon,
                    node_id=node_id
                ))
        
        # Add actual destination
        waypoints.append(RouteWaypoint(
            lat=dest_lat,
            lon=dest_lon,
            is_destination=True
        ))
        
        # Simplify route (remove unnecessary waypoints)
        waypoints = self._simplify_route(waypoints)
        
        # Calculate distances and bearings
        route.waypoints = waypoints
        self._calculate_distances(route)
        self._calculate_bearings(route)
        
        route.is_valid = True
        return route
    
    def _astar(self, start_id: str, goal_id: str) -> List[str]:
        """
        A* pathfinding algorithm.
        
        Args:
            start_id: Starting node ID
            goal_id: Goal node ID
        
        Returns:
            List of node IDs forming the path, or empty list if no path
        """
        if start_id not in self._grid.nodes or goal_id not in self._grid.nodes:
            return []
        
        goal_coords = self._node_coords[goal_id]
        
        # Priority queue: (f_score, counter, node_id)
        # counter is used to break ties
        counter = 0
        open_set = [(0, counter, start_id)]
        
        # Track where we came from
        came_from: Dict[str, str] = {}
        
        # g_score: cost from start to node
        g_score: Dict[str, float] = {start_id: 0}
        
        # f_score: g_score + heuristic
        start_coords = self._node_coords[start_id]
        h_start = haversine_distance(start_coords[0], start_coords[1], 
                                     goal_coords[0], goal_coords[1])
        f_score: Dict[str, float] = {start_id: h_start}
        
        # Set of visited nodes
        closed_set: set = set()
        
        while open_set:
            _, _, current = heapq.heappop(open_set)
            
            if current == goal_id:
                # Reconstruct path
                return self._reconstruct_path(came_from, current)
            
            if current in closed_set:
                continue
            
            closed_set.add(current)
            
            current_node = self._grid.get_node(current)
            if not current_node:
                continue
            
            current_coords = self._node_coords[current]
            
            for neighbor_id in current_node.neighbors:
                if neighbor_id in closed_set:
                    continue
                
                neighbor_coords = self._node_coords.get(neighbor_id)
                if not neighbor_coords:
                    continue
                
                # Calculate tentative g_score
                edge_cost = haversine_distance(
                    current_coords[0], current_coords[1],
                    neighbor_coords[0], neighbor_coords[1]
                )
                tentative_g = g_score[current] + edge_cost
                
                if neighbor_id not in g_score or tentative_g < g_score[neighbor_id]:
                    # This is a better path
                    came_from[neighbor_id] = current
                    g_score[neighbor_id] = tentative_g
                    
                    # Heuristic: straight-line distance to goal
                    h = haversine_distance(
                        neighbor_coords[0], neighbor_coords[1],
                        goal_coords[0], goal_coords[1]
                    )
                    f_score[neighbor_id] = tentative_g + h
                    
                    counter += 1
                    heapq.heappush(open_set, (f_score[neighbor_id], counter, neighbor_id))
        
        # No path found
        return []
    
    def _reconstruct_path(self, came_from: Dict[str, str], current: str) -> List[str]:
        """Reconstruct path from A* result"""
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path
    
    def _simplify_route(
        self, 
        waypoints: List[RouteWaypoint],
        angle_threshold: float = 15.0
    ) -> List[RouteWaypoint]:
        """
        Simplify route by removing collinear waypoints.
        
        Keeps waypoints where direction changes significantly.
        """
        if len(waypoints) <= 2:
            return waypoints
        
        simplified = [waypoints[0]]  # Always keep origin
        
        for i in range(1, len(waypoints) - 1):
            prev = simplified[-1]
            curr = waypoints[i]
            next_wp = waypoints[i + 1]
            
            # Calculate bearings
            bearing1 = calculate_bearing(prev.lat, prev.lon, curr.lat, curr.lon)
            bearing2 = calculate_bearing(curr.lat, curr.lon, next_wp.lat, next_wp.lon)
            
            # Calculate angle change
            angle_diff = abs(bearing2 - bearing1)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            
            # Keep waypoint if direction changes significantly
            if angle_diff > angle_threshold:
                simplified.append(curr)
        
        simplified.append(waypoints[-1])  # Always keep destination
        
        logger.debug(f"Simplified route: {len(waypoints)} -> {len(simplified)} waypoints")
        return simplified
    
    def _calculate_distances(self, route: SeaRoute) -> None:
        """Calculate distances between waypoints"""
        total = 0.0
        
        for i, wp in enumerate(route.waypoints):
            if i == 0:
                wp.distance_from_prev_km = 0
                wp.cumulative_distance_km = 0
            else:
                prev = route.waypoints[i - 1]
                dist = haversine_distance(prev.lat, prev.lon, wp.lat, wp.lon)
                wp.distance_from_prev_km = dist
                total += dist
                wp.cumulative_distance_km = total
        
        route.total_distance_km = total
        route.total_distance_nm = total / 1.852
    
    def _calculate_bearings(self, route: SeaRoute) -> None:
        """Calculate bearings to next waypoint"""
        for i, wp in enumerate(route.waypoints[:-1]):
            next_wp = route.waypoints[i + 1]
            bearing = calculate_bearing(wp.lat, wp.lon, next_wp.lat, next_wp.lon)
            wp.bearing_to_next = bearing
            wp.cardinal_to_next = bearing_to_cardinal(bearing)
    
    def get_next_waypoint(
        self,
        route: SeaRoute,
        current_lat: float,
        current_lon: float,
        reached_threshold_km: float = 0.5
    ) -> Optional[RouteWaypoint]:
        """
        Get the next waypoint to navigate to.
        
        Args:
            route: The current route
            current_lat, current_lon: Current position
            reached_threshold_km: Distance to consider waypoint "reached"
        
        Returns:
            Next waypoint to navigate to, or None if destination reached
        """
        for wp in route.waypoints:
            if wp.is_origin:
                continue
            
            dist = haversine_distance(current_lat, current_lon, wp.lat, wp.lon)
            
            if dist > reached_threshold_km:
                return wp
        
        return None  # Destination reached
    
    @property
    def grid(self) -> NavigationGrid:
        return self._grid