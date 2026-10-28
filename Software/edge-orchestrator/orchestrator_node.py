"""
orchestrator_node.py
Hardened Local Microservices Node with Real Hardware Serial Loop,
Cartesian Spatial Kinematic Ingress, Slew-Rate Limiting, and WAL Persistence.
"""

import os
import time
import serial
import threading
from collections import deque
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict

from database_manager import DatabaseManager
from kinematics import calculate_joint_angles, WorkspaceEnvelopeViolation
from trajectory import TrajectoryPlanner

# --- CONFIGURATION CONSTANTS ---
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyACM0") # /dev/ttyACM0 for linux or /dev/cu.usbmodem14201 for Mac
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))
TICK_INTERVAL_SEC = 0.020        # 50 Hz Hardware Dispatch Loop (20 ms)
QUEUE_MAX_CAPACITY = 200
WATCHDOG_TIMEOUT_SEC = 3.0
HEARTBEAT_INTERVAL_SEC = 1.5
DB_PATH = os.getenv("DB_PATH", "telemetry.db")
SLEW_RATE_MAX_DELTA_DEG = 2  # Max degree step per 20ms tick (~100 deg/s)

# --- THREAD-SAFE CONCURRENCY STATE ---
waypoint_queue: deque = deque(maxlen=QUEUE_MAX_CAPACITY)
queue_lock = threading.Lock()
shutdown_event = threading.Event()

last_known_angles = [90, 90, 90]
target_joint_angles = [90, 90, 90]
serial_bus_nominal = False
safe_hold_tripped = False
last_dispatch_time = 0.0

db_manager: Optional[DatabaseManager] = None
trajectory_planner = TrajectoryPlanner(step_size_cm=0.5)

# --- PYDANTIC SCHEMAS ---
class WaypointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    joint_1: int = Field(..., ge=0, le=180, description="Base Yaw (0-180 deg)")
    joint_2: int = Field(..., ge=0, le=180, description="Shoulder Pitch (0-180 deg)")
    joint_3: int = Field(..., ge=0, le=180, description="Elbow Pitch (0-180 deg)")


class CartesianPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(..., description="X coordinate in cm")
    y: float = Field(..., description="Y coordinate in cm")
    z: float = Field(..., description="Z coordinate in cm")


class TrajectoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    waypoints: List[CartesianPoint] = Field(..., min_length=1, description="List of 3D Cartesian coordinates")
    step_size_cm: Optional[float] = Field(0.5, gt=0.0, le=5.0, description="Max distance between path steps")


# --- PROTOCOL & CHECKSUM UTILITY ---
def build_option_a_frame(cmd: str, j1: int, j2: int, j3: int) -> bytes:
    j1 = max(0, min(180, int(j1)))
    j2 = max(0, min(180, int(j2)))
    j3 = max(0, min(180, int(j3)))
    payload = f"@{cmd},{j1},{j2},{j3}"
    if len(payload) > 24:
        raise ValueError("Payload exceeds 24-byte boundary")

    checksum = 0
    for ch in payload:
        checksum ^= ord(ch)

    return f"{payload}*{checksum:02X}\n".encode("ascii")


# --- HARDWARE WORKER DAEMON (THREAD 1) ---
def mechatronic_hardware_daemon():
    global serial_bus_nominal, safe_hold_tripped, last_dispatch_time
    global last_known_angles, target_joint_angles

    ser: Optional[serial.Serial] = None
    while not shutdown_event.is_set():
        if ser is None:
            try:
                ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.05)
                time.sleep(2.0)  # Allow DTR reset to settle
                # Issue Safe-Hold Recovery Burst
                for _ in range(3):
                    ser.write(build_option_a_frame("H", 90, 90, 90))
                    time.sleep(0.02)
                serial_bus_nominal = True
                safe_hold_tripped = False
            except Exception:
                serial_bus_nominal = False
                time.sleep(1.0)
                continue

        tick_start = time.time()

        with queue_lock:
            if waypoint_queue:
                target_joint_angles = list(waypoint_queue.popleft())

        # Slew-Rate Limiter (Interpolation Step)
        moved = False
        step_angles = list(last_known_angles)
        for i in range(3):
            delta = target_joint_angles[i] - last_known_angles[i]
            if delta != 0:
                step = max(-SLEW_RATE_MAX_DELTA_DEG, min(SLEW_RATE_MAX_DELTA_DEG, delta))
                step_angles[i] += step
                moved = True

        last_known_angles = list(step_angles)
        now = time.time()

        if moved or (now - last_dispatch_time >= HEARTBEAT_INTERVAL_SEC):
            cmd = "DRV" if moved else "HBT"
            frame = build_option_a_frame(cmd, last_known_angles[0], last_known_angles[1], last_known_angles[2])
            try:
                ser.write(frame)
                ser.flush()
                last_dispatch_time = now
                ack = "K"
                line = ser.readline().decode("ascii", errors="ignore").strip()
                if line:
                    if "K" in line:
                        ack = "K"
                        safe_hold_tripped = False
                    elif "E" in line or "H" in line:
                        ack = line
                        safe_hold_tripped = True
                if db_manager:
                    db_manager.enqueue_log(
                        last_known_angles[0], last_known_angles[1], last_known_angles[2],
                        "NOMINAL", ack, cmd
                    )
            except Exception:
                serial_bus_nominal = False
                ser.close()
                ser = None
                continue

        elapsed = time.time() - tick_start
        sleep_dur = max(0.0, TICK_INTERVAL_SEC - elapsed)
        time.sleep(sleep_dur)

    if ser and ser.is_open:
        ser.close()


