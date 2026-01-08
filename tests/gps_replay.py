"""
GPS Coordinate Replay Tool
Replays a predefined route for testing navigation.

Supports:
- Predefined demo routes
- Custom waypoint files
- Variable speed playback
- Loop/one-shot modes

Usage:
    python -m tests.gps_replay --route coastal_tour
    python -m tests.gps_replay --waypoints custom_route.csv
"""

import argparse
import csv
import json
import logging
import math
import os
import pty
import signal
import sys
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Waypoint:
    """A point along a route"""
    name: str
    lat: float
    lon: float
    
    def distance_to(self, other: 'Waypoint') -> float:
        """Calculate distance in km using Haversine"""
        R = 6371.0
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(other.lat), math.radians(other.lon)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def bearing_to(self, other: 'Waypoint') -> float:
        """Calculate bearing in degrees"""
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(other.lat), math.radians(other.lon)
        
        dlon = lon2 - lon1
        
        x = math.sin(dlon) * math.cos(lat2)
        y = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlon)
        
        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360) % 360


# =============================================================================
# Predefined Demo Routes
# =============================================================================

DEMO_ROUTES = {
    "coastal_tour": [
        Waypoint("Chennai Port", 13.0827, 80.2871),
        Waypoint("Ennore Approach", 13.1800, 80.3100),
        Waypoint("Kattupalli", 13.2632, 80.3172),
        Waypoint("Pulicat Lake", 13.4200, 80.3300),
        Waypoint("Return South", 13.2000, 80.3000),
        Waypoint("Chennai Port", 13.0827, 80.2871),
    ],
    "harbor_hop": [
        Waypoint("Chennai Port", 13.0827, 80.2871),
        Waypoint("Mamallapuram", 12.6269, 80.1927),
        Waypoint("Puducherry", 11.9416, 79.8083),
        Waypoint("Cuddalore", 11.7480, 79.7714),
        Waypoint("Return", 12.5000, 80.0000),
        Waypoint("Chennai Port", 13.0827, 80.2871),
    ],
    "emergency_test": [
        Waypoint("Start - Far from harbors", 12.0000, 79.5000),
        Waypoint("Moving towards coast", 12.2000, 79.7000),
        Waypoint("Near Puducherry", 11.9500, 79.8000),
        Waypoint("Emergency area", 11.8000, 79.7500),
    ],
    "short_demo": [
        Waypoint("Start", 13.0827, 80.2871),
        Waypoint("Point A", 13.1000, 80.3000),
        Waypoint("Point B", 13.0900, 80.2900),
        Waypoint("End", 13.0827, 80.2871),
    ]
}


