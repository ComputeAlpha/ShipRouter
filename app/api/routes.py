"""
API Routes
FastAPI REST and WebSocket endpoints
"""

import asyncio
import logging
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..services import get_router_service, SystemState

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Pydantic Models for Request/Response
# =============================================================================

class HarborSelectRequest(BaseModel):
    harbor_name: str


class AcknowledgeResponse(BaseModel):
    success: bool
    message: str


class HarborResponse(BaseModel):
    name: str
    latitude: float
    longitude: float
    description: str = ""


class StatusResponse(BaseModel):
    status: str
    message: str


# =============================================================================
# WebSocket Connection Manager
# =============================================================================

class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, data: dict):
        """Send data to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# =============================================================================
# REST Endpoints
# =============================================================================

@router.get("/status")
async def get_status():
    """Get current system status"""
    service = get_router_service()
    state = service.get_state()
    return state.to_dict()


@router.get("/harbors")
async def get_harbors():
    """Get all available harbors"""
    service = get_router_service()
    harbors = service.get_all_harbors()
    return [h.to_dict() for h in harbors]


@router.get("/harbors/distances")
async def get_harbors_with_distances():
    """Get all harbors with distances from current position"""
    service = get_router_service()
    state = service.get_state()
    
    if not state.gps_valid:
        return JSONResponse(
            status_code=400,
            content={"error": "GPS position not available"}
        )
    
    harbors = service.get_harbors_with_distances()
    return [h.to_dict() for h in harbors]


@router.get("/harbors/nearest")
async def get_nearest_harbors():
    """Get nearest harbors from current position"""
    service = get_router_service()
    state = service.get_state()
    return [h.to_dict() for h in state.nearest_harbors]


@router.post("/harbor/select")
async def select_harbor(request: HarborSelectRequest):
    """Select a harbor as navigation destination"""
    service = get_router_service()
    
    success = service.select_harbor(request.harbor_name)
    
    if not success:
        state = service.get_state()
        if state.system_mode == "emergency":
            raise HTTPException(
                status_code=400,
                detail="Cannot select harbor in emergency mode"
            )
        raise HTTPException(
            status_code=404,
            detail=f"Harbor not found: {request.harbor_name}"
        )
    
    return {"success": True, "selected": request.harbor_name}


@router.post("/harbor/clear")
async def clear_harbor_selection():
    """Clear current harbor selection"""
    service = get_router_service()
    service.clear_selection()
    return {"success": True}


@router.post("/emergency/acknowledge")
async def acknowledge_emergency():
    """Acknowledge and exit emergency mode"""
    service = get_router_service()
    
    success = service.acknowledge_emergency()
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Not in a state that can be acknowledged"
        )
    
    return AcknowledgeResponse(
        success=True,
        message="Emergency mode cleared"
    )


@router.get("/navigation")
async def get_navigation():
    """Get current navigation data"""
    service = get_router_service()
    state = service.get_state()
    
    return {
        "system_mode": state.system_mode,
        "gps_valid": state.gps_valid,
        "position": {
            "latitude": state.latitude,
            "longitude": state.longitude,
            "heading": state.heading,
            "speed_knots": state.speed_knots
        },
        "destination": state.destination.to_dict() if state.destination else None,
        "nearest_harbors": [h.to_dict() for h in state.nearest_harbors]
    }


@router.get("/fuel")
async def get_fuel_status():
    """Get current fuel status"""
    service = get_router_service()
    state = service.get_state()
    
    return {
        "status": state.fuel_status,
        "is_low": state.fuel_status == 0,
        "state": state.fuel_state.to_dict() if state.fuel_state else None
    }


@router.get("/connection")
async def get_connection_status():
    """Get serial connection status"""
    service = get_router_service()
    state = service.get_state()
    
    return {
        "connected": state.serial_connected,
        "status": state.connection_status
    }


# =============================================================================
# WebSocket Endpoint
# =============================================================================

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.
    
    Sends system state updates at configured interval.
    """
    await manager.connect(websocket)
    service = get_router_service()
    
    try:
        while True:
            # Send current state
            state = service.get_state()
            await websocket.send_json({
                "type": "state_update",
                "data": state.to_dict()
            })
            
            # Wait for next update interval (0.5s as per requirement)
            await asyncio.sleep(0.5)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# =============================================================================
# Utility function for broadcasting from service
# =============================================================================

async def broadcast_state_update(state: SystemState):
    """Broadcast state update to all WebSocket clients"""
    await manager.broadcast({
        "type": "state_update",
        "data": state.to_dict()
    })