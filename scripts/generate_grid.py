#!/usr/bin/env python3
"""
Grid Generation Utility
Run this after downloading the Natural Earth shapefile to generate the navigation grid.

Usage:
    python generate_grid.py [--resolution 10]
"""

import argparse
import sys
import time
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.geo_classifier import GeoClassifier
from app.core.navigation_grid import GridGenerator
from app.config import DATASET_DIR


def main():
    parser = argparse.ArgumentParser(description='Generate navigation grid for sea routing')
    parser.add_argument('--resolution', type=float, default=10.0,
                        help='Grid resolution in km (default: 10)')
    parser.add_argument('--shapefile', type=str, default=None,
                        help='Path to land shapefile (default: dataset/geodata/ne_10m_land.shp)')
    args = parser.parse_args()
    
    # Paths
    shapefile = Path(args.shapefile) if args.shapefile else DATASET_DIR / "geodata" / "ne_10m_land.shp"
    
    print("=" * 60)
    print("ShipRouter - Navigation Grid Generator")
    print("=" * 60)
    print()
    
    # Check shapefile exists
    if not shapefile.exists():
        print(f"ERROR: Shapefile not found: {shapefile}")
        print()
        print("Please download Natural Earth land polygons:")
        print("  wget https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip")
        print("  unzip ne_10m_land.zip -d dataset/geodata/")
        sys.exit(1)
    
    print(f"Shapefile: {shapefile}")
    print(f"Resolution: {args.resolution} km")
    print()
    
    # Load classifier
    print("Loading land polygons...")
    start_time = time.time()
    
    classifier = GeoClassifier(shapefile)
    if not classifier.load():
        print("ERROR: Failed to load shapefile")
        sys.exit(1)
    
    print(f"  Loaded {classifier.polygon_count} polygons in {time.time() - start_time:.1f}s")
    print()
    
    # Generate grid
    print("Generating navigation grid (this may take several minutes)...")
    start_time = time.time()
    
    generator = GridGenerator(classifier)
    grid = generator.generate(
        min_lat=-5.0,    # South of Sri Lanka
        max_lat=23.0,    # Up to Bangladesh
        min_lon=68.0,    # West coast of India
        max_lon=95.0,    # Andaman Sea
        resolution_km=args.resolution
    )
    
    print(f"  Generated {grid.node_count} sea nodes in {time.time() - start_time:.1f}s")
    print()
    
    # Save grid
    print("Saving grid...")
    if generator.save_grid():
        print(f"  Saved to: {DATASET_DIR / 'geodata' / 'navigation_grid.json'}")
    else:
        print("  ERROR: Failed to save grid")
        sys.exit(1)
    
    print()
    print("=" * 60)
    print("Grid generation complete!")
    print("Sea routing is now available.")
    print("=" * 60)


if __name__ == "__main__":
    main()