# --- FASTAPI LIFECYCLE & INGRESS (THREAD 2) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_manager
    db_manager = DatabaseManager(DB_PATH)
    if hasattr(db_manager, "start"):
        db_manager.start()
    elif hasattr(db_manager, "initialize_database"):
        db_manager.initialize_database()

    driver_thread = threading.Thread(target=mechatronic_hardware_daemon, daemon=True)
    driver_thread.start()
    yield
    shutdown_event.set()
    driver_thread.join(timeout=2.0)
    if db_manager and hasattr(db_manager, "stop"):
        db_manager.stop()


app = FastAPI(title="AutoRoboticArms Orchestrator Node", lifespan=lifespan)


@app.get("/api/v1/health")
async def get_health():
    with queue_lock:
        backlog = len(waypoint_queue)
    return {
        "status": "NOMINAL" if serial_bus_nominal and not safe_hold_tripped else "DEGRADED",
        "serial_bus_nominal": serial_bus_nominal,
        "safe_hold_tripped": safe_hold_tripped,
        "current_pose": last_known_angles,
        "queue_backlog": backlog
    }


@app.post("/api/v1/waypoint", status_code=status.HTTP_200_OK)
async def post_waypoint(wp: WaypointRequest):
    with queue_lock:
        if len(waypoint_queue) >= QUEUE_MAX_CAPACITY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Hardened FIFO Queue Saturated (Backpressure Tripped)"
            )
        waypoint_queue.append((wp.joint_1, wp.joint_2, wp.joint_3))
        depth = len(waypoint_queue)

    if db_manager:
        db_manager.enqueue_log(wp.joint_1, wp.joint_2, wp.joint_3, "NOMINAL", "RECV", "INGRESS")

    return {"status": "ENQUEUED", "queue_depth": depth}


@app.post("/api/v1/cartesian", status_code=status.HTTP_200_OK)
async def post_cartesian(target: CartesianPoint):
    try:
        angles = calculate_joint_angles(target.x, target.y, target.z)
    except WorkspaceEnvelopeViolation as exc:
        raise HTTPException(
            status_code=422,
            detail=f"GEOMETRIC_WORKSPACE_BREACH: {str(exc)}"
        )

    j1, j2, j3 = angles["base"], angles["shoulder"], angles["elbow"]

    with queue_lock:
        if len(waypoint_queue) >= QUEUE_MAX_CAPACITY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Hardened FIFO Queue Saturated (Backpressure Tripped)"
            )
        waypoint_queue.append((j1, j2, j3))
        depth = len(waypoint_queue)

    if db_manager:
        db_manager.enqueue_log(j1, j2, j3, "NOMINAL", "RECV", "INGRESS")

    return {
        "status": "ENQUEUED",
        "solved_angles": {"joint_1": j1, "joint_2": j2, "joint_3": j3},
        "queue_depth": depth
    }


@app.post("/api/v1/trajectory", status_code=status.HTTP_200_OK)
async def post_trajectory(req: TrajectoryRequest):
    """
    Subdivides Cartesian multi-waypoint paths into equidistant linear steps,
    atomically validates every intermediate pose against the geometric envelope,
    and enqueues the continuous joint trajectory.
    """
    pts = [(p.x, p.y, p.z) for p in req.waypoints]
    custom_planner = TrajectoryPlanner(step_size_cm=req.step_size_cm)

    # Atomic envelope validation across the entire continuous trajectory
    try:
        joint_trajectory = custom_planner.generate_joint_trajectory(pts)
    except WorkspaceEnvelopeViolation as exc:
        raise HTTPException(
            status_code=422,
            detail=f"GEOMETRIC_WORKSPACE_BREACH: {str(exc)}"
        )

    with queue_lock:
        available_slots = QUEUE_MAX_CAPACITY - len(waypoint_queue)
        if len(joint_trajectory) > available_slots:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Queue capacity exceeded: requires {len(joint_trajectory)} slots, but only {available_slots} available."
            )
        for angles in joint_trajectory:
            waypoint_queue.append(angles)
        depth = len(waypoint_queue)

    if db_manager and joint_trajectory:
        first = joint_trajectory[0]
        db_manager.enqueue_log(first[0], first[1], first[2], "NOMINAL", "RECV", f"TRAJECTORY_START_{len(joint_trajectory)}")

    return {
        "status": "ENQUEUED",
        "total_steps": len(joint_trajectory),
        "queue_depth": depth
    }


@app.get("/api/v1/telemetry")
async def get_telemetry(limit: int = 50):
    if not db_manager:
        return {"logs": []}
    return {"logs": db_manager.fetch_recent_logs(limit=limit)}