import time
import threading
import collections
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from database_manager import DatabaseManager

# 1. Global State & Cross-Thread Queue
# Bounded queue prevents Head-of-Line Blocking and unbounded memory growth
waypoint_queue = collections.deque(maxlen=10000)

# Global DatabaseManager instance for thread-safe telemetry ingestion
db = DatabaseManager(db_path="telemetry.db")

# 2. FastAPI Lifespan (Graceful Shutdown)
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    print("[SYSTEM] Shutting down. Flushing telemetry queue to disk...")
    db.shutdown()

app = FastAPI(lifespan=lifespan)

# 3. Validation Schemas
class Waypoint(BaseModel):
    joint_1: int = Field(..., ge=0, le=180)
    joint_2: int = Field(..., ge=0, le=180)
    joint_3: int = Field(..., ge=0, le=180)

# 4. Thread 1: 20 Hz Real-Time Serial / Mock Hardware Loop
def hardware_serial_loop():
    while True:
        cycle_start = time.perf_counter()
        
        if waypoint_queue:
            # Dequeue target angles
            target = waypoint_queue.popleft()
            
            # Format payload strictly to Option A ICD: @DRV,<j1>,<j2>,<j3>*<CHK>\n
            payload_body = f"DRV,{target['joint_1']},{target['joint_2']},{target['joint_3']}"
            
            # Calculate 8-bit XOR checksum
            checksum = 0
            for char in payload_body:
                checksum ^= ord(char)
            checksum_hex = f"{checksum:02X}"
            
            # Simulated Hardware Response (Mocking Option A Silicon)
            status_code = "K"  # Default to Nominal
            
            # Log the hardware dispatch to SQLite (Microsecond execution, non-blocking)
            db.log_telemetry(
                joint_1=target['joint_1'],
                joint_2=target['joint_2'],
                joint_3=target['joint_3'],
                checksum=checksum_hex,
                status_code=status_code,
                source="DISPATCH"
            )
        
        # Enforce deterministic 20 Hz (50 ms) cycle
        elapsed = time.perf_counter() - cycle_start
        sleep_time = max(0.0, 0.05 - elapsed)
        time.sleep(sleep_time)

# Start real-time hardware loop immediately
threading.Thread(target=hardware_serial_loop, daemon=True).start()

# 5. Thread 2: FastAPI Ingress Gateway
@app.post("/api/v1/waypoint")
async def enqueue_waypoint(waypoint: Waypoint):
    if len(waypoint_queue) >= 10000:
        raise HTTPException(status_code=503, detail="Active queue backlog full. Hardware buffer saturated.")
    
    # Safely pass command to Thread 1
    waypoint_dict = waypoint.model_dump()
    waypoint_queue.append(waypoint_dict)
    
    # Log the incoming user request instantly
    db.log_telemetry(
        joint_1=waypoint.joint_1,
        joint_2=waypoint.joint_2,
        joint_3=waypoint.joint_3,
        checksum="N/A",
        status_code="RECV",
        source="INGRESS"
    )
    
    return {"status": "ENQUEUED", "queue_depth": len(waypoint_queue)}

@app.get("/api/v1/telemetry")
async def get_telemetry():
    # Read gateway fetching live dashboard data concurrently via WAL mode
    rows = db.get_recent_telemetry(limit=50)
    return {"status": "ONLINE", "telemetry_logs": rows}

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ONLINE", "serial_bus_nominal": True, "active_queue_backlog": len(waypoint_queue)}