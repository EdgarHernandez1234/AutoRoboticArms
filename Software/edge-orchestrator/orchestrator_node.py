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

# --- CONFIGURATION CONSTANTS ---
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/ttyACM0")
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))
QUEUE_MAX_CAPACITY = 10000
WATCHDOG_TIMEOUT_SEC = 3.0
KEEP_ALIVE_INTERVAL_SEC = 1.5
DB_PATH = os.getenv("DB_PATH", "telemetry.db")
SLEW_RATE_MAX_DELTA_DEG = 2  # Max degree step per 20ms tick (~100 deg/s)

# --- THREAD-SAFE CONCURRENCY STATE ---
queue_lock = threading.Lock()
waypoint_queue: deque = deque(maxlen=QUEUE_MAX_CAPACITY)

hardware_state_lock = threading.Lock()
last_known_angles = [90, 90, 90]
target_joint_angles = [90, 90, 90]
is_serial_connected = False
interlock_tripped = False
shutdown_event = threading.Event()

db_manager: Optional[DatabaseManager] = None


# --- PYDANTIC SCHEMAS ---
class WaypointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    joint_1: int = Field(..., ge=0, le=180, description="Base Yaw angle (0-180)")
    joint_2: int = Field(..., ge=0, le=180, description="Shoulder Pitch angle (0-180)")
    joint_3: int = Field(..., ge=0, le=180, description="Elbow Pitch angle (0-180)")


class CartesianRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(..., description="X coordinate in cm")
    y: float = Field(..., description="Y coordinate in cm")
    z: float = Field(..., description="Z coordinate in cm")


# --- FRAME SERIALIZATION ---
def build_option_a_frame(j1: int, j2: int, j3: int) -> bytes:
    j1_clamped = max(0, min(180, int(round(j1))))
    j2_clamped = max(0, min(180, int(round(j2))))
    j3_clamped = max(0, min(180, int(round(j3))))

    payload = f"DRV,{j1_clamped},{j2_clamped},{j3_clamped}"
    if len(payload) > 24:
        raise ValueError(f"Payload length exceeds 24-byte ceiling: '{payload}'")

    checksum = 0
    for char in payload:
        checksum ^= ord(char)

    return f"@{payload}*{checksum:02X}\n".encode("ascii")