class GPSReplayTool:
    """
    Replays GPS coordinates along a route.
    Creates a virtual serial port with NMEA output.
    """
    
    def __init__(
        self,
        waypoints: List[Waypoint],
        speed_kmh: float = 30.0,
        update_rate_hz: float = 5.0,
        loop: bool = True
    ):
        self.waypoints = waypoints
        self.speed_kmh = speed_kmh
        self.update_rate_hz = update_rate_hz
        self.update_interval = 1.0 / update_rate_hz
        self.loop = loop
        
        # Current state
        self.current_waypoint_idx = 0
        self.progress = 0.0  # 0.0 to 1.0 between waypoints
        self.current_lat = waypoints[0].lat
        self.current_lon = waypoints[0].lon
        self.current_heading = 0.0
        self.satellites = 8
        
        self.fuel_status = 1
        self.running = False
        
        # Virtual serial port
        self.master_fd: Optional[int] = None
        self.slave_path: Optional[str] = None
    
    def create_virtual_port(self) -> str:
        """Create virtual serial port"""
        master, slave = pty.openpty()
        self.master_fd = master
        self.slave_path = os.ttyname(slave)
        
        symlink = "/tmp/ttyVUSB0"
        try:
            if os.path.islink(symlink):
                os.unlink(symlink)
            os.symlink(self.slave_path, symlink)
            return symlink
        except OSError:
            return self.slave_path
    
    def update_position(self) -> None:
        """Update position along the route"""
        if self.current_waypoint_idx >= len(self.waypoints) - 1:
            if self.loop:
                self.current_waypoint_idx = 0
                self.progress = 0.0
            else:
                return
        
        current_wp = self.waypoints[self.current_waypoint_idx]
        next_wp = self.waypoints[self.current_waypoint_idx + 1]
        
        # Calculate segment distance
        segment_dist = current_wp.distance_to(next_wp)
        
        # Calculate how far we travel in this update
        distance_per_update = (self.speed_kmh / 3600.0) * self.update_interval
        
        if segment_dist > 0:
            progress_increment = distance_per_update / segment_dist
            self.progress += progress_increment
        else:
            self.progress = 1.0
        
        # Check if we've reached the next waypoint
        if self.progress >= 1.0:
            self.current_waypoint_idx += 1
            self.progress = 0.0
            
            if self.current_waypoint_idx >= len(self.waypoints) - 1:
                if self.loop:
                    logger.info("Route complete, looping...")
                else:
                    logger.info("Route complete")
                    return
            
            logger.info(f"Reached: {self.waypoints[self.current_waypoint_idx].name}")
        
        # Interpolate position
        if self.current_waypoint_idx < len(self.waypoints) - 1:
            current_wp = self.waypoints[self.current_waypoint_idx]
            next_wp = self.waypoints[self.current_waypoint_idx + 1]
            
            self.current_lat = current_wp.lat + (next_wp.lat - current_wp.lat) * self.progress
            self.current_lon = current_wp.lon + (next_wp.lon - current_wp.lon) * self.progress
            self.current_heading = current_wp.bearing_to(next_wp)
    
    def generate_nmea(self) -> str:
        """Generate NMEA sentence"""
        from datetime import datetime
        now = datetime.utcnow()
        time_str = now.strftime("%H%M%S.00")
        date_str = now.strftime("%d%m%y")
        
        # Latitude
        lat_deg = int(abs(self.current_lat))
        lat_min = (abs(self.current_lat) - lat_deg) * 60
        lat_str = f"{lat_deg:02d}{lat_min:07.4f}"
        lat_dir = 'N' if self.current_lat >= 0 else 'S'
        
        # Longitude
        lon_deg = int(abs(self.current_lon))
        lon_min = (abs(self.current_lon) - lon_deg) * 60
        lon_str = f"{lon_deg:03d}{lon_min:07.4f}"
        lon_dir = 'E' if self.current_lon >= 0 else 'W'
        
        # Speed in knots
        speed_knots = self.speed_kmh / 1.852
        
        # RMC sentence
        sentence = f"GPRMC,{time_str},A,{lat_str},{lat_dir},{lon_str},{lon_dir},{speed_knots:.1f},{self.current_heading:.1f},{date_str},0.0,E"
        
        checksum = 0
        for c in sentence:
            checksum ^= ord(c)
        
        return f"${sentence}*{checksum:02X}"
    
    def send_packet(self) -> None:
        """Send JSON packet"""
        if self.master_fd is None:
            return
        
        self.update_position()
        nmea = self.generate_nmea()
        
        packet = json.dumps({"fuel": self.fuel_status, "nmea": nmea}) + "\n"
        
        try:
            os.write(self.master_fd, packet.encode())
        except OSError as e:
            logger.error(f"Write error: {e}")
    
    def run(self) -> None:
        """Main loop"""
        self.running = True
        logger.info(f"Starting replay: {len(self.waypoints)} waypoints at {self.speed_kmh} km/h")
        
        # Input thread
        input_thread = threading.Thread(target=self._input_handler, daemon=True)
        input_thread.start()
        
        try:
            while self.running:
                self.send_packet()
                time.sleep(self.update_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
    
    def _input_handler(self) -> None:
        """Handle keyboard commands"""
        while self.running:
            try:
                cmd = input().strip().lower()
                if cmd == 'f':
                    self.fuel_status = 1 - self.fuel_status
                    logger.info(f"Fuel: {'NORMAL' if self.fuel_status else 'LOW'}")
                elif cmd == 'q':
                    self.running = False
                elif cmd == 's':
                    wp = self.waypoints[self.current_waypoint_idx]
                    logger.info(f"Position: {self.current_lat:.5f}, {self.current_lon:.5f}")
                    logger.info(f"Near: {wp.name}, Progress: {self.progress:.1%}")
                elif cmd.startswith('speed '):
                    try:
                        self.speed_kmh = float(cmd.split()[1])
                        logger.info(f"Speed set to {self.speed_kmh} km/h")
                    except (IndexError, ValueError):
                        pass
            except EOFError:
                break
    
    def stop(self) -> None:
        """Clean up"""
        self.running = False
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
        try:
            if os.path.islink("/tmp/ttyVUSB0"):
                os.unlink("/tmp/ttyVUSB0")
        except OSError:
            pass
        logger.info("Replay stopped")


def load_waypoints_from_csv(filepath: str) -> List[Waypoint]:
    """Load waypoints from CSV file"""
    waypoints = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            waypoints.append(Waypoint(
                name=row.get('name', f"Point {len(waypoints)+1}"),
                lat=float(row['latitude']),
                lon=float(row['longitude'])
            ))
    return waypoints


def main():
    parser = argparse.ArgumentParser(description="GPS Coordinate Replay Tool")
    parser.add_argument(
        "--route", choices=list(DEMO_ROUTES.keys()),
        help="Predefined demo route"
    )
    parser.add_argument(
        "--waypoints", type=str,
        help="Path to CSV file with waypoints"
    )
    parser.add_argument(
        "--speed", type=float, default=30.0,
        help="Speed in km/h (default: 30)"
    )
    parser.add_argument(
        "--rate", type=float, default=5.0,
        help="Update rate in Hz (default: 5)"
    )
    parser.add_argument(
        "--no-loop", action="store_true",
        help="Don't loop the route"
    )
    parser.add_argument(
        "--list-routes", action="store_true",
        help="List available demo routes"
    )
    
    args = parser.parse_args()
    
    if args.list_routes:
        print("\nAvailable Demo Routes:")
        print("-" * 40)
        for name, waypoints in DEMO_ROUTES.items():
            print(f"\n{name}:")
            for wp in waypoints:
                print(f"  - {wp.name} ({wp.lat:.4f}, {wp.lon:.4f})")
        return
    
    # Load waypoints
    if args.waypoints:
        waypoints = load_waypoints_from_csv(args.waypoints)
    elif args.route:
        waypoints = DEMO_ROUTES[args.route]
    else:
        # Default to short demo
        waypoints = DEMO_ROUTES["short_demo"]
    
    tool = GPSReplayTool(
        waypoints=waypoints,
        speed_kmh=args.speed,
        update_rate_hz=args.rate,
        loop=not args.no_loop
    )
    
    # Signal handlers
    def signal_handler(sig, frame):
        tool.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run
    port = tool.create_virtual_port()
    print(f"\n{'='*60}")
    print(f"GPS Replay Tool")
    print(f"{'='*60}")
    print(f"Virtual Port: {port}")
    print(f"Route:        {len(waypoints)} waypoints")
    print(f"Speed:        {args.speed} km/h")
    print(f"Loop:         {'Yes' if not args.no_loop else 'No'}")
    print(f"{'='*60}")
    print("Commands: f=toggle fuel, s=status, speed N=set speed, q=quit")
    print(f"{'='*60}\n")
    
    tool.run()


if __name__ == "__main__":
    main()