/**
 * ShipRouter - Frontend Application
 * Handles WebSocket connection, Leaflet map, and UI updates
 */

// =============================================================================
// Configuration
// =============================================================================

const CONFIG = {
    WS_RECONNECT_INTERVAL: 3000,
    TOAST_DURATION: 5000,
    MAP_DEFAULT_CENTER: [12.5, 80.0],  // Tamil Nadu coast
    MAP_DEFAULT_ZOOM: 8,
    MAP_TILE_URL: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    MAP_ATTRIBUTION: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
};

// =============================================================================
// State
// =============================================================================

const state = {
    connected: false,
    systemMode: 'normal',
    fuelLow: false,
    gpsValid: false,
    currentPosition: null,
    selectedHarbor: null,
    destination: null,
    nearestHarbors: [],
    harbors: [],
    // Sea routing
    seaRoutingAvailable: false,
    isOnSea: true,
    terrainType: 'unknown',
    seaRoute: null,
    routeWaypoints: [],
    navigationGuidance: null,
    // Embarkation
    embarkation: null
};

// =============================================================================
// DOM Elements
// =============================================================================

const elements = {
    // Connection
    connectionBadge: document.getElementById('connectionBadge'),
    
    // Mode
    modeCard: document.getElementById('modeCard'),
    systemMode: document.getElementById('systemMode'),
    
    // Fuel
    fuelCard: document.getElementById('fuelCard'),
    fuelIndicator: document.getElementById('fuelIndicator'),
    fuelLevel: document.getElementById('fuelLevel'),
    fuelText: document.getElementById('fuelText'),
    
    // GPS
    gpsStatus: document.getElementById('gpsStatus'),
    gpsPosition: document.getElementById('gpsPosition'),
    gpsSpeed: document.getElementById('gpsSpeed'),
    gpsHeading: document.getElementById('gpsHeading'),
    gpsSatellites: document.getElementById('gpsSatellites'),
    
    // Harbor
    harborSelect: document.getElementById('harborSelect'),
    clearHarborBtn: document.getElementById('clearHarborBtn'),
    
    // Navigation
    navCard: document.getElementById('navCard'),
    navDisplay: document.getElementById('navDisplay'),
    navDestination: document.getElementById('navDestination'),
    navMetrics: document.getElementById('navMetrics'),
    navDistance: document.getElementById('navDistance'),
    navBearing: document.getElementById('navBearing'),
    navCardinal: document.getElementById('navCardinal'),
    
    // Nearest
    nearestCard: document.getElementById('nearestCard'),
    nearestList: document.getElementById('nearestList'),
    
    // Emergency
    emergencyActions: document.getElementById('emergencyActions'),
    acknowledgeBtn: document.getElementById('acknowledgeBtn'),
    
    // Toast
    toastContainer: document.getElementById('toastContainer')
};

// =============================================================================
// Map Setup
// =============================================================================

let map;
let vesselMarker;
let harborMarkers = {};
let destinationLine;
let seaRouteLine;
let waypointMarkers = [];
let embarkationVisible = false;  // Track embarkation section visibility

function initMap() {
    map = L.map('map', {
        center: CONFIG.MAP_DEFAULT_CENTER,
        zoom: CONFIG.MAP_DEFAULT_ZOOM,
        zoomControl: true
    });
    
    L.tileLayer(CONFIG.MAP_TILE_URL, {
        attribution: CONFIG.MAP_ATTRIBUTION,
        maxZoom: 18
    }).addTo(map);
    
    // Create vessel marker (initially hidden)
    const vesselIcon = L.divIcon({
        className: 'vessel-marker',
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });
    
    vesselMarker = L.marker([0, 0], { 
        icon: vesselIcon,
        zIndexOffset: 1000
    });
}

function updateVesselPosition(lat, lon) {
    if (!map) return;
    
    if (lat && lon) {
        vesselMarker.setLatLng([lat, lon]);
        if (!map.hasLayer(vesselMarker)) {
            vesselMarker.addTo(map);
        }
    }
}