# --- THREAD 1: HARDWARE DRIVER & SLEW-RATE DISPATCH ---
def mechatronic_hardware_daemon():
    global is_serial_connected, interlock_tripped
    ser: Optional[serial.Serial] = None
    last_tx_timestamp = time.time()

    def send_frame_and_read_ack(frame_bytes: bytes) -> str:
        nonlocal ser
        ser.write(frame_bytes)
        ser.flush()
        ack = ser.read(1).decode("ascii", errors="ignore")
        return ack if ack else "TIMEOUT"

    def execute_safe_hold_recovery():
        global interlock_tripped
        with hardware_state_lock:
            h_frame = build_option_a_frame(*last_known_angles)
        for _ in range(3):
            ser.write(h_frame)
            ser.flush()
            ser.read(1)
            time.sleep(0.02)
        with hardware_state_lock:
            interlock_tripped = False

    while not shutdown_event.is_set():
        if ser is None or not ser.is_open:
            try:
                ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.5)
                time.sleep(2.0)
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                with hardware_state_lock:
                    is_serial_connected = True
                    interlock_tripped = False
                home_frame = build_option_a_frame(90, 90, 90)
                ack = send_frame_and_read_ack(home_frame)
                last_tx_timestamp = time.time()
                if db_manager:
                    db_manager.enqueue_log(90, 90, 90, "VERIFIED", ack, "DISPATCH")
            except (serial.SerialException, FileNotFoundError, PermissionError):
                with hardware_state_lock:
                    is_serial_connected = False
                time.sleep(1.0)
                continue

        # Dequeue waypoint or pop intermediate slew waypoint
        next_waypoint = None
        with queue_lock:
            if waypoint_queue:
                next_waypoint = waypoint_queue.popleft()

        if next_waypoint is not None:
            with hardware_state_lock:
                target_joint_angles[0] = next_waypoint[0]
                target_joint_angles[1] = next_waypoint[1]
                target_joint_angles[2] = next_waypoint[2]

        # Slew-Rate Step Calculation: limit delta per joint
        with hardware_state_lock:
            curr = list(last_known_angles)
            targ = list(target_joint_angles)

        step_angles = []
        needs_motion = False
        for c, t in zip(curr, targ):
            diff = t - c
            if diff != 0:
                needs_motion = True
                step = min(abs(diff), SLEW_RATE_MAX_DELTA_DEG)
                step_angles.append(c + (step if diff > 0 else -step))
            else:
                step_angles.append(c)

        now = time.time()
        ack = None
        cmd_type = None

        try:
            if needs_motion:
                frame = build_option_a_frame(*step_angles)
                ack = send_frame_and_read_ack(frame)
                last_tx_timestamp = now
                cmd_type = "DISPATCH"
                with hardware_state_lock:
                    last_known_angles[0] = step_angles[0]
                    last_known_angles[1] = step_angles[1]
                    last_known_angles[2] = step_angles[2]
            elif (now - last_tx_timestamp) >= KEEP_ALIVE_INTERVAL_SEC:
                with hardware_state_lock:
                    hb_frame = build_option_a_frame(*last_known_angles)
                    hb_angles = list(last_known_angles)
                ack = send_frame_and_read_ack(hb_frame)
                last_tx_timestamp = now
                cmd_type = "HEARTBEAT"
                step_angles = hb_angles

            if ack is not None:
                if ack == "H":
                    with hardware_state_lock:
                        interlock_tripped = True
                    execute_safe_hold_recovery()

                if db_manager:
                    db_manager.enqueue_log(
                        step_angles[0], step_angles[1], step_angles[2],
                        "VERIFIED", ack, cmd_type
                    )

        except (serial.SerialException, OSError):
            with hardware_state_lock:
                is_serial_connected = False
            if ser:
                try:
                    ser.close()
                except Exception:
                    pass
            ser = None
            time.sleep(1.0)
            continue

        time.sleep(0.02)  # 20ms deterministic control tick (50 Hz)

    if ser and ser.is_open:
        ser.close()


# --- LIFESPAN CONTEXT ---
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
    if db_manager:
        db_manager.stop()


# --- FASTAPI INGRESS ---
app = FastAPI(title="Hardened Microservices Node", lifespan=lifespan)


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
        db_manager.enqueue_log(wp.joint_1, wp.joint_2, wp.joint_3, "N/A", "RECV", "INGRESS")

    return {"status": "ENQUEUED", "queue_depth": depth}


@app.post("/api/v1/cartesian", status_code=status.HTTP_200_OK)
async def post_cartesian(target: CartesianRequest):
    """
    Accepts 3D Cartesian coordinates (X, Y, Z in cm), validates reachability,
    solves geometric IK, and queues the resultant clamped joint angles.
    """
    try:
        angles = calculate_joint_angles(target.x, target.y, target.z)
    except WorkspaceEnvelopeViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
        db_manager.enqueue_log(j1, j2, j3, "N/A", "RECV", "INGRESS")

    return {
        "status": "ENQUEUED",
        "solved_angles": {"joint_1": j1, "joint_2": j2, "joint_3": j3},
        "queue_depth": depth
    }


@app.get("/api/v1/telemetry", status_code=status.HTTP_200_OK)
async def get_telemetry(limit: int = 50):
    if not db_manager:
        raise HTTPException(status_code=500, detail="DatabaseManager uninitialized")
    rows = db_manager.fetch_recent_logs(limit=limit)
    return {"count": len(rows), "records": rows}


@app.get("/api/v1/health", status_code=status.HTTP_200_OK)
async def get_health():
    with hardware_state_lock:
        nominal = is_serial_connected and not interlock_tripped
        status_str = "NOMINAL" if nominal else "DEGRADED"
        serial_status = is_serial_connected
        safe_hold = interlock_tripped
        current_pose = list(last_known_angles)

    with queue_lock:
        q_depth = len(waypoint_queue)

    return {
        "status": status_str,
        "serial_bus_nominal": serial_status,
        "safe_hold_tripped": safe_hold,
        "current_pose": current_pose,
        "queue_backlog": q_depth
    }