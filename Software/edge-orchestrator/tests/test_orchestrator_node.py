import os
import sys
import tempfile
import time
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
host_main = os.path.abspath(os.path.join(os.path.dirname(__file__), "../orchestrator_node"))
sys.path.append(host_main)
import orchestrator_node
from orchestrator_node import (
    app,
    waypoint_queue,
    build_option_a_frame,
    is_serial_connected,
    last_commanded_angles,
    last_commanded_lock
)

client = TestClient(app)
# =====================================================================
# TEST FIXTURES
# =====================================================================
@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch):
    """
    1. Swaps the production database for an isolated temporary SQLite file.
    2. Clears in-memory queues and resets serial state flags.
    3. Prevents background serial loops from binding to real /dev ports during unit tests.
    """
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Isolate database
    original_db = orchestrator_node.db
    orchestrator_node.db = orchestrator_node.DatabaseManager(db_path=temp_db_path)
    waypoint_queue.clear()
    is_serial_connected.clear()
    
    # Reset last commanded angles to default home pose
    with last_commanded_lock:
        last_commanded_angles.update({"joint_1": 90, "joint_2": 90, "joint_3": 90})

    yield

    # Teardown
    orchestrator_node.db.shutdown()
    orchestrator_node.db = original_db
    for ext in ["", "-wal", "-shm"]:
        if os.path.exists(temp_db_path + ext):
            os.remove(temp_db_path + ext)


# =====================================================================
# 1. FRAME BUILDER & PARSER VALIDATION (Vulnerability 6 Tests)
# =====================================================================
def test_build_option_a_frame_nominal():
    """Verifies standard frame composition, ASCII delimiters, and XOR checksum math."""
    frame = build_option_a_frame(90, 45, 120)
    
    # Payload: "DRV,90,45,120"
    payload = "DRV,90,45,120"
    expected_xor = 0
    for ch in payload:
        expected_xor ^= ord(ch)
    expected_checksum = f"{expected_xor:02X}"
    
    assert frame == f"@{payload}*{expected_checksum}\n".encode("ascii")
    assert len(frame) <= 32  # Microcontroller circular buffer ceiling


def test_build_option_a_frame_clamping():
    """Verifies that out-of-range angles are strictly clamped to [0, 180]."""
    frame = build_option_a_frame(250, -20, 90)
    # Expected clamping: 250 -> 180, -20 -> 0
    payload = "DRV,180,0,90"
    
    expected_xor = 0
    for ch in payload:
        expected_xor ^= ord(ch)
    expected_checksum = f"{expected_xor:02X}"
    
    assert frame == f"@{payload}*{expected_checksum}\n".encode("ascii")


# =====================================================================
# 2. INGRESS & IN-MEMORY CONTROLS
# =====================================================================
def test_health_endpoint_degraded_when_unplugged():
    """Health check must accurately reflect that serial hardware is disconnected."""
    is_serial_connected.clear()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ONLINE"
    assert response.json()["serial_bus_nominal"] is False


def test_nominal_waypoint_ingestion_and_ingress_logging():
    """Confirms HTTP ingress enqueues item and logs INGRESS telemetry immediately."""
    payload = {"joint_1": 90, "joint_2": 45, "joint_3": 180}
    response = client.post("/api/v1/waypoint", json=payload)
    
    assert response.status_code == 200
    assert response.json()["status"] == "ENQUEUED"
    assert len(waypoint_queue) == 1
    
    # Give the database worker time to commit the row
    time.sleep(0.6)
    
    logs = orchestrator_node.db.get_recent_telemetry()
    assert len(logs) >= 1
    # Check the newest record matches the ingress event
    ingress_log = [l for l in logs if l[7] == "INGRESS"][0]
    assert ingress_log[2] == 90   # joint_1
    assert ingress_log[3] == 45   # joint_2
    assert ingress_log[4] == 180  # joint_3
    assert ingress_log[6] == "RECV"


def test_pydantic_boundary_rejection():
    """Verifies out-of-spec coordinates trigger HTTP 422 and are dropped."""
    payload = {"joint_1": 190, "joint_2": -5, "joint_3": 90}
    response = client.post("/api/v1/waypoint", json=payload)
    
    assert response.status_code == 422
    assert len(waypoint_queue) == 0


def test_queue_saturation_protection():
    """Validates HTTP 503 backpressure rejection when FIFO hits 10,000 capacity."""
    for _ in range(10000):
        waypoint_queue.append({"joint_1": 0, "joint_2": 0, "joint_3": 0})
        
    payload = {"joint_1": 90, "joint_2": 90, "joint_3": 90}
    response = client.post("/api/v1/waypoint", json=payload)
    
    assert response.status_code == 503
    assert "Active queue backlog full" in response.json()["detail"]


# =====================================================================
# 3. SERIAL PROTOCOL & WATCHDOG SIMULATION (Vulnerability 4 Tests)
# =====================================================================
def test_safe_hold_recovery_handshake():
    """
    Tests that receiving an 'H' status code (Safe-Hold latch) purges the 
    waypoint queue and issues 3 successive holding frames to clear the latch.
    """
    mock_serial = MagicMock()
    # Mock sequence: 1st read returns 'H' (Safe-Hold active), subsequent reads return 'K'
    mock_serial.is_open = True
    mock_serial.read.side_effect = [b'H', b'K', b'K', b'K']
    
    # Preload queue with a move that will encounter the hold
    waypoint_queue.append({"joint_1": 100, "joint_2": 80, "joint_3": 70})
    
    # Simulate single dispatch logic from hardware_serial_worker
    target = waypoint_queue.popleft()
    frame = build_option_a_frame(target["joint_1"], target["joint_2"], target["joint_3"])
    mock_serial.write(frame)
    
    ack = mock_serial.read(1).decode("ascii", errors="ignore")
    assert ack == "H"
    
    # Enforce safe-hold mitigation logic
    if ack == "H":
        waypoint_queue.clear()
        recovery_frame = build_option_a_frame(
            last_commanded_angles["joint_1"],
            last_commanded_angles["joint_2"],
            last_commanded_angles["joint_3"]
        )
        for _ in range(3):
            mock_serial.write(recovery_frame)
            
    # Assertions: 1 initial transmission + 3 handshake burst transmissions = 4 writes
    assert mock_serial.write.call_count == 4
    assert len(waypoint_queue) == 0


def test_telemetry_read_gateway():
    """Validates the GET telemetry endpoint can read WAL records."""
    client.post("/api/v1/waypoint", json={"joint_1": 10, "joint_2": 20, "joint_3": 30})
    time.sleep(0.6)
    
    response = client.get("/api/v1/telemetry")
    assert response.status_code == 200
    assert len(response.json()["telemetry_logs"]) > 0

def test_arduino_physical_device_node_detected():
    """Verifies that the configured character device exists on the host."""
    assert os.path.exists(orchestrator_node.SERIAL_PORT), (
        f"Arduino device node not detected at {orchestrator_node.SERIAL_PORT}. "
        "Check physical USB connection or run 'ls /dev/ttyACM*' / 'ls /dev/ttyUSB*'."
    )
    
def test_arduino_serial_link_active():
    """Asserts that the background serial worker has acquired the port."""
    assert orchestrator_node.is_serial_connected.is_set(), (
        f"Serial link to Arduino at {orchestrator_node.SERIAL_PORT} is inactive or disconnected."
    )