"""
ShipRouter Configuration
All configurable parameters in one place
"""

from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================
BASE_DIR = Path(__file__).parent.parent
DATASET_DIR = BASE_DIR / "dataset"
HARBORS_CSV = DATASET_DIR / "harbors.csv"

# =============================================================================
# SERIAL COMMUNICATION
# =============================================================================
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 115200
SERIAL_TIMEOUT = 1.0  # seconds

# =============================================================================
# TIMING
# =============================================================================
FUEL_DEBOUNCE_SECONDS = 2.0  # Low fuel must persist this long to trigger emergency
UPDATE_INTERVAL_SECONDS = 0.5  # Navigation recalculation interval

# =============================================================================
# NAVIGATION
# =============================================================================
EARTH_RADIUS_KM = 6371.0
TOP_N_HARBORS = 3  # Number of nearest harbors to return

# =============================================================================
# FUEL STATUS CODES
# =============================================================================
class FuelStatus:
    NORMAL = 1
    LOW = 0

# =============================================================================
# SYSTEM MODES
# =============================================================================
class SystemMode:
    NORMAL = "normal"
    EMERGENCY = "emergency"

# =============================================================================
# CONNECTION STATUS
# =============================================================================
class ConnectionStatus:
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"

# =============================================================================
# SERVER
# =============================================================================
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000