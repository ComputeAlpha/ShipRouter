"""
Mock Serial Emulator
Simulates Arduino output for testing without hardware.

Creates a virtual serial port pair using socat or pty.
Sends simulated fuel status and GPS NMEA data.

Usage:
    python -m tests.mock_serial_emulator

    # In another terminal, run the server pointing to the virtual port:
    # Edit config.py: SERIAL_PORT = "/tmp/ttyVUSB0"
"""

import argparse
import json
import logging
import os
import pty
import random
import signal
import sys
import threading
import time
from datetime import datetime
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GPSSimulator:
    """Simulates GPS movement along a path"""
    
    def __init__(
        self,
        start_lat: float = 13.0827,
        start_lon: float = 80.2871,
        speed_kmh: float = 20.0
    ):
        self.lat = start_lat
        self.lon = start_lon
        self.speed_kmh = speed_kmh
        self.heading = random.uniform(0, 360)
        self.satellites = random.randint(6, 12)
        self.fix_quality = 1
        
        # Movement parameters
        self.heading_change_rate = 5.0  # degrees per update
        self.last_update = time.time()
    
    def update(self) -> None:
        """Update position based on speed and heading"""
        now = time.time()
        dt = now - self.last_update
        self.last_update = now
        
        # Convert speed to degrees per second (approximate)
        speed_deg_per_sec = self.speed_kmh / 111.0 / 3600.0
        
        # Calculate movement
        import math
        heading_rad = math.radians(self.heading)
        dlat = speed_deg_per_sec * math.cos(heading_rad) * dt
        dlon = speed_deg_per_sec * math.sin(heading_rad) * dt
        
        self.lat += dlat
        self.lon += dlon
        
        # Slowly change heading (simulate realistic movement)
        self.heading += random.uniform(-self.heading_change_rate, self.heading_change_rate) * dt
        self.heading = self.heading % 360
        
        # Occasionally vary satellites
        if random.random() < 0.1:
            self.satellites = max(4, min(12, self.satellites + random.randint(-1, 1)))
    
    def generate_gpgga(self) -> str:
        """Generate GPGGA NMEA sentence"""
        now = datetime.utcnow()
        time_str = now.strftime("%H%M%S.00")
        
        # Convert latitude to NMEA format (ddmm.mmmm)
        lat_deg = int(abs(self.lat))
        lat_min = (abs(self.lat) - lat_deg) * 60
        lat_str = f"{lat_deg:02d}{lat_min:07.4f}"
        lat_dir = 'N' if self.lat >= 0 else 'S'
        
        # Convert longitude to NMEA format (dddmm.mmmm)
        lon_deg = int(abs(self.lon))
        lon_min = (abs(self.lon) - lon_deg) * 60
        lon_str = f"{lon_deg:03d}{lon_min:07.4f}"
        lon_dir = 'E' if self.lon >= 0 else 'W'
        
        # Build sentence without checksum
        sentence = f"GPGGA,{time_str},{lat_str},{lat_dir},{lon_str},{lon_dir},{self.fix_quality},{self.satellites:02d},0.9,10.0,M,0.0,M,,"
        
        # Calculate checksum
        checksum = 0
        for c in sentence:
            checksum ^= ord(c)
        
        return f"${sentence}*{checksum:02X}"
    
    def generate_gprmc(self) -> str:
        """Generate GPRMC NMEA sentence"""
        now = datetime.utcnow()
        time_str = now.strftime("%H%M%S.00")
        date_str = now.strftime("%d%m%y")
        
        # Convert latitude
        lat_deg = int(abs(self.lat))
        lat_min = (abs(self.lat) - lat_deg) * 60
        lat_str = f"{lat_deg:02d}{lat_min:07.4f}"
        lat_dir = 'N' if self.lat >= 0 else 'S'
        
        # Convert longitude
        lon_deg = int(abs(self.lon))
        lon_min = (abs(self.lon) - lon_deg) * 60
        lon_str = f"{lon_deg:03d}{lon_min:07.4f}"
        lon_dir = 'E' if self.lon >= 0 else 'W'
        
        # Speed in knots
        speed_knots = self.speed_kmh / 1.852
        
        # Build sentence
        sentence = f"GPRMC,{time_str},A,{lat_str},{lat_dir},{lon_str},{lon_dir},{speed_knots:.1f},{self.heading:.1f},{date_str},0.0,E"
        
        # Calculate checksum
        checksum = 0
        for c in sentence:
            checksum ^= ord(c)
        
        return f"${sentence}*{checksum:02X}"


