import os
import time
import threading
import collections
from contextlib import asynccontextmanager
from typing import Optional 
import serial
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from database_manager import DatabaseManager

# =====================================================================
# CONFIGURATION & GLOBAL STATE
# =====================================================================
SERIAL_PORT = os.getenv("SERIAL_PORT", "/dev/tty.usbmodem14101") # /dev/tty.usbmodem14101 for mac or /dev/ttyACM0 for linux
BAUD_RATE = 115200
WATCHDOG_KEEPALIVE_INTERVAL = 1.5  # Seconds (Hardware trips at 3.0s)
LOOP_FREQUENCY_HZ = 20.0
CYCLE_INTERVAL = 1.0 / LOOP_FREQUENCY_HZ  # 0.05s (50 ms)

# Cross-thread FIFO queue bounded to prevent memory runaway
waypoint_queue = collections.deque(maxlen=10000)

# Global telemetry manager backed by SQLite WAL
db = DatabaseManager(db_path="telemetry.db")

# Thread synchronization events
is_serial_connected = threading.Event()
shutdown_event = threading.Event()

# Holding cache for keep-alive heartbeats and watchdog recovery
last_commanded_angles = {"joint_1": 90, "joint_2": 90, "joint_3": 90}
last_commanded_lock = threading.Lock()


# =====================================================================
# FRAME COMPOSER & VALIDATOR (Vulnerability 6 Mitigation)
# =====================================================================
def build_option_a_frame(joint_1: int, joint_2: int, joint_3: int) -> bytes:
    """
    Constructs an Hardware Layer UART frame conforming to strict framing:
    Payload format: DRV,<j1>,<j2>,<j3>
    Frame format:   @<payload>*<CHK>\n
    Total payload body must not exceed 24 bytes.
    """
    # Enforce integer clamping (0 - 180)
    j1 = max(0, min(180, int(round(joint_1))))
    j2 = max(0, min(180, int(round(joint_2))))
    j3 = max(0, min(180, int(round(joint_3))))

    payload = f"DRV,{j1},{j2},{j3}"
    
    # Pre-flight length assertion (Microcontroller MAX_PAYLOAD_LEN = 24)
    if len(payload.encode("ascii")) > 24:
        raise ValueError(f"Payload '{payload}' overshoots 24-byte circular buffer limit.")

    # Compute rolling 8-bit XOR checksum
    checksum = 0
    for ch in payload:
        checksum ^= ord(ch)
    checksum_hex = f"{checksum:02X}"

    full_frame = f"@{payload}*{checksum_hex}\n"
    return full_frame.encode("ascii")


