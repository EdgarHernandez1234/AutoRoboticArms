import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Security, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from google.protobuf.json_format import MessageToDict

# Import our compiled binary schema
from src.proto.telemetry_schema_pb2 import TelemetrySnapshot

# Configure System Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ControlPlane")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Local Control Plane async resources...")
    yield
    logger.info("Shutting down Local Control Plane... Pruning open sockets.")
app = FastAPI(
    title="AutoRoboticArms Local Control Plane (Step 2 Armored)",
    lifespan=lifespan
)

ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8050",
    "http://127.0.0.1:8050",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # NO WILDCARDS (*) ALLOWED!
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# Initialize the ASGI Web Application
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def verify_api_key(api_key: str = Security(api_key_header)):
    """
    Jax's DevSecOps Perimeter Guard: Validates the X-API-Key header.
    Rejects unauthorized or missing security tokens prior to route execution.
    """
    EXPECTED_KEY = os.getenv("CONTROL_PLANE_API_KEY", "DEV_SECRET_KEY_123")
    if not api_key or api_key != EXPECTED_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Missing or invalid X-API-Key header."
        )
    return api_key

class ConnectionManager:
    """
    Elena's Asynchronous Broadcast Airlock.
    Manages active WebSockets and handles translation from Protobuf to JSON.
    """
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accepts incoming browser connections and adds them to the pool."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Active streams: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Removes dead connections from the broadcast pool."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_telemetry(self, binary_blob: bytes):
        """
        Translates binary Protobuf to JSON and pushes to all connected clients.
        Called cross-thread by conductor_host.py via asyncio.run_coroutine_threadsafe.
        """
        if not self.active_connections:
            return  # Save CPU cycles if no one is watching the dashboard

        # Data Translation (Protobuf -> Python Dict)
        snapshot = TelemetrySnapshot()
        snapshot.ParseFromString(binary_blob)
        
        payload_dict = MessageToDict(
            snapshot,
            preserving_proto_field_name=True,  # Keep 'base_deg' instead of converting to camelCase
            use_integers_for_enums=True
        )

        # Broadcast loop with slow-client pruning
        for connection in list(self.active_connections):
            try:
                # 100ms non-blocking write timeout prevents lagging clients from freezing the server
                await asyncio.wait_for(connection.send_json(payload_dict), timeout=0.1)
            except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
                logger.warning("Pruning slow or disconnected web client.")
                self.disconnect(connection)

# Global manager instance
manager = ConnectionManager()


# ==========================================
# REST & WEBSOCKET ENDPOINT ROUTERS
# ==========================================

@app.get("/health")
async def health_check():
    """1. Node Health Assertion (GET)"""
    return {"status": "HEALTHY", "subsystem": "Local Control Plane Web Gateway"}


@app.post("/api/v1/override")
async def manual_override(command: dict, _key: str = Security(verify_api_key)):
    """
    2. Operator Command Override (POST) - 🚀 ARMORED WITH STEP 1 API KEY SECURITY
    Requires valid X-API-Key header to execute override commands.
    """
    logger.warning(f"🔒 Authenticated Override Command Executed: {command}")
    return {"status": "COMMAND_RECEIVED", "command": command}


@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """
    3. WebSocket Stream Listener
    Holds the TCP socket open to receive broadcasts from the ConnectionManager.
    """
    await manager.connect(websocket)
    try:
        while True:
            # We use this loop to keep the socket alive and detect client disconnects.
            # Actual data is pushed asynchronously via manager.broadcast_telemetry().
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)