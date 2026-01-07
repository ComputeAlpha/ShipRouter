# ShipRouter 

**Marine Fuel Monitoring & Navigation System**

A real-time vessel navigation system that monitors fuel levels and provides intelligent harbor routing. Features automatic emergency mode when fuel runs low, directing vessels to the nearest harbor.

## Features

- **Real-time GPS Tracking**: Display current vessel position on an interactive map
- **Fuel Monitoring**: Binary fuel level detection with debounced state transitions
- **Smart Navigation**: Calculate distance and bearing to any harbor
- **Emergency Mode**: Automatic nearest-harbor routing when fuel is low
- **User Acknowledgment**: Manual confirmation required to exit emergency mode
- **WebSocket Updates**: Real-time UI updates every 0.5 seconds

## Architecture

```
ShipRouter/
├── app/
│   ├── interfaces/         # Hardware abstraction layer
│   │   ├── base.py        # Abstract base classes
│   │   ├── gps_interface.py
│   │   ├── sensor_interface.py
│   │   └── serial_interface.py
│   │
│   ├── core/              # Pure algorithms (no HW dependency)
│   │   ├── navigation.py  # Haversine, bearing calculations
│   │   ├── harbor_manager.py
│   │   └── fuel_monitor.py
│   │
│   ├── services/          # Business logic orchestration
│   │   └── router_service.py
│   │
│   ├── api/               # FastAPI routes
│   │   └── routes.py
│   │
│   ├── static/            # Frontend assets
│   │   ├── index.html
│   │   ├── css/style.css
│   │   └── js/app.js
│   │
│   ├── config.py          # Configuration constants
│   └── main.py            # FastAPI entry point
│
├── dataset/
│   └── harbors.csv        # Harbor database
│
├── sensor_src/            # Arduino firmware (TODO)
│
├── tests/                 # Test suite (TODO)
│
└── requirements.txt
```

## Hardware Requirements

- Raspberry Pi 5 (4GB RAM)
- Arduino Nano R4 (Renesas MCU)
- DFRobot Non-contact Capacitive Liquid Level Sensor
- Quectel EC200U 4G/GSM Module with GPS/GNSS

## Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd ShipRouter
```

### 2. Create virtual environment (optional)

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the server

```bash
# Development mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Or directly
python -m app.main
```

### 5. Access the UI

Open your browser and navigate to:
```
http://<raspberry-pi-ip>:8000
```

## Configuration

Edit `app/config.py` to customize:

```python
# Serial port
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 115200

# Timing
FUEL_DEBOUNCE_SECONDS = 2.0
UPDATE_INTERVAL_SECONDS = 0.5

# Navigation
TOP_N_HARBORS = 3
```

## Serial Protocol

The Arduino sends JSON packets over USB Serial:

```json
{"fuel": 1, "nmea": "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,47.0,M,,*47"}
```

- `fuel`: `1` = normal, `0` = low
- `nmea`: Raw NMEA sentence (GPGGA, GPRMC, or GPVTG)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Full system status |
| GET | `/api/harbors` | List all harbors |
| GET | `/api/harbors/nearest` | Get nearest harbors |
| POST | `/api/harbor/select` | Select destination harbor |
| POST | `/api/harbor/clear` | Clear selection |
| POST | `/api/emergency/acknowledge` | Acknowledge emergency |
| WS | `/api/ws` | WebSocket for real-time updates |

## System Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Normal** | Fuel sensor = HIGH | User selects destination, system provides navigation |
| **Emergency** | Fuel sensor = LOW (debounced 2s) | Auto-selects nearest harbor, requires acknowledgment to exit |

## Module Isolation

The codebase is designed for easy hardware swapping:

- **Interfaces**: Implement `BaseGPSInterface`, `BaseSensorInterface`, or `BaseSerialInterface`
- **Core**: Pure Python algorithms with no hardware dependencies
- **Services**: Orchestrates interfaces and core logic

To swap GPS hardware, simply create a new class implementing `BaseGPSInterface`.

## License

MIT

--