# =====================================================================
# THREAD 1: 20 Hz HARDWARE SERIAL LOOP (Vulnerability 4 Mitigation)
# =====================================================================
def hardware_serial_worker():
    global last_commanded_angles
    ser: Optional[serial.Serial] = None
    last_tx_time = 0.0

    print(f"[SERIAL] Worker thread attached. Target port: {SERIAL_PORT} @ {BAUD_RATE} baud.")

    while not shutdown_event.is_set():
        cycle_start = time.perf_counter()

        # Step 1: Manage Port Connection
        if ser is None or not ser.is_open:
            is_serial_connected.clear()
            try:
                ser = serial.Serial(
                    port=SERIAL_PORT,
                    baudrate=BAUD_RATE,
                    timeout=0.03,        # Non-blocking 30 ms read timeout
                    write_timeout=0.05
                )
                time.sleep(2.0)          # Settle bootloader DTR toggle
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                is_serial_connected.set()
                print(f"[SERIAL] Physical link established on {SERIAL_PORT}")
            except (serial.SerialException, FileNotFoundError, PermissionError) as err:
                print(f"[SERIAL_DISCONNECTED] Retrying in 1.0s: {err}")
                time.sleep(1.0)
                continue

        # Step 2: Determine Frame to Transmit (Work Item vs. Watchdog Keep-Alive)
        target = None
        is_keepalive = False

        if waypoint_queue:
            target = waypoint_queue.popleft()
            with last_commanded_lock:
                last_commanded_angles = {
                    "joint_1": target["joint_1"],
                    "joint_2": target["joint_2"],
                    "joint_3": target["joint_3"]
                }
        elif (time.perf_counter() - last_tx_time) >= WATCHDOG_KEEPALIVE_INTERVAL:
            # Starvation prevention: transmit current holding angle to reset 3000ms watchdog
            with last_commanded_lock:
                target = dict(last_commanded_angles)
            is_keepalive = True

        # Step 3: Transmit and Handle Silicon Response
        if target:
            try:
                frame_bytes = build_option_a_frame(target["joint_1"], target["joint_2"], target["joint_3"])
                ser.write(frame_bytes)
                ser.flush()
                last_tx_time = time.perf_counter()

                # Read 1-byte ACK from ATmega328P ('K', 'E', or 'H')
                ack_byte = ser.read(1).decode("ascii", errors="ignore")
                status_code = ack_byte if ack_byte else "TIMEOUT"

                # Safe-Hold ('H') Recovery: Execute 3-frame handshake burst
                if status_code == "H":
                    print("[WATCHDOG_TRIP] Hardware latched in Safe-Hold ('H'). Disagreeing queue cleared.")
                    waypoint_queue.clear()
                    
                    # 3 consecutive valid holding frames prove link recovery to firmware
                    with last_commanded_lock:
                        recovery_frame = build_option_a_frame(
                            last_commanded_angles["joint_1"],
                            last_commanded_angles["joint_2"],
                            last_commanded_angles["joint_3"]
                        )
                    for _ in range(3):
                        time.sleep(0.05)
                        ser.write(recovery_frame)
                        ser.flush()
                 
                    status_code = "RECOVERING"

                # Log non-blocking telemetry event to SQLite
                db.log_telemetry(
                    joint_1=target["joint_1"],
                    joint_2=target["joint_2"],
                    joint_3=target["joint_3"],
                    checksum="VERIFIED",
                    status_code=status_code,
                    source="HEARTBEAT" if is_keepalive else "DISPATCH"
                )

            except (serial.SerialException, serial.SerialTimeoutException) as err:
                print(f"[SERIAL_IO_ERROR] Link failure during transmission: {err}")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                is_serial_connected.clear()
                continue

        # Step 4: Deterministic 20 Hz Timing Slot (50 ms)
        elapsed = time.perf_counter() - cycle_start
        sleep_time = max(0.0, CYCLE_INTERVAL - elapsed)
        time.sleep(sleep_time)

    # Teardown
    if ser and ser.is_open:
        ser.close()
    print("[SERIAL] Hardware worker thread terminated gracefully.")


# =====================================================================
# LIFESPAN & FASTAPI APPLICATION
# =====================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Launch real-time serial loop in background thread
    worker_thread = threading.Thread(target=hardware_serial_worker, name="HardwareSerialLoop", daemon=True)
    worker_thread.start()
    yield
    print("[SYSTEM] Stopping orchestrator node...")
    shutdown_event.set()
    worker_thread.join(timeout=1.0)
    db.shutdown()

app = FastAPI(
    title="AutoRoboticArms Core Orchestrator",
    version="1.2.0",
    lifespan=lifespan
)


# =====================================================================
# PYDANTIC INGRESS MODELS
# =====================================================================
class Waypoint(BaseModel):
    joint_1: int = Field(..., ge=0, le=180, description="Shoulder azimuth angle")
    joint_2: int = Field(..., ge=0, le=180, description="Elbow pitch angle")
    joint_3: int = Field(..., ge=0, le=180, description="Wrist pitch angle")


# =====================================================================
# API ENDPOINTS
# =====================================================================
@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "ONLINE",
        "serial_bus_nominal": is_serial_connected.is_set(),
        "active_queue_backlog": len(waypoint_queue),
        "target_port": SERIAL_PORT
    }

@app.post("/api/v1/waypoint")
async def enqueue_waypoint(waypoint: Waypoint):
    if len(waypoint_queue) >= 10000:
        raise HTTPException(
            status_code=503,
            detail="Active queue backlog full. Hardware buffer saturated."
        )

    # Append to cross-thread FIFO queue
    waypoint_dict = waypoint.model_dump()
    waypoint_queue.append(waypoint_dict)

    # Ingress persistence snapshot
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
    # Ephemeral read via SQLite WAL mode
    rows = db.get_recent_telemetry(limit=50)
    return {"status": "ONLINE", "telemetry_logs": rows}