function loadHarborMarkers(harbors) {
    // Clear existing markers
    Object.values(harborMarkers).forEach(marker => map.removeLayer(marker));
    harborMarkers = {};
    
    harbors.forEach(harbor => {
        const icon = L.divIcon({
            className: 'harbor-marker',
            iconSize: [14, 14],
            iconAnchor: [7, 7]
        });
        
        const marker = L.marker([harbor.latitude, harbor.longitude], { icon })
            .bindPopup(`
                <div class="popup-title">${harbor.name}</div>
                <div class="popup-info">${harbor.description || 'Harbor'}</div>
            `);
        
        marker.addTo(map);
        harborMarkers[harbor.name] = marker;
    });
}

function updateDestinationMarker(harborName, isEmergency = false) {
    // Reset all harbor markers
    Object.entries(harborMarkers).forEach(([name, marker]) => {
        const icon = L.divIcon({
            className: 'harbor-marker',
            iconSize: [14, 14],
            iconAnchor: [7, 7]
        });
        marker.setIcon(icon);
    });
    
    // Highlight destination
    if (harborName && harborMarkers[harborName]) {
        const className = isEmergency ? 'harbor-marker emergency' : 'harbor-marker destination';
        const size = isEmergency ? [20, 20] : [18, 18];
        const anchor = isEmergency ? [10, 10] : [9, 9];
        
        const icon = L.divIcon({
            className,
            iconSize: size,
            iconAnchor: anchor
        });
        harborMarkers[harborName].setIcon(icon);
    }
}

function drawDestinationLine(fromLat, fromLon, toLat, toLon, isEmergency = false) {
    // Remove existing line
    if (destinationLine) {
        map.removeLayer(destinationLine);
    }
    
    if (!fromLat || !fromLon || !toLat || !toLon) return;
    
    const color = isEmergency ? '#ff3355' : '#ffaa00';
    
    destinationLine = L.polyline(
        [[fromLat, fromLon], [toLat, toLon]],
        { 
            color, 
            weight: 2, 
            dashArray: '10, 10',
            opacity: 0.8
        }
    ).addTo(map);
}

function drawSeaRoute(waypoints, isEmergency = false) {
    // Clear existing sea route
    if (seaRouteLine) {
        map.removeLayer(seaRouteLine);
        seaRouteLine = null;
    }
    
    // Clear existing waypoint markers
    waypointMarkers.forEach(marker => map.removeLayer(marker));
    waypointMarkers = [];
    
    if (!waypoints || waypoints.length < 2) return;
    
    // Build coordinates array
    const coords = waypoints.map(wp => [wp.lat, wp.lon]);
    
    // Draw route line
    const color = isEmergency ? '#ff3355' : '#00ff88';
    
    seaRouteLine = L.polyline(coords, {
        color,
        weight: 3,
        opacity: 0.9
    }).addTo(map);
    
    // Add waypoint markers (skip first and last - origin and destination)
    waypoints.forEach((wp, index) => {
        if (wp.is_origin || wp.is_destination) return;
        
        const icon = L.divIcon({
            className: 'waypoint-marker',
            iconSize: [10, 10],
            iconAnchor: [5, 5],
            html: `<div class="waypoint-dot">${index}</div>`
        });
        
        const marker = L.marker([wp.lat, wp.lon], { icon })
            .bindPopup(`
                <div class="popup-title">Waypoint ${index}</div>
                <div class="popup-info">
                    ${wp.distance_from_prev_km?.toFixed(1) || '--'} km from prev<br>
                    ${wp.bearing_to_next?.toFixed(0) || '--'}° ${wp.cardinal_to_next || ''}
                </div>
            `);
        
        marker.addTo(map);
        waypointMarkers.push(marker);
    });
}

function clearSeaRoute() {
    if (seaRouteLine) {
        map.removeLayer(seaRouteLine);
        seaRouteLine = null;
    }
    waypointMarkers.forEach(marker => map.removeLayer(marker));
    waypointMarkers = [];
}

// =============================================================================
// WebSocket Connection
// =============================================================================

let ws;
let wsReconnectTimeout;

