"""
ShipRouter - Marine Fuel Monitoring & Navigation System
FastAPI Entry Point
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api import router as api_router
from .services import get_router_service, initialize_router_service
from .config import SERVER_HOST, SERVER_PORT

# =============================================================================
# Logging Setup
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


# =============================================================================
# Application Lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events"""
    logger.info("Starting ShipRouter...")
    
    # Initialize and start the router service
    service = get_router_service()
    
    if not service.initialize():
        logger.error("Failed to initialize RouterService")
        # Continue anyway - may work without harbors for testing
    
    service.start()
    logger.info("RouterService started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down ShipRouter...")
    service.stop()
    logger.info("ShipRouter stopped")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="ShipRouter",
    description="Marine Fuel Monitoring & Navigation System",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Include API routes
app.include_router(api_router, prefix="/api")


# =============================================================================
# Root Routes
# =============================================================================

@app.get("/")
async def root():
    """Serve the main UI"""
    return FileResponse(static_path / "index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    service = get_router_service()
    state = service.get_state()
    
    return {
        "status": "healthy",
        "service_running": service.is_running,
        "serial_connected": state.serial_connected,
        "harbors_loaded": service.harbor_manager.is_loaded,
        "harbor_count": service.harbor_manager.count
    }


# =============================================================================
# Run with Uvicorn (for development)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True
    )