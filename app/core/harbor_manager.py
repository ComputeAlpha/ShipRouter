"""
Harbor Manager Module
Handles loading, storing, and querying harbor data.
"""

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .navigation import calculate_navigation, NavigationResult
from ..config import HARBORS_CSV, TOP_N_HARBORS

logger = logging.getLogger(__name__)


@dataclass
class Harbor:
    """Harbor data structure"""
    name: str
    latitude: float
    longitude: float
    description: str = ""
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "description": self.description
        }


@dataclass
class HarborWithDistance:
    """Harbor with calculated navigation data from current position"""
    harbor: Harbor
    navigation: NavigationResult
    rank: int = 0  # 1 = closest
    
    def to_dict(self) -> dict:
        return {
            "name": self.harbor.name,
            "latitude": self.harbor.latitude,
            "longitude": self.harbor.longitude,
            "description": self.harbor.description,
            "distance_km": self.navigation.distance_km,
            "distance_nm": self.navigation.distance_nm,
            "bearing": self.navigation.bearing,
            "cardinal_direction": self.navigation.cardinal_direction,
            "rank": self.rank
        }


class HarborManager:
    """
    Manages harbor database operations.
    Loads harbors from CSV and provides query methods.
    """
    
    def __init__(self, csv_path: Optional[Path] = None):
        self._csv_path = csv_path or HARBORS_CSV
        self._harbors: List[Harbor] = []
        self._loaded = False
    
    def load(self) -> bool:
        """
        Load harbors from CSV file.
        
        Expected CSV format:
        name,latitude,longitude,description (optional)
        
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            if not self._csv_path.exists():
                logger.error(f"Harbors CSV not found: {self._csv_path}")
                return False
            
            self._harbors = []
            
            with open(self._csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        harbor = Harbor(
                            name=row['name'].strip(),
                            latitude=float(row['latitude']),
                            longitude=float(row['longitude']),
                            description=row.get('description', '').strip()
                        )
                        self._harbors.append(harbor)
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Invalid harbor row: {row}, error: {e}")
            
            self._loaded = True
            logger.info(f"Loaded {len(self._harbors)} harbors from {self._csv_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load harbors: {e}")
            return False
    
    def reload(self) -> bool:
        """Reload harbors from CSV"""
        self._loaded = False
        return self.load()
    
    @property
    def is_loaded(self) -> bool:
        """Check if harbors are loaded"""
        return self._loaded
    
    @property
    def count(self) -> int:
        """Get number of loaded harbors"""
        return len(self._harbors)
    
    def get_all(self) -> List[Harbor]:
        """Get all harbors"""
        return self._harbors.copy()
    
    def get_by_name(self, name: str) -> Optional[Harbor]:
        """
        Find harbor by name (case-insensitive).
        
        Args:
            name: Harbor name to search
        
        Returns:
            Harbor object or None if not found
        """
        name_lower = name.lower()
        for harbor in self._harbors:
            if harbor.name.lower() == name_lower:
                return harbor
        return None
    
    def find_nearest(
        self,
        current_lat: float,
        current_lon: float,
        top_n: int = TOP_N_HARBORS
    ) -> List[HarborWithDistance]:
        """
        Find the nearest harbors from current position.
        
        Args:
            current_lat: Current latitude
            current_lon: Current longitude
            top_n: Number of nearest harbors to return
        
        Returns:
            List of HarborWithDistance sorted by distance (closest first)
        """
        if not self._harbors:
            return []
        
        results = []
        
        for harbor in self._harbors:
            nav = calculate_navigation(
                current_lat, current_lon,
                harbor.latitude, harbor.longitude
            )
            results.append(HarborWithDistance(harbor=harbor, navigation=nav))
        
        # Sort by distance
        results.sort(key=lambda x: x.navigation.distance_km)
        
        # Assign ranks and limit results
        for i, item in enumerate(results[:top_n]):
            item.rank = i + 1
        
        return results[:top_n]
    
    def calculate_distance_to(
        self,
        harbor_name: str,
        current_lat: float,
        current_lon: float
    ) -> Optional[HarborWithDistance]:
        """
        Calculate navigation data to a specific harbor.
        
        Args:
            harbor_name: Name of destination harbor
            current_lat: Current latitude
            current_lon: Current longitude
        
        Returns:
            HarborWithDistance or None if harbor not found
        """
        harbor = self.get_by_name(harbor_name)
        if not harbor:
            return None
        
        nav = calculate_navigation(
            current_lat, current_lon,
            harbor.latitude, harbor.longitude
        )
        
        return HarborWithDistance(harbor=harbor, navigation=nav, rank=0)
    
    def get_all_with_distances(
        self,
        current_lat: float,
        current_lon: float
    ) -> List[HarborWithDistance]:
        """
        Get all harbors with distances from current position.
        
        Args:
            current_lat: Current latitude
            current_lon: Current longitude
        
        Returns:
            List of all harbors with distances, sorted by distance
        """
        return self.find_nearest(current_lat, current_lon, top_n=len(self._harbors))
    
    def to_dict_list(self) -> List[dict]:
        """Convert all harbors to list of dicts"""
        return [h.to_dict() for h in self._harbors]