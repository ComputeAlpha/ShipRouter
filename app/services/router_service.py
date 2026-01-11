"""
Router Service
Orchestrates hardware interfaces and core algorithms.
Main business logic layer.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Callable, Any
from threading import Thread, Event

from ..interfaces import SerialInterface, GPSData, SensorData, CombinedData
from ..core import (
    HarborManager, 
    Harbor,
    HarborWithDistance,
    FuelMonitor, 
    FuelMonitorState,
    NavigationResult,
    calculate_navigation,
    HAS_SEA_ROUTING
)

# Import sea routing if available
if HAS_SEA_ROUTING:
    from ..core import SeaRouter, SeaRoute, NavigationGuidance, get_sea_router
else:
    SeaRouter = None
    SeaRoute = None
    NavigationGuidance = None

from ..config import (
    ConnectionStatus, 
    SystemMode, 
    UPDATE_INTERVAL_SECONDS,
    SERIAL_PORT,
    SERIAL_BAUDRATE
)

logger = logging.getLogger(__name__)


@dataclass
class SystemState:
    """Complete system state snapshot"""
    # Connection
    serial_connected: bool = False
    connection_status: str = ConnectionStatus.DISCONNECTED
    
    # GPS
    gps_valid: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_knots: Optional[float] = None
    heading: Optional[float] = None
    satellites: int = 0
    
    # Fuel
    fuel_status: int = 1  # 1 = normal, 0 = low
    fuel_state: Optional[FuelMonitorState] = None
    
    # Navigation
    system_mode: str = SystemMode.NORMAL
    selected_harbor: Optional[str] = None
    destination: Optional[HarborWithDistance] = None
    nearest_harbors: List[HarborWithDistance] = field(default_factory=list)
    
    # Sea routing
    sea_routing_available: bool = False
    is_on_sea: bool = True
    terrain_type: str = "unknown"
    sea_route: Optional[dict] = None  # SeaRoute.to_dict()
    route_waypoints: List[dict] = field(default_factory=list)
    navigation_guidance: Optional[dict] = None  # NavigationGuidance.to_dict()
    
    # Embarkation (for land-to-sea routes)
    requires_embarkation: bool = False
    embarkation_harbor: Optional[str] = None
    embarkation_distance_km: float = 0.0
    embarkation_bearing: float = 0.0
    embarkation_cardinal: str = ""
    
    # Timestamps
    last_update: Optional[datetime] = None
    last_gps_update: Optional[datetime] = None
    last_sensor_update: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "connection": {
                "serial_connected": self.serial_connected,
                "status": self.connection_status
            },
            "gps": {
                "valid": self.gps_valid,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "speed_knots": self.speed_knots,
                "heading": self.heading,
                "satellites": self.satellites
            },
            "fuel": {
                "status": self.fuel_status,
                "is_low": self.fuel_status == 0,
                "state": self.fuel_state.to_dict() if self.fuel_state else None
            },
            "navigation": {
                "system_mode": self.system_mode,
                "selected_harbor": self.selected_harbor,
                "destination": self.destination.to_dict() if self.destination else None,
                "nearest_harbors": [h.to_dict() for h in self.nearest_harbors]
            },
            "sea_routing": {
                "available": self.sea_routing_available,
                "is_on_sea": self.is_on_sea,
                "terrain_type": self.terrain_type,
                "route": self.sea_route,
                "waypoints": self.route_waypoints,
                "guidance": self.navigation_guidance
            },
            "embarkation": {
                "required": self.requires_embarkation,
                "harbor": self.embarkation_harbor,
                "distance_km": round(self.embarkation_distance_km, 2),
                "bearing": round(self.embarkation_bearing, 1),
                "cardinal": self.embarkation_cardinal
            } if self.requires_embarkation else None,
            "timestamps": {
                "last_update": self.last_update.isoformat() if self.last_update else None,
                "last_gps": self.last_gps_update.isoformat() if self.last_gps_update else None,
                "last_sensor": self.last_sensor_update.isoformat() if self.last_sensor_update else None
            }
        }


class RouterService:
    """
    Main service that coordinates all system components.
    
    Responsibilities:
    - Manage serial connection lifecycle
    - Process incoming sensor and GPS data
    - Handle fuel monitoring and emergency mode
    - Calculate navigation to harbors
    - Broadcast state updates to subscribers
    """
    
    def __init__(
        self,
        serial_port: str = SERIAL_PORT,
        serial_baudrate: int = SERIAL_BAUDRATE,
        update_interval: float = UPDATE_INTERVAL_SECONDS
    ):
        # Components
        self._serial = SerialInterface(port=serial_port, baudrate=serial_baudrate)
        self._harbor_manager = HarborManager()
        self._fuel_monitor = FuelMonitor(
            on_emergency_trigger=self._on_emergency_triggered,
            on_emergency_clear=self._on_emergency_cleared
        )
        
        # Sea router (optional - may not be available)
        self._sea_router: Optional[SeaRouter] = None
        if HAS_SEA_ROUTING:
            try:
                self._sea_router = SeaRouter(auto_load=False)
            except Exception as e:
                logger.warning(f"Sea routing not available: {e}")
        
        # State
        self._state = SystemState()
        self._selected_harbor: Optional[str] = None
        self._update_interval = update_interval
        
        # Threading
        self._running = False
        self._stop_event = Event()
        self._read_thread: Optional[Thread] = None
        
        # Subscribers for state updates
        self._subscribers: List[Callable[[SystemState], Any]] = []
    
    def initialize(self) -> bool:
        """
        Initialize the service (load harbors, sea router, etc.)
        
        Returns:
            True if initialization successful
        """
        if not self._harbor_manager.load():
            logger.error("Failed to load harbors")
            return False
        
        # Initialize sea router if available
        if self._sea_router:
            if self._sea_router.initialize():
                self._state.sea_routing_available = True
                logger.info(f"Sea routing initialized with {self._sea_router.grid_node_count} nodes")
                
                # Pass harbor data to sea router for land-to-sea routing
                harbors = self._harbor_manager.get_all()
                harbor_tuples = [(h.name, h.latitude, h.longitude) for h in harbors]
                self._sea_router.set_harbors(harbor_tuples)
            else:
                logger.warning("Sea routing not initialized - geodata may be missing")
                self._state.sea_routing_available = False
        
        logger.info(f"RouterService initialized with {self._harbor_manager.count} harbors")
        return True
    
    def start(self) -> bool:
        """
        Start the service (connect serial, begin reading).
        
        Returns:
            True if started successfully
        """
        if self._running:
            return True
        
        # Try to connect serial
        if self._serial.connect():
            self._state.serial_connected = True
            self._state.connection_status = ConnectionStatus.CONNECTED
        else:
            self._state.serial_connected = False
            self._state.connection_status = ConnectionStatus.DISCONNECTED
            logger.warning("Serial connection failed - running in disconnected mode")
        
        # Start read thread
        self._running = True
        self._stop_event.clear()
        self._read_thread = Thread(target=self._read_loop, daemon=True)
        self._read_thread.start()
        
        logger.info("RouterService started")
        return True
    
    def stop(self) -> None:
        """Stop the service"""
        self._running = False
        self._stop_event.set()
        
        if self._read_thread:
            self._read_thread.join(timeout=2.0)
        
        self._serial.disconnect()
        self._state.serial_connected = False
        self._state.connection_status = ConnectionStatus.DISCONNECTED
        
        logger.info("RouterService stopped")
    
    def _read_loop(self) -> None:
        """Background thread for reading serial data"""
        while self._running and not self._stop_event.is_set():
            try:
                if self._serial.is_connected():
                    data = self._serial.read_data()
                    if data:
                        self._process_data(data)
                else:
                    # Try to reconnect
                    if self._serial.connect():
                        self._state.serial_connected = True
                        self._state.connection_status = ConnectionStatus.CONNECTED
                
                # Small sleep to prevent CPU spinning
                self._stop_event.wait(timeout=0.05)
                
            except Exception as e:
                logger.error(f"Error in read loop: {e}")
                self._stop_event.wait(timeout=1.0)
    
    def _process_data(self, data: CombinedData) -> None:
        """Process incoming combined data"""
        now = datetime.now()
        self._state.last_update = now
        
        # Process GPS data
        if data.gps:
            self._process_gps(data.gps, now)
        
        # Process sensor data
        if data.sensor:
            self._process_sensor(data.sensor, now)
        
        # Update navigation calculations
        self._update_navigation()
        
        # Notify subscribers
        self._notify_subscribers()
    
    def _process_gps(self, gps: GPSData, now: datetime) -> None:
        """Process GPS data"""
        self._state.gps_valid = gps.is_valid
        self._state.latitude = gps.latitude
        self._state.longitude = gps.longitude
        self._state.speed_knots = gps.speed_knots
        self._state.heading = gps.heading
        self._state.satellites = gps.satellites
        self._state.last_gps_update = now
    
    def _process_sensor(self, sensor: SensorData, now: datetime) -> None:
        """Process sensor data and update fuel monitor"""
        self._state.fuel_status = sensor.fuel_status
        self._state.fuel_state = self._fuel_monitor.update(sensor.fuel_status)
        self._state.system_mode = self._state.fuel_state.system_mode
        self._state.last_sensor_update = now
    
    def _update_navigation(self) -> None:
        """Update navigation calculations"""
        if not self._state.gps_valid:
            return
        
        lat = self._state.latitude
        lon = self._state.longitude
        
        # Check if on sea (if sea router available)
        if self._sea_router and self._sea_router.is_initialized:
            classification = self._sea_router.classify_position(lat, lon)
            self._state.is_on_sea = classification.is_sea
            self._state.terrain_type = classification.terrain_type
        
        # Always calculate nearest harbors
        self._state.nearest_harbors = self._harbor_manager.find_nearest(lat, lon)
        
        # Determine destination based on mode
        dest_harbor = None
        if self._state.system_mode == SystemMode.EMERGENCY:
            # In emergency mode, destination is the nearest harbor
            if self._state.nearest_harbors:
                self._state.destination = self._state.nearest_harbors[0]
                dest_harbor = self._state.nearest_harbors[0].harbor
        else:
            # In normal mode, use selected harbor
            if self._selected_harbor:
                self._state.destination = self._harbor_manager.calculate_distance_to(
                    self._selected_harbor, lat, lon
                )
                if self._state.destination:
                    dest_harbor = self._state.destination.harbor
            else:
                self._state.destination = None
                # Clear route when no destination
                if self._sea_router:
                    self._sea_router.clear_route()
        
        self._state.selected_harbor = self._selected_harbor
        
        # Calculate sea route if destination exists and sea routing available
        if dest_harbor and self._sea_router and self._sea_router.is_initialized:
            route = self._sea_router.plan_route(
                lat, lon,
                dest_harbor.latitude, dest_harbor.longitude,
                dest_harbor.name
            )
            
            if route.is_valid:
                self._state.sea_route = route.to_dict()
                
                # Get navigation guidance (includes next waypoint calculation)
                guidance = self._sea_router.get_guidance(lat, lon, route)
                self._state.navigation_guidance = guidance.to_dict()
                
                # Build REMAINING waypoints for display (current pos → remaining waypoints)
                # This ensures the route line always starts from current position
                remaining_waypoints = self._build_remaining_waypoints(
                    lat, lon, route, guidance
                )
                self._state.route_waypoints = remaining_waypoints
                
                # Get embarkation info from SeaRouter (it manages the state)
                embark = self._sea_router.embarkation_harbor
                if embark and not self._state.is_on_sea:
                    self._state.requires_embarkation = True
                    self._state.embarkation_harbor = embark[0]  # name
                    self._state.embarkation_distance_km = guidance.distance_to_embarkation_km
                    self._state.embarkation_bearing = guidance.bearing_to_embarkation
                    self._state.embarkation_cardinal = guidance.cardinal_to_embarkation
                else:
                    self._state.requires_embarkation = False
                    self._state.embarkation_harbor = None
                    self._state.embarkation_distance_km = 0.0
                    self._state.embarkation_bearing = 0.0
                    self._state.embarkation_cardinal = ""
            else:
                self._state.sea_route = None
                self._state.route_waypoints = []
                self._state.navigation_guidance = None
                self._state.requires_embarkation = False
                self._state.embarkation_harbor = None
        else:
            self._state.sea_route = None
            self._state.route_waypoints = []
            self._state.navigation_guidance = None
            self._state.requires_embarkation = False
            self._state.embarkation_harbor = None
    
    def _build_remaining_waypoints(
        self, 
        current_lat: float, 
        current_lon: float, 
        route, 
        guidance
    ) -> List[dict]:
        """
        Build list of remaining waypoints starting from current position.
        This ensures the displayed route always starts from vessel location.
        """
        from ..core.navigation import haversine_distance
        
        remaining = []
        
        # Always start with current position
        remaining.append({
            "lat": current_lat,
            "lon": current_lon,
            "is_origin": True,
            "is_current_position": True
        })
        
        # Find and add remaining waypoints (skip passed ones)
        found_next = False
        for wp in route.waypoints:
            if wp.is_origin:
                continue  # Skip original origin
            
            dist = haversine_distance(current_lat, current_lon, wp.lat, wp.lon)
            
            # Include waypoint if not yet reached (>500m away)
            if dist > 0.5:
                found_next = True
                remaining.append(wp.to_dict())
            elif not found_next:
                # This waypoint has been passed, skip it
                continue
        
        return remaining
    
    def _on_emergency_triggered(self) -> None:
        """Callback when emergency mode is triggered"""
        logger.warning("Emergency mode triggered - auto-selecting nearest harbor")
        # The nearest harbor will be auto-selected in _update_navigation
    
    def _on_emergency_cleared(self) -> None:
        """Callback when emergency mode is cleared"""
        logger.info("Emergency mode cleared")
    
    def select_harbor(self, harbor_name: str) -> bool:
        """
        Select a harbor as navigation destination.
        Only works in normal mode.
        
        Args:
            harbor_name: Name of harbor to select
        
        Returns:
            True if selection successful
        """
        if self._state.system_mode == SystemMode.EMERGENCY:
            logger.warning("Cannot select harbor in emergency mode")
            return False
        
        harbor = self._harbor_manager.get_by_name(harbor_name)
        if not harbor:
            logger.warning(f"Harbor not found: {harbor_name}")
            return False
        
        self._selected_harbor = harbor_name
        self._update_navigation()
        self._notify_subscribers()
        
        logger.info(f"Selected harbor: {harbor_name}")
        return True
    
    def clear_selection(self) -> None:
        """Clear harbor selection"""
        self._selected_harbor = None
        self._state.destination = None
        self._notify_subscribers()
    
    def acknowledge_emergency(self) -> bool:
        """
        Acknowledge and exit emergency mode.
        
        Returns:
            True if acknowledgment accepted
        """
        result = self._fuel_monitor.acknowledge_emergency()
        if result:
            self._state.fuel_state = self._fuel_monitor.get_state()
            self._state.system_mode = SystemMode.NORMAL
            self._notify_subscribers()
        return result
    
    def subscribe(self, callback: Callable[[SystemState], Any]) -> None:
        """Subscribe to state updates"""
        self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[SystemState], Any]) -> None:
        """Unsubscribe from state updates"""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
    
    def _notify_subscribers(self) -> None:
        """Notify all subscribers of state change"""
        for callback in self._subscribers:
            try:
                callback(self._state)
            except Exception as e:
                logger.error(f"Error notifying subscriber: {e}")
    
    def get_state(self) -> SystemState:
        """Get current system state"""
        return self._state
    
    def get_all_harbors(self) -> List[Harbor]:
        """Get all available harbors"""
        return self._harbor_manager.get_all()
    
    def get_harbors_with_distances(self) -> List[HarborWithDistance]:
        """Get all harbors with distances from current position"""
        if not self._state.gps_valid:
            return []
        return self._harbor_manager.get_all_with_distances(
            self._state.latitude,
            self._state.longitude
        )
    
    @property
    def is_running(self) -> bool:
        """Check if service is running"""
        return self._running
    
    @property
    def harbor_manager(self) -> HarborManager:
        """Access to harbor manager"""
        return self._harbor_manager
    
    @property
    def fuel_monitor(self) -> FuelMonitor:
        """Access to fuel monitor"""
        return self._fuel_monitor
    
    @property
    def sea_router(self) -> Optional['SeaRouter']:
        """Access to sea router (may be None if not available)"""
        return self._sea_router
    
    @property
    def sea_routing_available(self) -> bool:
        """Check if sea routing is available"""
        return self._sea_router is not None and self._sea_router.is_initialized


# Singleton instance for easy access
_router_service: Optional[RouterService] = None


def get_router_service() -> RouterService:
    """Get or create the singleton RouterService instance"""
    global _router_service
    if _router_service is None:
        _router_service = RouterService()
    return _router_service


def initialize_router_service(**kwargs) -> RouterService:
    """Initialize the singleton RouterService with custom parameters"""
    global _router_service
    _router_service = RouterService(**kwargs)
    return _router_service