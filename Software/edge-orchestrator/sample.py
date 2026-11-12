from contextlib import asynccontextmanager
import logging
import threading
import time
from collections import deque
from typing import Dict, Union, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, ConfigDict

# =====================================================================
# SYSTEM LOGGING & STAGING DIAGNOSTICS INITIALIZATION
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("OrchestratorCore")


# =====================================================================
# ENCAPSULATED THREAD-SAFE ROBOTIC QUEUE OBJECT MECHANICS
# =====================================================================
class HardenedRoboticQueue:
    """
    Thread-safe, explicitly bounded FIFO wrapper protecting memory tracks.
    Insulates physical link execution pacing from high-frequency network spikes.
    """
    def __init__(self, maxsize: int = 50):
        self._maxsize = maxsize
        self._storage = deque(maxlen=maxsize)
        self._lock = threading.Lock()

    def push(self, item: Dict[str, Union[int, float]]) -> None:
        with self._lock:
            if len(self._storage) >= self._maxsize:
                raise ValueError("Queue backpressure capacity saturated.")
            self._storage.append(item)

    def pop(self) -> Optional[Dict[str, Union[int, float]]]:
        with self._lock:
            return self._storage.popleft() if self._storage else None

    def clear(self) -> None:
        with self._lock:
            self._storage.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._storage)


# =====================================================================
# GLOBAL STATE MEMORY REGISTERS & FAULT FLAGS
# =====================================================================
shared_movement_queue = HardenedRoboticQueue(maxsize=50)

is_serial_bus_nominal = threading.Event()
is_serial_bus_nominal.set()

last_sent_timestamp: float = time.time()
timestamp_lock = threading.Lock()


# =====================================================================
# EMERGENCY MANAGEMENT CIRCUITS & LOCKOUT TRIGGERS
# =====================================================================
def trigger_systemic_safety_lockout() -> None:
    """Instantly trips state circuit breakers and flushes memory buffers."""
    is_serial_bus_nominal.clear()
    shared_movement_queue.clear()
    logger.critical("Systemic protection lockout engaged. In-memory queues cleared.")


def execute_controlled_software_deceleration_ramp() -> None:
    """Safely reduces linkage current velocities down to baseline indexes."""
    logger.warning("LOCKOUT SIGNAL ENGAGED: Executing controlled deceleration current ramp.")
    for step in range(3, 0, -1):
        logger.info(f"Deceleration Ramp Matrix Scale: Step {step}")
        time.sleep(0.015)
    logger.info("Safety hold finalized. Motor tracks are locked in home alignment state.")


# =====================================================================
# THREAD 1: BACKGROUND HARDWARE CONTROL SERIAL CONDUCTOR
# =====================================================================
def serial_conductor_worker_loop() -> None:
    """
    Dedicated mechatronic bus writer. Pops commands from the low-latency
    memory object and pipes structured ASCII rows down to the hardware sentinel.
    """
    global last_sent_timestamp
    logger.info("Serial Conductor active and attached to background processing pools.")
    
    while True:
        try:
            if not is_serial_bus_nominal.is_set():
                time.sleep(0.05)
                continue

            command_packet = shared_movement_queue.pop()

            if command_packet:
                if command_packet.get("control_signal") == "HOST_FAULT_LOCKOUT":
                    execute_controlled_software_deceleration_ramp()
                    continue

                execute_icd_hardware_uart_stream(command_packet)
                
                with timestamp_lock:
                    last_sent_timestamp = time.time()

            time.sleep(0.005)

        except Exception as system_anomaly:
            logger.error(f"Critical execution error caught inside Conductor Core: {str(system_anomaly)}")
            trigger_systemic_safety_lockout()


def execute_icd_hardware_uart_stream(packet: Dict[str, Union[int, float]]) -> None:
    """Translates coordinate metrics into fixed 32-byte physical UART frames."""
    jid = packet["joint_id"]
    angle = packet["target_angle"]
    
    scaled_angle = int(angle * 10)
    payload_string = f"DRV,{jid},{scaled_angle}"
    
    xor_checksum = 0
    for char in payload_string:
        xor_checksum ^= ord(char)
    hex_signature = f"{xor_checksum:02X}"
    
    final_uart_packet = f"@{payload_string}*{hex_signature}\n"
    
    byte_length = len(final_uart_packet.encode('ascii'))
    if byte_length > 32:
        logger.error(f"ICD String Over-Length Blocked: {final_uart_packet.strip()} ({byte_length} Bytes)")
        return
        
    logger.info(f"UART TX -> {final_uart_packet.strip()} ({byte_length} Bytes)")