function connectWebSocket() {
    const wsUrl = `ws://${window.location.host}/api/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
        state.connected = true;
        updateConnectionUI(true);
    };
    
    ws.onclose = () => {
        console.log('WebSocket disconnected');
        state.connected = false;
        updateConnectionUI(false);
        
        // Attempt reconnection
        clearTimeout(wsReconnectTimeout);
        wsReconnectTimeout = setTimeout(connectWebSocket, CONFIG.WS_RECONNECT_INTERVAL);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    ws.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            if (message.type === 'state_update') {
                handleStateUpdate(message.data);
            }
        } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
        }
    };
}

// =============================================================================
// State Update Handler
// =============================================================================

function handleStateUpdate(data) {
    // Connection
    if (data.connection) {
        updateConnectionUI(data.connection.serial_connected);
    }
    
    // GPS
    if (data.gps) {
        updateGPSUI(data.gps);
        state.gpsValid = data.gps.valid;
        state.currentPosition = data.gps.valid ? 
            { lat: data.gps.latitude, lon: data.gps.longitude } : null;
        
        if (data.gps.valid) {
            updateVesselPosition(data.gps.latitude, data.gps.longitude);
        }
    }
    
    // Fuel
    if (data.fuel) {
        updateFuelUI(data.fuel);
        state.fuelLow = data.fuel.is_low;
    }
    
    // Sea routing - update state first
    if (data.sea_routing) {
        state.seaRoutingAvailable = data.sea_routing.available;
        state.isOnSea = data.sea_routing.is_on_sea;
        state.terrainType = data.sea_routing.terrain_type;
        state.seaRoute = data.sea_routing.route;
        state.routeWaypoints = data.sea_routing.waypoints || [];
        state.navigationGuidance = data.sea_routing.guidance;
        
        updateTerrainUI(data.sea_routing);
    }
    
    // Embarkation - pass current terrain state
    state.embarkation = data.embarkation;
    updateEmbarkationUI(data.embarkation, state.isOnSea);
    
    // Navigation
    if (data.navigation) {
        state.systemMode = data.navigation.system_mode;
        state.destination = data.navigation.destination;
        state.nearestHarbors = data.navigation.nearest_harbors || [];
        state.selectedHarbor = data.navigation.selected_harbor;
        
        updateModeUI(data.navigation.system_mode);
        updateNavigationUI(data.navigation, data.sea_routing);
        updateNearestUI(data.navigation.nearest_harbors);
        
        // Update map
        const isEmergency = data.navigation.system_mode === 'emergency';
        
        if (data.navigation.destination) {
            const dest = data.navigation.destination;
            updateDestinationMarker(dest.name, isEmergency);
            
            // Draw sea route if available, otherwise draw direct line
            if (state.routeWaypoints && state.routeWaypoints.length > 0) {
                drawSeaRoute(state.routeWaypoints, isEmergency);
                // Hide direct line when we have sea route
                if (destinationLine) {
                    map.removeLayer(destinationLine);
                    destinationLine = null;
                }
            } else if (state.currentPosition) {
                // Fallback to direct line
                clearSeaRoute();
                drawDestinationLine(
                    state.currentPosition.lat,
                    state.currentPosition.lon,
                    dest.latitude,
                    dest.longitude,
                    isEmergency
                );
            }
            
            // Highlight embarkation harbor if on land
            if (state.embarkation && state.embarkation.required) {
                highlightEmbarkationHarbor(state.embarkation.harbor);
            }
        } else {
            updateDestinationMarker(null);
            clearSeaRoute();
            if (destinationLine) {
                map.removeLayer(destinationLine);
                destinationLine = null;
            }
        }
    }
    
    // Emergency acknowledgment button
    const showAckBtn = data.fuel?.state?.awaiting_acknowledgment || false;
    elements.emergencyActions.style.display = showAckBtn ? 'block' : 'none';
}

// =============================================================================
// UI Update Functions
// =============================================================================

function updateConnectionUI(connected) {
    elements.connectionBadge.classList.toggle('connected', connected);
    elements.connectionBadge.querySelector('.status-text').textContent = 
        connected ? 'Connected' : 'Disconnected';
}

function updateModeUI(mode) {
    const isEmergency = mode === 'emergency';
    
    elements.modeCard.classList.toggle('emergency', isEmergency);
    elements.systemMode.textContent = mode.toUpperCase();
    
    // Disable harbor selection in emergency mode
    elements.harborSelect.disabled = isEmergency;
}

function updateFuelUI(fuel) {
    const isLow = fuel.is_low;
    
    elements.fuelLevel.classList.toggle('low', isLow);
    elements.fuelText.classList.toggle('low', isLow);
    elements.fuelText.textContent = isLow ? 'LOW FUEL' : 'NORMAL';
}

function updateGPSUI(gps) {
    // Status
    elements.gpsStatus.textContent = gps.valid ? 'Valid Fix' : 'No Fix';
    elements.gpsStatus.classList.toggle('valid', gps.valid);
    elements.gpsStatus.classList.toggle('invalid', !gps.valid);
    
    // Position
    if (gps.latitude && gps.longitude) {
        elements.gpsPosition.textContent = 
            `${gps.latitude.toFixed(5)}, ${gps.longitude.toFixed(5)}`;
    } else {
        elements.gpsPosition.textContent = '---, ---';
    }
    
    // Speed
    elements.gpsSpeed.textContent = gps.speed_knots ? 
        `${gps.speed_knots.toFixed(1)} kts` : '--- kts';
    
    // Heading
    elements.gpsHeading.textContent = gps.heading ? 
        `${gps.heading.toFixed(0)}°` : '---°';
    
    // Satellites
    elements.gpsSatellites.textContent = gps.satellites || '0';
}

function updateNavigationUI(nav, seaRouting = null) {
    if (nav.destination) {
        elements.navDestination.textContent = nav.destination.name;
        elements.navDestination.classList.add('active');
        elements.navMetrics.style.display = 'flex';
        
        // Use sea route distance if available, otherwise straight-line
        if (seaRouting?.route?.is_valid) {
            elements.navDistance.textContent = seaRouting.route.total_distance_km.toFixed(1);
            
            // Show guidance to next waypoint if available
            if (seaRouting.guidance?.navigation) {
                elements.navBearing.textContent = seaRouting.guidance.navigation.bearing.toFixed(0);
                elements.navCardinal.textContent = `° ${seaRouting.guidance.navigation.cardinal}`;
            } else {
                elements.navBearing.textContent = nav.destination.bearing.toFixed(0);
                elements.navCardinal.textContent = `° ${nav.destination.cardinal_direction}`;
            }
        } else {
            elements.navDistance.textContent = nav.destination.distance_km.toFixed(2);
            elements.navBearing.textContent = nav.destination.bearing.toFixed(0);
            elements.navCardinal.textContent = `° ${nav.destination.cardinal_direction}`;
        }
    } else {
        elements.navDestination.textContent = 'No destination selected';
        elements.navDestination.classList.remove('active');
        elements.navMetrics.style.display = 'none';
    }
}

function updateTerrainUI(seaRouting) {
    // Update GPS card to show terrain type
    const terrainEl = document.getElementById('gpsTerrain');
    if (terrainEl) {
        const terrainText = seaRouting.is_on_sea ? 'Sea' : 'Land';
        if (terrainEl.textContent !== terrainText) {
            terrainEl.textContent = terrainText;
        }
        terrainEl.classList.toggle('warning', !seaRouting.is_on_sea);
    }
}

function updateEmbarkationUI(embarkation, isOnSea) {
    const embarkSection = document.getElementById('embarkationSection');
    if (!embarkSection) return;
    
    // Simple logic: show if required, hide if not
    const shouldShow = embarkation && embarkation.required === true;
    
    if (shouldShow) {
        // Show and update values
        if (!embarkationVisible) {
            embarkationVisible = true;
            embarkSection.style.display = 'block';
            void embarkSection.offsetHeight;
            embarkSection.classList.add('visible');
        }
        
        // Always update values
        const harborEl = document.getElementById('embarkHarbor');
        const distEl = document.getElementById('embarkDistance');
        const bearingEl = document.getElementById('embarkBearing');
        
        if (harborEl) harborEl.textContent = embarkation.harbor || '--';
        if (distEl) distEl.textContent = (embarkation.distance_km?.toFixed(1) || '--');
        if (bearingEl) bearingEl.textContent = `${embarkation.bearing?.toFixed(0) || '--'}° ${embarkation.cardinal || ''}`;
    } else {
        // Hide
        if (embarkationVisible) {
            embarkationVisible = false;
            embarkSection.classList.remove('visible');
            setTimeout(() => {
                if (!embarkationVisible) {
                    embarkSection.style.display = 'none';
                }
            }, 300);
        }
    }
}

function highlightEmbarkationHarbor(harborName) {
    // Add special highlight to embarkation harbor marker
    if (harborName && harborMarkers[harborName]) {
        const icon = L.divIcon({
            className: 'harbor-marker embarkation',
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        });
        harborMarkers[harborName].setIcon(icon);
    }
}

function updateNearestUI(harbors) {
    elements.nearestList.innerHTML = '';
    
    if (!harbors || harbors.length === 0) {
        elements.nearestList.innerHTML = 
            '<li class="nearest-item empty">Waiting for GPS...</li>';
        return;
    }
    
    harbors.forEach(h => {
        const li = document.createElement('li');
        li.className = 'nearest-item';
        li.innerHTML = `
            <span class="harbor-name">${h.name}</span>
            <span class="harbor-distance">${h.distance_km.toFixed(2)} km</span>
        `;
        elements.nearestList.appendChild(li);
    });
}

function populateHarborDropdown(harbors) {
    elements.harborSelect.innerHTML = '<option value="">Select Harbor...</option>';
    
    harbors.forEach(harbor => {
        const option = document.createElement('option');
        option.value = harbor.name;
        option.textContent = harbor.name;
        elements.harborSelect.appendChild(option);
    });
    
    state.harbors = harbors;
}

// =============================================================================
// Toast Notifications
// =============================================================================

function showToast(title, message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div class="toast-title">${title}</div>
        <div class="toast-message">${message}</div>
    `;
    
    elements.toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 300);
    }, CONFIG.TOAST_DURATION);
}

