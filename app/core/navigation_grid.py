"""
NavigationGrid Module
Generates a navigable grid over sea areas for pathfinding.
"""

import logging
import json
import math
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime

from .geo_classifier import GeoClassifier
from .navigation import haversine_distance
from ..config import DATASET_DIR

logger = logging.getLogger(__name__)

# Grid cache file
GRID_CACHE_FILE = DATASET_DIR / "geodata" / "navigation_grid.json"


@dataclass
class GridNode:
    """A single node in the navigation grid"""
    id: str
    lat: float
    lon: float
    neighbors: List[str] = field(default_factory=list)
    is_coastal: bool = False  # True if near land
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lat": self.lat,
            "lon": self.lon,
            "neighbors": self.neighbors,
            "is_coastal": self.is_coastal
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'GridNode':
        return cls(
            id=data["id"],
            lat=data["lat"],
            lon=data["lon"],
            neighbors=data.get("neighbors", []),
            is_coastal=data.get("is_coastal", False)
        )


@dataclass
class NavigationGrid:
    """
    A navigation grid covering sea areas.
    Used for A* pathfinding to avoid land.
    """
    nodes: Dict[str, GridNode] = field(default_factory=dict)
    resolution_km: float = 10.0
    bounds: Dict[str, float] = field(default_factory=dict)
    created_at: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "resolution_km": self.resolution_km,
            "bounds": self.bounds,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'NavigationGrid':
        grid = cls(
            resolution_km=data.get("resolution_km", 10.0),
            bounds=data.get("bounds", {}),
            created_at=data.get("created_at")
        )
        for node_id, node_data in data.get("nodes", {}).items():
            grid.nodes[node_id] = GridNode.from_dict(node_data)
        return grid
    
    def get_node(self, node_id: str) -> Optional[GridNode]:
        return self.nodes.get(node_id)
    
    def get_nearest_node(self, lat: float, lon: float) -> Optional[GridNode]:
        """Find the nearest grid node to a given position"""
        if not self.nodes:
            return None
        
        nearest = None
        min_dist = float('inf')
        
        for node in self.nodes.values():
            dist = haversine_distance(lat, lon, node.lat, node.lon)
            if dist < min_dist:
                min_dist = dist
                nearest = node
        
        return nearest
    
    @property
    def node_count(self) -> int:
        return len(self.nodes)