# =====================================================================
# SYSTEM APPLICATION LIFESPAN LIFECYCLE MANAGEMENT
# =====================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Unified Lifespan Context Manager handling clean boot/teardown rails."""
    conductor_thread = threading.Thread(
        target=serial_conductor_worker_loop,
        name="SerialConductorThread",
        daemon=True
    )
    conductor_thread.start()
    logger.info("Multi-threaded architecture successfully pinned to pools via Lifespan Engine.")
    
    yield  # Handshake operational context control to active network endpoint paths
    
    logger.warning("Application shutdown captured. Enforcing safe host tracking stop sequences.")
    trigger_systemic_safety_lockout()
    logger.info("Lifespan cleanup pass finalized. Edge gateway terminated nominally.")


# =====================================================================
# HARDENED FastAPI CORE INITIALIZATION
# =====================================================================
app = FastAPI(
    title="AutoRoboticArms Core Orchestrator",
    version="1.1.0",
    description="Hardened High-Speed Embedded Edge Concurrency Conductor Node",
    lifespan=lifespan
)


# =====================================================================
# JAX'S CHOSEN MIDDLEWARE: ASGI EXCEPTION CUSTOMIZATION HANDLER
# =====================================================================
@app.exception_handler(RequestValidationError)
async def custom_mechatronic_validation_exception_handler(request, exc: RequestValidationError):
    """
    Mitigation Wrapper: Intercepts raw Pydantic validation rejections at the perimeter.
    Appends custom, high-level mechatronic failure matrices back to the streaming client.
    """
    custom_errors = []
    
    for error in exc.errors():
        failed_location = error.get("loc", ["body"])[-1]
        raw_msg = error.get("msg", "Value parsing breakdown.")
        
        mechatronic_tag = "GENERIC_INGRESS_ANOMALY"
        if failed_location == "joint_id":
            mechatronic_tag = "PCA9685_REGISTER_OVERFLOW"
        elif failed_location == "target_angle":
            mechatronic_tag = "GEOMETRIC_WORKSPACE_BREACH"
            
        custom_errors.append({
            "field": failed_location,
            "mechatronic_tag": mechatronic_tag,
            "security_tier": "PERIMETER_GATE_BLOCK",
            "rejection_detail": raw_msg
        })
        logger.warning(f"DevSecOps Perimeter Catch -> [{mechatronic_tag}] on field '{failed_location}': {raw_msg}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "REJECTED",
            "hardware_bus_nominal": True,
            "error_matrix": custom_errors
        }
    )


# =====================================================================
# CHOICE A: HARD-BOUNDED PYDANTIC PERIMETER DATA MODEL
# =====================================================================
class TrajectoryCommand(BaseModel):
    joint_id: int = Field(..., ge=0, le=15, description="Target PCA9685 execution channel register footprint.")
    target_angle: float = Field(..., description="Geometric target tracking angle coordinate.")

    model_config = ConfigDict(
        json_schema_extra={"example": {"joint_id": 1, "target_angle": 90.5}}
    )

    @field_validator("target_angle")
    @classmethod
    def enforce_eager_epsilon_grid(cls, val: float) -> float:
        """DevSecOps Perimeter Guard: Validates float precision depth using an epsilon window."""
        scaled_val = val * 10
        if abs(scaled_val - round(scaled_val)) > 1e-5:
            raise ValueError("Target coordinate depth overshoots hardware registration capabilities.")
        return round(val, 1)


# =====================================================================
# API ENDPOINT ROUTE INTERFACES
# =====================================================================
@app.get("/api/v1/health", status_code=status.HTTP_200_OK)
def get_system_health() -> Dict[str, Union[str, bool, int]]:
    return {
        "status": "ONLINE",
        "serial_bus_nominal": is_serial_bus_nominal.is_set(),
        "active_queue_backlog": len(shared_movement_queue)
    }