// =============================================================================
// API Calls
// =============================================================================

async function fetchHarbors() {
    try {
        const response = await fetch('/api/harbors');
        const harbors = await response.json();
        populateHarborDropdown(harbors);
        loadHarborMarkers(harbors);
    } catch (error) {
        console.error('Failed to fetch harbors:', error);
        showToast('Error', 'Failed to load harbors', 'error');
    }
}

async function selectHarbor(harborName) {
    try {
        const response = await fetch('/api/harbor/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ harbor_name: harborName })
        });
        
        if (!response.ok) {
            const error = await response.json();
            showToast('Error', error.detail || 'Failed to select harbor', 'error');
            elements.harborSelect.value = '';
        }
    } catch (error) {
        console.error('Failed to select harbor:', error);
        showToast('Error', 'Failed to select harbor', 'error');
    }
}

async function clearHarborSelection() {
    try {
        await fetch('/api/harbor/clear', { method: 'POST' });
        elements.harborSelect.value = '';
    } catch (error) {
        console.error('Failed to clear harbor:', error);
    }
}

async function acknowledgeEmergency() {
    try {
        const response = await fetch('/api/emergency/acknowledge', { method: 'POST' });
        
        if (response.ok) {
            showToast('Success', 'Emergency mode cleared', 'success');
        } else {
            const error = await response.json();
            showToast('Error', error.detail || 'Failed to acknowledge', 'error');
        }
    } catch (error) {
        console.error('Failed to acknowledge emergency:', error);
        showToast('Error', 'Failed to acknowledge emergency', 'error');
    }
}

// =============================================================================
// Event Listeners
// =============================================================================

function setupEventListeners() {
    // Harbor selection
    elements.harborSelect.addEventListener('change', (e) => {
        const harborName = e.target.value;
        if (harborName) {
            selectHarbor(harborName);
        }
    });
    
    // Clear harbor button
    elements.clearHarborBtn.addEventListener('click', clearHarborSelection);
    
    // Emergency acknowledge button
    elements.acknowledgeBtn.addEventListener('click', acknowledgeEmergency);
}

// =============================================================================
// Initialization
// =============================================================================

async function init() {
    console.log('Initializing ShipRouter...');
    
    // Initialize map
    initMap();
    
    // Setup event listeners
    setupEventListeners();
    
    // Fetch harbors
    await fetchHarbors();
    
    // Connect WebSocket
    connectWebSocket();
    
    console.log('ShipRouter initialized');
}

// Start the application
document.addEventListener('DOMContentLoaded', init);