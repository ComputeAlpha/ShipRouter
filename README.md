# ShipRouter - Marine Fuel Monitoring & Navigation System

A real-time marine navigation system with fuel monitoring, emergency routing, and intelligent sea path planning. Designed to run on Raspberry Pi with Arduino-based sensor integration.

![System Mode](https://img.shields.io/badge/Mode-Normal%20%7C%20Emergency-blue)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205-red)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Table of Contents

- [Features](#features)
- [System Architecture](#system-architecture)
- [Hardware Requirements](#hardware-requirements)
- [Software Requirements](#software-requirements)
- [Installation](#installation)
- [Sea Routing Setup](#sea-routing-setup)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Features

### Core Features
- **Real-time GPS Tracking** - Live vessel position on interactive map
- **Fuel Level Monitoring** - Binary fuel status with debounced alerts
- **Harbor Navigation** - Distance and bearing to selected destination
- **Nearest Harbor Finder** - Automatically finds closest harbors

### Emergency System
- **Automatic Emergency Mode** - Triggers when fuel drops below threshold
- **Auto-routing to Nearest Harbor** - Immediate redirection in emergencies
- **Visual & Audio Alerts** - Clear emergency indicators
- **Acknowledgment System** - Requires user confirmation to exit emergency

### Sea Routing (Advanced)
- **Land/Sea Detection** - Knows if vessel is on water or land
- **A* Pathfinding** - Optimal sea routes avoiding land masses
- **Land-to-Sea Routing** - Navigates from land to nearest harbor, then sea route
- **Turn-by-turn Waypoints** - Intermediate navigation points
- **Actual Sea Distance** - Route distance accounting for land avoidance

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          RASPBERRY PI 5                                  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    FastAPI Web Server (Python)                      │ │
│  │  • WebSocket for real-time updates    • REST API endpoints         │ │
│  │  • Leaflet.js map interface           • Static file serving        │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                   ↕                                      │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                     RouterService (Core Logic)                      │ │
│  │  • State management                   • Mode controller             │ │
│  │  • Navigation calculations            • Emergency handling          │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                   ↕                                      │
│  ┌──────────────────────┐    ┌────────────────────────────────────────┐ │
│  │    SeaRouter         │    │         Core Algorithms                │ │
│  │  • GeoClassifier     │    │  • Haversine distance                  │ │
│  │  • NavigationGrid    │    │  • Bearing calculation                 │ │
│  │  • A* RouteEngine    │    │  • Harbor management                   │ │
│  │  • Land-to-sea logic │    │  • Fuel monitoring                     │ │
│  └──────────────────────┘    └────────────────────────────────────────┘ │
│                                   ↕                                      │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    Serial Interface (JSON @ 5Hz)                    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                   ↕                                      │
└───────────────────────────────────╂─────────────────────────────────────┘
                                    ║ USB Serial
                    ┌───────────────╨───────────────┐
                    │       ARDUINO NANO R4         │
                    │  • GPS NMEA parsing           │
                    │  • Fuel sensor reading        │
                    │  • RGB LED status             │
                    │  • JSON packet output         │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
              ┌─────┴─────┐                 ┌───────┴───────┐
              │ GPS/GNSS  │                 │  Fuel Sensor  │
              │  Module   │                 │ (Capacitive)  │
              └───────────┘                 └───────────────┘
```

---

## Hardware Requirements

| Component | Model | Purpose |
|-----------|-------|---------|
| **Single Board Computer** | Raspberry Pi 5 (4GB+) | Main processing unit |
| **Microcontroller** | Arduino Nano R4 (Renesas) | Sensor interface |
| **GPS Module** | SkyTraq/Quectel with NMEA output | Position tracking |
| **Fuel Sensor** | DFRobot Capacitive Liquid Level | Fuel detection |
| **Storage** | 32GB+ microSD | OS and data |
| **Power** | 5V 3A USB-C | Pi power supply |

### Wiring Diagram

```
Arduino Nano R4 Connections:
├── USB ────────────────→ Raspberry Pi USB Port
├── Pin 0 (RX1) ←─────── GPS TX
├── Pin 1 (TX1) ────────→ GPS RX  
├── Pin 8 (D8) ←──────── Fuel Sensor SIGNAL
├── Pin 9 (D9) ─────────→ Fuel Sensor MODE (→ GND for Mode 0)
├── 5V ─────────────────→ GPS VCC, Sensor VCC
└── GND ────────────────→ Common Ground
```

---

## Software Requirements

### Raspberry Pi
- Raspbian OS (64-bit recommended)
- Python 3.10+
- pip package manager

### Python Dependencies
```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
websockets>=12.0
pyserial>=3.5
pynmea2>=1.19.0
pydantic>=2.5.0

# For sea routing (optional)
shapely>=2.0.0
fiona>=1.9.0
pyproj>=3.6.0
```

---

## Installation

### 1. Clone/Copy Project
```bash
cd ~
# Copy ShipRouter folder to home directory
```

### 2. Install Python Dependencies
```bash
cd ~/ShipRouter
pip install -r requirements.txt --break-system-packages
```

### 3. Configure Serial Port
Edit `app/config.py`:
```python
SERIAL_PORT = "/dev/ttyUSB0"  # Or /dev/ttyACM0
SERIAL_BAUDRATE = 115200
```

### 4. Add Harbor Data
Edit `dataset/harbors.csv`:
```csv
name,latitude,longitude,description
Chennai Port,13.0827,80.2707,Major port in Tamil Nadu
Kochi Port,9.9312,76.2673,Major port in Kerala
Mumbai Port,18.9388,72.8354,Largest port in India
```

### 5. Flash Arduino Firmware
1. Open `sensor_src/ShipRouter_Firmware/ShipRouter_Firmware.ino` in Arduino IDE
2. Select Board: "Arduino Nano R4"
3. Upload firmware

### 6. Run the Server
```bash
cd ~/ShipRouter
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 7. Access Web Interface
Open browser: `http://<pi-ip-address>:8000`

---

## Sea Routing Setup

Sea routing enables intelligent path planning that avoids land masses. This is **optional** but recommended for realistic navigation.

### 1. Download Coastline Data
```bash
cd ~/ShipRouter/dataset/geodata
wget https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip
unzip ne_10m_land.zip
```

### 2. Install Geo Dependencies
```bash
pip install shapely fiona pyproj --break-system-packages
```

### 3. Generate Navigation Grid
This creates a pre-computed mesh of navigable sea points (~5-10 minutes):
```bash
cd ~/ShipRouter
python tools/generate_grid.py --resolution 10
```

### 4. Restart Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Sea Routing Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       SEA ROUTING SYSTEM                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐     ┌─────────────────┐                    │
│  │  GeoClassifier  │     │ NavigationGrid  │                    │
│  │                 │     │                 │                    │
│  │ • Load shapefile│     │ • 10km resolution│                   │
│  │ • Point-in-poly │     │ • ~5000+ nodes  │                    │
│  │ • Land/Sea test │     │ • 8-way connections│                 │
│  └────────┬────────┘     └────────┬────────┘                    │
│           │                       │                              │
│           └───────────┬───────────┘                              │
│                       ▼                                          │
│            ┌─────────────────────┐                               │
│            │    RouteEngine      │                               │
│            │                     │                               │
│            │ • A* pathfinding    │                               │
│            │ • Path simplification│                              │
│            │ • Distance calc     │                               │
│            └──────────┬──────────┘                               │
│                       ▼                                          │
│            ┌─────────────────────┐                               │
│            │     SeaRouter       │                               │
│            │                     │                               │
│            │ • Route planning    │                               │
│            │ • Land-to-sea logic │                               │
│            │ • Guidance updates  │                               │
│            └─────────────────────┘                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### How Land-to-Sea Routing Works

When the vessel is on **land** (e.g., Coimbatore):

1. **Detect terrain** → System identifies position is on land
2. **Find embarkation point** → Nearest harbor (e.g., Kochi)
3. **Plan composite route**:
   - Land segment: Current position → Embarkation harbor (straight line)
   - Sea segment: Embarkation harbor → Destination (A* through grid)
4. **Display guidance** → Shows embarkation info + full route

```
[Land Position] ──straight line──→ [Embarkation Harbor] ══sea route══→ [Destination]
   Coimbatore                           Kochi Port                      Chennai Port
```

### Coverage Region

Default configuration covers **South Asian waters**:
- Latitude: -5° to 23° N
- Longitude: 68° to 95° E
- Includes: Bay of Bengal, Arabian Sea, Indian Ocean (around India/Sri Lanka)

To change region, edit `app/core/sea_router.py`:
```python
SOUTH_ASIA_BOUNDS = {
    "min_lat": -5.0,
    "max_lat": 23.0,
    "min_lon": 68.0,
    "max_lon": 95.0
}
```

Then regenerate grid:
```bash
python tools/generate_grid.py --resolution 10
```

---

## Configuration

### Main Configuration (`app/config.py`)

```python
# Serial Communication
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 115200

# Timing
FUEL_DEBOUNCE_SECONDS = 2.0      # Seconds of low fuel before emergency
UPDATE_INTERVAL_SECONDS = 0.5    # UI update rate

# Navigation
TOP_N_HARBORS = 3                # Number of nearest harbors to show

# Paths
DATASET_DIR = Path(__file__).parent.parent / "dataset"
HARBOR_CSV = DATASET_DIR / "harbors.csv"
```

### Harbor Database (`dataset/harbors.csv`)

```csv
name,latitude,longitude,description
Chennai Port,13.0827,80.2707,Major commercial port
Tuticorin Port,8.7642,78.1348,Second largest port in Tamil Nadu
Kochi Port,9.9312,76.2673,Natural harbor in Kerala
Visakhapatnam Port,17.6868,83.2185,Deepest port in India
```

---

## Usage

### Normal Mode
1. Select destination harbor from dropdown
2. View distance and bearing in Navigation panel
3. Follow route line on map
4. If on land, embarkation point shows nearest harbor to reach

### Emergency Mode
1. **Triggered automatically** when fuel sensor reads LOW for 2+ seconds
2. **System auto-selects** nearest harbor as destination
3. **Red emergency indicators** appear throughout UI
4. **To exit**: Click "ACKNOWLEDGE & EXIT EMERGENCY" button

### Map Controls
- **Pan**: Click and drag
- **Zoom**: Scroll wheel or +/- buttons
- **Harbor info**: Click harbor markers

### LED Status (Arduino)
| Color | Meaning |
|-------|---------|
| 🟢 Green | GPS Fix + Fuel OK |
| 🟡 Yellow | No GPS + Fuel OK |
| 🔴 Red | No GPS + Fuel LOW |
| 🟣 Purple | GPS Fix + Fuel LOW (Emergency) |

---

## API Reference

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/state` | Full system state |
| GET | `/api/harbors` | List all harbors |
| POST | `/api/harbor/select` | Select destination harbor |
| POST | `/api/harbor/clear` | Clear selection |
| GET | `/api/fuel` | Fuel status |
| POST | `/api/emergency/acknowledge` | Acknowledge emergency |
| GET | `/api/connection` | Serial connection status |
| GET | `/api/sea-routing/status` | Sea routing availability |
| GET | `/api/sea-routing/route` | Current sea route with waypoints |
| GET | `/api/sea-routing/terrain` | Land/sea detection for current position |

### WebSocket

Connect to `/api/ws` for real-time state updates (JSON format, ~2Hz).

---

## Project Structure

```
ShipRouter/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry
│   ├── config.py               # Configuration constants
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py           # REST & WebSocket endpoints
│   ├── core/                   # Core algorithms (no HW dependencies)
│   │   ├── __init__.py
│   │   ├── navigation.py       # Haversine, bearing calculations
│   │   ├── harbor_manager.py   # Harbor database operations
│   │   ├── fuel_monitor.py     # Fuel state machine
│   │   ├── geo_classifier.py   # Land/sea detection
│   │   ├── navigation_grid.py  # Sea grid generation
│   │   ├── route_engine.py     # A* pathfinding
│   │   └── sea_router.py       # High-level routing service
│   ├── interfaces/             # Hardware interfaces
│   │   ├── __init__.py
│   │   ├── serial_interface.py # Arduino communication
│   │   ├── gps_interface.py    # NMEA parsing
│   │   └── sensor_interface.py # Fuel sensor handling
│   ├── services/
│   │   ├── __init__.py
│   │   └── router_service.py   # Main orchestration service
│   └── static/                 # Web frontend
│       ├── index.html
│       ├── css/style.css
│       └── js/app.js
├── dataset/
│   ├── harbors.csv             # Harbor database
│   └── geodata/                # Coastline data (user downloaded)
│       ├── ne_10m_land.shp
│       ├── ne_10m_land.shx
│       ├── ne_10m_land.dbf
│       └── navigation_grid.json
├── sensor_src/
│   └── ShipRouter_Firmware/
│       └── ShipRouter_Firmware.ino
|       └── config.h
├── tools/
│   └── generate_grid.py        # Grid generation utility
├── tests/
│   ├── mock_serial_emulator.py # Testing without hardware
│   ├── gps_replay.py           # GPS data replay tool
│   └── test_core.py            # Unit tests
├── requirements.txt
└── README.md
```

---

## Troubleshooting

### Serial Connection Issues

| Problem | Solution |
|---------|----------|
| "Port not found" | Check `ls /dev/ttyUSB*` or `/dev/ttyACM*` |
| "Permission denied" | Run `sudo chmod 666 /dev/ttyUSB0` or add user to `dialout` group |
| No data received | Verify Arduino is flashed and LED is blinking |

### GPS Issues

| Problem | Solution |
|---------|----------|
| No GPS fix | Move outdoors, wait 1-2 minutes for cold start |
| Yellow LED only | GPS module not receiving satellites |
| Garbled NMEA | Check baud rate matches (115200) |

### Sea Routing Issues

| Problem | Solution |
|---------|----------|
| "Sea routing not available" | Download and unzip coastline data |
| "No route found" | Destination may be on land or unreachable |
| Grid generation slow | Normal for first run (~5-10 min) |
| Wrong terrain detection | Regenerate grid with higher resolution |

### Fuel Sensor Issues

| Problem | Solution |
|---------|----------|
| Always shows LOW | Check D9 is connected to GND (Mode 0) |
| Always shows OK | Verify sensor LED matches status |
| Random fluctuations | Add decoupling capacitor, check power supply |

### Testing Without Hardware

Use the mock serial emulator:
```bash
# Terminal 1: Start mock serial
python tests/mock_serial_emulator.py

# Terminal 2: Start server (edit config to use mock port)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## License

MIT License

---

## Acknowledgments

- [Natural Earth](https://www.naturalearthdata.com/) - Coastline data
- [Leaflet.js](https://leafletjs.com/) - Interactive maps
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [pynmea2](https://github.com/Knio/pynmea2) - NMEA sentence parsing