@app.post("/api/v1/trajectory/step", status_code=status.HTTP_202_ACCEPTED)
def ingest_trajectory_movement_step(command: TrajectoryCommand) -> Dict[str, str]:
    if not is_serial_bus_nominal.is_set():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Robotic Arm Core is locked out due to an unmitigated hardware exception state."
        )

    # Hard Envelope Boundaries Circuit Breaker Trap
    if not (0.0 <= command.target_angle <= 180.0):
        trigger_systemic_safety_lockout()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workspace envelope breached! Target angle {command.target_angle}° violates safe limits."
        )

    try:
        shared_movement_queue.push({
            "joint_id": command.joint_id,
            "target_angle": command.target_angle
        })
    except ValueError as queue_err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(queue_err)
        )

    return {"message": "Movement token successfully cached inside target node memory array."}


@app.post("/api/v1/fault/reset", status_code=status.HTTP_200_OK)
def reset_systemic_lockout() -> Dict[str, str]:
    if is_serial_bus_nominal.is_set():
        return {"message": "System is already operating nominally. Clear pass skipped."}
    shared_movement_queue.clear()
    is_serial_bus_nominal.set()
    logger.info("Manual operator hardware reset registered successfully. Flight operations online.")
    return {"message": "System state registers successfully re-initialized."}







# Test Code













import pytest
from fastapi.testclient import TestClient
from orchestrator_node import app, is_serial_bus_nominal, shared_movement_queue

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_system_state_deck():
    """Guarantees pristine, un-contaminated memory metrics before every single assertion."""
    is_serial_bus_nominal.set()
    shared_movement_queue.clear()
    yield

def test_diagnostics_health_route():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ONLINE"
    assert response.json()["serial_bus_nominal"] is True

def test_nominal_input_precision_caching():
    payload = {"joint_id": 4, "target_angle": 125.3}
    response = client.post("/api/v1/trajectory/step", json=payload)
    assert response.status_code == 202
    assert len(shared_movement_queue) == 1

def test_floating_point_epsilon_validation_pass():
    """Proves that eager epsilon sanitization accepts and normalizes binary IEEE-754 tail noise."""
    payload = {"joint_id": 1, "target_angle": 45.2000000001}
    response = client.post("/api/v1/trajectory/step", json=payload)
    assert response.status_code == 202
    
    cached_command = shared_movement_queue.pop()
    assert cached_command["target_angle"] == 45.2

def test_pydantic_epsilon_precision_rejection():
    """Verifies that precision attacks are captured by middleware and return mechatronic metadata."""
    malicious_payload = {"joint_id": 1, "target_angle": 45.2359182391}
    response = client.post("/api/v1/trajectory/step", json=malicious_payload)
    
    assert response.status_code == 422
    assert response.json()["status"] == "REJECTED"
    assert response.json()["error_matrix"][0]["mechatronic_tag"] == "GEOMETRIC_WORKSPACE_BREACH"
    assert is_serial_bus_nominal.is_set()

def test_pydantic_integer_overflow_rejection():
    """Verifies that invalid or out-of-bounds joint registers are dropped with custom tags."""
    overflow_payload = {"joint_id": 99, "target_angle": 90.0}
    response = client.post("/api/v1/trajectory/step", json=overflow_payload)
    
    assert response.status_code == 422
    assert response.json()["status"] == "REJECTED"
    assert response.json()["error_matrix"][0]["mechatronic_tag"] == "PCA9685_REGISTER_OVERFLOW"
    assert is_serial_bus_nominal.is_set()

def test_workspace_envelope_violation_lockout():
    """Verifies that physical envelope breaches trigger an HTTP 400 and flip the lockout breaker."""
    dangerous_payload = {"joint_id": 2, "target_angle": 185.0}
    response = client.post("/api/v1/trajectory/step", json=dangerous_payload)
    
    assert response.status_code == 400
    assert "Workspace envelope breached" in response.json()["detail"]
    assert not is_serial_bus_nominal.is_set()
    assert len(shared_movement_queue) == 0

def test_backpressure_saturation_limit():
    """Spams the bounded custom queue class object to verify it drops traffic via 429 errors when full."""
    for i in range(50):
        shared_movement_queue.push({"joint_id": 1, "target_angle": 90.0})
        
    assert len(shared_movement_queue) == 50
    
    payload = {"joint_id": 1, "target_angle": 90.0}
    response = client.post("/api/v1/trajectory/step", json=payload)
    assert response.status_code == 429
    assert "backpressure capacity saturated" in response.json()["detail"]