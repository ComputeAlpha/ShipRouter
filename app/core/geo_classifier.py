"""
GeoClassifier Module
Determines if a geographic point is on land or sea using shapefile data.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass

try:
    import fiona
    from shapely.geometry import Point, shape
    from shapely.prepared import prep
    from shapely import STRtree
    HAS_GEO_LIBS = True
except ImportError:
    HAS_GEO_LIBS = False

from ..config import DATASET_DIR

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_LAND_SHAPEFILE = DATASET_DIR / "geodata" / "ne_10m_land.shp"

# South Asian region bounding box (for filtering/optimization)
SOUTH_ASIA_BOUNDS = {
    "min_lat": -10.0,
    "max_lat": 25.0,
    "min_lon": 65.0,
    "max_lon": 100.0
}


@dataclass
class ClassificationResult:
    """Result of land/sea classification"""
    is_sea: bool
    is_land: bool
    confidence: float  # 0.0 to 1.0
    nearest_coast_km: Optional[float] = None
    
    @property
    def terrain_type(self) -> str:
        return "sea" if self.is_sea else "land"


class GeoClassifier:
    """
    Classifies geographic points as land or sea.
    Uses Natural Earth land polygons for detection.
    
    Optimized for South Asian waters (Bay of Bengal, Indian Ocean).
    """
    
    def __init__(self, shapefile_path: Optional[Path] = None):
        """
        Initialize the GeoClassifier.
        
        Args:
            shapefile_path: Path to land polygons shapefile (.shp)
        """
        if not HAS_GEO_LIBS:
            raise ImportError(
                "Geospatial libraries not installed. "
                "Run: pip install shapely fiona pyproj"
            )
        
        self._shapefile_path = shapefile_path or DEFAULT_LAND_SHAPEFILE
        self._land_polygons = []
        self._prepared_polygons = []
        self._spatial_index = None
        self._loaded = False
        self._bounds = SOUTH_ASIA_BOUNDS
    
    def load(self, filter_to_region: bool = True) -> bool:
        """
        Load land polygons from shapefile.
        
        Args:
            filter_to_region: If True, only load polygons intersecting South Asia
        
        Returns:
            True if loaded successfully
        """
        if not self._shapefile_path.exists():
            logger.error(f"Shapefile not found: {self._shapefile_path}")
            logger.info("Download from: https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip")
            return False
        
        try:
            logger.info(f"Loading land polygons from {self._shapefile_path}...")
            
            self._land_polygons = []
            
            with fiona.open(self._shapefile_path, 'r') as src:
                for feature in src:
                    geom = shape(feature['geometry'])
                    
                    # Filter to region of interest for performance
                    if filter_to_region:
                        if not self._intersects_bounds(geom):
                            continue
                    
                    self._land_polygons.append(geom)
            
            # Create prepared geometries for faster point-in-polygon tests
            self._prepared_polygons = [prep(poly) for poly in self._land_polygons]
            
            # Create spatial index for faster lookups
            if self._land_polygons:
                self._spatial_index = STRtree(self._land_polygons)
            
            self._loaded = True
            logger.info(f"Loaded {len(self._land_polygons)} land polygons for region")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load shapefile: {e}")
            return False
    
    def _intersects_bounds(self, geom) -> bool:
        """Check if geometry intersects the region of interest"""
        minx, miny, maxx, maxy = geom.bounds
        
        return not (
            maxx < self._bounds["min_lon"] or
            minx > self._bounds["max_lon"] or
            maxy < self._bounds["min_lat"] or
            miny > self._bounds["max_lat"]
        )
    
    def is_on_sea(self, lat: float, lon: float) -> bool:
        """
        Check if a point is on sea (water).
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
        
        Returns:
            True if point is on sea, False if on land
        """
        if not self._loaded:
            logger.warning("GeoClassifier not loaded, assuming sea")
            return True
        
        point = Point(lon, lat)  # Shapely uses (x, y) = (lon, lat)
        
        # Use spatial index for faster lookup
        if self._spatial_index:
            # Get candidate polygons that might contain the point
            candidates_idx = self._spatial_index.query(point)
            
            for idx in candidates_idx:
                if idx < len(self._prepared_polygons):
                    if self._prepared_polygons[idx].contains(point):
                        return False  # Point is on land
        else:
            # Fallback to brute force check
            for prepared_poly in self._prepared_polygons:
                if prepared_poly.contains(point):
                    return False  # Point is on land
        
        return True  # Point is on sea
    
    def is_on_land(self, lat: float, lon: float) -> bool:
        """
        Check if a point is on land.
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
        
        Returns:
            True if point is on land, False if on sea
        """
        return not self.is_on_sea(lat, lon)
    
    def classify(self, lat: float, lon: float) -> ClassificationResult:
        """
        Get detailed classification for a point.
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
        
        Returns:
            ClassificationResult with detailed info
        """
        is_sea = self.is_on_sea(lat, lon)
        
        return ClassificationResult(
            is_sea=is_sea,
            is_land=not is_sea,
            confidence=1.0 if self._loaded else 0.5
        )
    
    def classify_points(self, points: List[Tuple[float, float]]) -> List[bool]:
        """
        Batch classify multiple points (more efficient).
        
        Args:
            points: List of (lat, lon) tuples
        
        Returns:
            List of booleans (True = sea, False = land)
        """
        return [self.is_on_sea(lat, lon) for lat, lon in points]
    
    def is_path_over_sea(
        self, 
        start: Tuple[float, float], 
        end: Tuple[float, float],
        num_samples: int = 10
    ) -> bool:
        """
        Check if a straight-line path is entirely over sea.
        
        Args:
            start: (lat, lon) of start point
            end: (lat, lon) of end point
            num_samples: Number of points to sample along path
        
        Returns:
            True if entire path is over sea
        """
        lat1, lon1 = start
        lat2, lon2 = end
        
        for i in range(num_samples + 1):
            t = i / num_samples
            lat = lat1 + t * (lat2 - lat1)
            lon = lon1 + t * (lon2 - lon1)
            
            if not self.is_on_sea(lat, lon):
                return False
        
        return True
    
    def set_bounds(
        self, 
        min_lat: float, 
        max_lat: float, 
        min_lon: float, 
        max_lon: float
    ) -> None:
        """
        Set custom region bounds for filtering.
        Call before load() to take effect.
        """
        self._bounds = {
            "min_lat": min_lat,
            "max_lat": max_lat,
            "min_lon": min_lon,
            "max_lon": max_lon
        }
    
    @property
    def is_loaded(self) -> bool:
        """Check if data is loaded"""
        return self._loaded
    
    @property
    def polygon_count(self) -> int:
        """Number of loaded land polygons"""
        return len(self._land_polygons)
    
    @property
    def bounds(self) -> dict:
        """Current region bounds"""
        return self._bounds.copy()