class MockSerialEmulator:
    """
    Emulates Arduino serial output.
    Creates a virtual serial port for the server to connect to.
    """
    
    def __init__(
        self,
        update_rate_hz: float = 5.0,
        start_lat: float = 13.0827,
        start_lon: float = 80.2871
    ):
        self.update_rate_hz = update_rate_hz
        self.update_interval = 1.0 / update_rate_hz
        
        self.gps = GPSSimulator(start_lat, start_lon)
        
        self.fuel_status = 1  # 1 = normal, 0 = low
        self.running = False
        
        # Virtual serial port
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.slave_path: Optional[str] = None
    
    def create_virtual_port(self) -> str:
        """Create a virtual serial port pair"""
        self.master_fd, self.slave_fd = pty.openpty()
        self.slave_path = os.ttyname(self.slave_fd)
        
        # Create a symlink for easier access
        symlink_path = "/tmp/ttyVUSB0"
        try:
            if os.path.islink(symlink_path):
                os.unlink(symlink_path)
            os.symlink(self.slave_path, symlink_path)
            logger.info(f"Virtual serial port: {symlink_path} -> {self.slave_path}")
        except OSError as e:
            logger.warning(f"Could not create symlink: {e}")
            logger.info(f"Virtual serial port: {self.slave_path}")
        
        return symlink_path if os.path.exists(symlink_path) else self.slave_path
    
    def set_fuel_status(self, status: int) -> None:
        """Set fuel status (1 = normal, 0 = low)"""
        self.fuel_status = 1 if status else 0
        logger.info(f"Fuel status set to: {'NORMAL' if self.fuel_status else 'LOW'}")
    
    def toggle_fuel_status(self) -> None:
        """Toggle fuel status"""
        self.fuel_status = 1 - self.fuel_status
        logger.info(f"Fuel status toggled to: {'NORMAL' if self.fuel_status else 'LOW'}")
    
    def send_packet(self) -> None:
        """Send a JSON packet to the virtual serial port"""
        if self.master_fd is None:
            return
        
        # Update GPS position
        self.gps.update()
        
        # Alternate between GGA and RMC sentences
        if random.random() < 0.5:
            nmea = self.gps.generate_gpgga()
        else:
            nmea = self.gps.generate_gprmc()
        
        # Build JSON packet
        packet = {
            "fuel": self.fuel_status,
            "nmea": nmea
        }
        
        data = json.dumps(packet) + "\n"
        
        try:
            os.write(self.master_fd, data.encode())
        except OSError as e:
            logger.error(f"Write error: {e}")
    
    def run(self) -> None:
        """Main loop - send packets at configured rate"""
        self.running = True
        logger.info(f"Emulator running at {self.update_rate_hz} Hz")
        logger.info("Commands: 'f' = toggle fuel, 'q' = quit")
        
        # Start input thread for commands
        input_thread = threading.Thread(target=self._input_handler, daemon=True)
        input_thread.start()
        
        try:
            while self.running:
                self.send_packet()
                time.sleep(self.update_interval)
        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            self.stop()
    
    def _input_handler(self) -> None:
        """Handle keyboard input for commands"""
        while self.running:
            try:
                cmd = input().strip().lower()
                if cmd == 'f':
                    self.toggle_fuel_status()
                elif cmd == 'q':
                    self.running = False
                elif cmd == 'l':
                    self.set_fuel_status(0)  # Set to LOW
                elif cmd == 'n':
                    self.set_fuel_status(1)  # Set to NORMAL
                elif cmd == 'h':
                    print("Commands: f=toggle, l=low, n=normal, q=quit")
            except EOFError:
                break
    
    def stop(self) -> None:
        """Stop the emulator and clean up"""
        self.running = False
        
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
        
        if self.slave_fd:
            try:
                os.close(self.slave_fd)
            except OSError:
                pass
        
        # Remove symlink
        try:
            if os.path.islink("/tmp/ttyVUSB0"):
                os.unlink("/tmp/ttyVUSB0")
        except OSError:
            pass
        
        logger.info("Emulator stopped")


def main():
    parser = argparse.ArgumentParser(description="Mock Serial Emulator for ShipRouter")
    parser.add_argument(
        "--rate", type=float, default=5.0,
        help="Update rate in Hz (default: 5.0)"
    )
    parser.add_argument(
        "--lat", type=float, default=13.0827,
        help="Starting latitude (default: 13.0827 - Chennai)"
    )
    parser.add_argument(
        "--lon", type=float, default=80.2871,
        help="Starting longitude (default: 80.2871 - Chennai)"
    )
    parser.add_argument(
        "--fuel-low", action="store_true",
        help="Start with fuel status LOW"
    )
    
    args = parser.parse_args()
    
    emulator = MockSerialEmulator(
        update_rate_hz=args.rate,
        start_lat=args.lat,
        start_lon=args.lon
    )
    
    if args.fuel_low:
        emulator.set_fuel_status(0)
    
    # Handle signals
    def signal_handler(sig, frame):
        emulator.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create virtual port and run
    port = emulator.create_virtual_port()
    print(f"\n{'='*60}")
    print(f"Mock Serial Emulator Running")
    print(f"{'='*60}")
    print(f"Virtual Port: {port}")
    print(f"Update Rate:  {args.rate} Hz")
    print(f"Start Pos:    {args.lat}, {args.lon}")
    print(f"{'='*60}")
    print("Update app/config.py:")
    print(f'  SERIAL_PORT = "{port}"')
    print(f"{'='*60}")
    print("Commands: f=toggle fuel, l=low, n=normal, h=help, q=quit")
    print(f"{'='*60}\n")
    
    emulator.run()


if __name__ == "__main__":
    main()