class GridGenerator:
    """
    Generates navigation grids over sea areas.
    
    The grid consists of evenly-spaced points over water,
    with connections (edges) between neighboring sea points.
    """
    
    def __init__(self, geo_classifier: GeoClassifier):
        """
        Initialize grid generator.
        
        Args:
            geo_classifier: GeoClassifier instance for land/sea detection
        """
        self._classifier = geo_classifier
        self._grid: Optional[NavigationGrid] = None
    
    def generate(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        resolution_km: float = 10.0,
        include_diagonals: bool = True
    ) -> NavigationGrid:
        """
        Generate a navigation grid over the specified region.
        
        Args:
            min_lat, max_lat: Latitude bounds
            min_lon, max_lon: Longitude bounds  
            resolution_km: Distance between grid points in km
            include_diagonals: Include diagonal connections
        
        Returns:
            NavigationGrid with sea nodes and connections
        """
        logger.info(f"Generating navigation grid: {resolution_km}km resolution")
        logger.info(f"Bounds: lat [{min_lat}, {max_lat}], lon [{min_lon}, {max_lon}]")
        
        # Convert resolution to degrees (approximate)
        # 1 degree latitude ≈ 111 km
        # 1 degree longitude ≈ 111 * cos(lat) km
        lat_step = resolution_km / 111.0
        avg_lat = (min_lat + max_lat) / 2
        lon_step = resolution_km / (111.0 * math.cos(math.radians(avg_lat)))
        
        grid = NavigationGrid(
            resolution_km=resolution_km,
            bounds={
                "min_lat": min_lat,
                "max_lat": max_lat,
                "min_lon": min_lon,
                "max_lon": max_lon
            },
            created_at=datetime.now().isoformat()
        )
        
        # Generate grid points
        sea_points = {}  # (row, col) -> GridNode
        
        row = 0
        lat = min_lat
        while lat <= max_lat:
            col = 0
            lon = min_lon
            while lon <= max_lon:
                # Check if point is on sea
                if self._classifier.is_on_sea(lat, lon):
                    node_id = f"N{row}_{col}"
                    
                    # Check if coastal (has land nearby)
                    is_coastal = self._is_near_land(lat, lon, resolution_km / 2)
                    
                    node = GridNode(
                        id=node_id,
                        lat=round(lat, 6),
                        lon=round(lon, 6),
                        is_coastal=is_coastal
                    )
                    sea_points[(row, col)] = node
                    grid.nodes[node_id] = node
                
                lon += lon_step
                col += 1
            lat += lat_step
            row += 1
        
        logger.info(f"Generated {len(grid.nodes)} sea nodes")
        
        # Connect neighboring nodes
        self._connect_neighbors(grid, sea_points, include_diagonals)
        
        self._grid = grid
        return grid
    
    def _is_near_land(self, lat: float, lon: float, radius_km: float) -> bool:
        """Check if a point is near land"""
        # Sample points in a small circle
        for angle in range(0, 360, 45):
            dlat = (radius_km / 111.0) * math.cos(math.radians(angle))
            dlon = (radius_km / (111.0 * math.cos(math.radians(lat)))) * math.sin(math.radians(angle))
            
            if self._classifier.is_on_land(lat + dlat, lon + dlon):
                return True
        
        return False
    
    def _connect_neighbors(
        self, 
        grid: NavigationGrid, 
        sea_points: Dict[Tuple[int, int], GridNode],
        include_diagonals: bool
    ) -> None:
        """Connect neighboring sea nodes"""
        
        # Direction offsets: (row_offset, col_offset)
        directions = [
            (-1, 0),   # North
            (1, 0),    # South
            (0, -1),   # West
            (0, 1),    # East
        ]
        
        if include_diagonals:
            directions.extend([
                (-1, -1),  # NW
                (-1, 1),   # NE
                (1, -1),   # SW
                (1, 1),    # SE
            ])
        
        edge_count = 0
        
        for (row, col), node in sea_points.items():
            for dr, dc in directions:
                neighbor_pos = (row + dr, col + dc)
                if neighbor_pos in sea_points:
                    neighbor = sea_points[neighbor_pos]
                    
                    # Verify path between nodes is over sea
                    if self._classifier.is_path_over_sea(
                        (node.lat, node.lon),
                        (neighbor.lat, neighbor.lon),
                        num_samples=3
                    ):
                        node.neighbors.append(neighbor.id)
                        edge_count += 1
        
        logger.info(f"Created {edge_count} connections between nodes")
    
    def save_grid(self, path: Optional[Path] = None) -> bool:
        """Save grid to JSON file"""
        if not self._grid:
            logger.error("No grid to save")
            return False
        
        save_path = path or GRID_CACHE_FILE
        
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(save_path, 'w') as f:
                json.dump(self._grid.to_dict(), f)
            
            logger.info(f"Saved grid to {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save grid: {e}")
            return False
    
    def load_grid(self, path: Optional[Path] = None) -> Optional[NavigationGrid]:
        """Load grid from JSON file"""
        load_path = path or GRID_CACHE_FILE
        
        if not load_path.exists():
            logger.warning(f"Grid file not found: {load_path}")
            return None
        
        try:
            with open(load_path, 'r') as f:
                data = json.load(f)
            
            self._grid = NavigationGrid.from_dict(data)
            logger.info(f"Loaded grid with {self._grid.node_count} nodes from {load_path}")
            return self._grid
            
        except Exception as e:
            logger.error(f"Failed to load grid: {e}")
            return None
    
    @property
    def grid(self) -> Optional[NavigationGrid]:
        return self._grid


def generate_south_asia_grid(
    geo_classifier: GeoClassifier,
    resolution_km: float = 10.0
) -> NavigationGrid:
    """
    Generate a pre-configured grid for South Asian waters.
    
    Covers: Bay of Bengal, Indian Ocean (around India/Sri Lanka)
    """
    generator = GridGenerator(geo_classifier)
    
    return generator.generate(
        min_lat=-5.0,    # South of Sri Lanka
        max_lat=23.0,    # Up to Bangladesh
        min_lon=68.0,    # West coast of India
        max_lon=95.0,    # Andaman Sea
        resolution_km=resolution_km,
        include_diagonals=True
    )