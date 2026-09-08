import os
import sys
import tempfile
import time
import pytest
from fastapi.testclient import TestClient
host_main = os.path.abspath(os.path.join(os.path.dirname(__file__), "../orchestrator_node"))
sys.path.append(host_main)
import orchestrator_node
from orchestrator_node import app, waypoint_queue

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_test_environment():
    """Swaps the production database for an isolated temporary SQLite file."""
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Store original and inject test database manager
    original_db = orchestrator_node.db
    orchestrator_node.db = orchestrator_node.DatabaseManager(db_path=temp_db_path)
    waypoint_queue.clear()
    
    yield
    
    # Teardown: Shutdown background thread and purge temporary files
    orchestrator_node.db.shutdown()
    orchestrator_node.db = original_db
    for ext in ["", "-wal", "-shm"]:
        if os.path.exists(temp_db_path + ext):
            os.remove(temp_db_path + ext)

def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ONLINE"

def test_nominal_waypoint_ingestion_and_logging():
    payload = {"joint_1": 90, "joint_2": 45, "joint_3": 180}
    response = client.post("/api/v1/waypoint", json=payload)
    
    assert response.status_code == 200
    assert response.json()["status"] == "ENQUEUED"
    
    # Allow the background database worker thread 600ms to micro-batch to disk
    time.sleep(0.6)
    
    logs = orchestrator_node.db.get_recent_telemetry()
    assert len(logs) >= 2  # Expecting both INGRESS and DISPATCH records
    
    # ORDER BY id DESC means logs[0] is the most recent (DISPATCH)
    assert logs[0][7] == "DISPATCH"
    
    # logs[1] is the initial API ingestion (INGRESS)
    assert logs[1][7] == "INGRESS"
    assert logs[1][2] == 90  # joint_1 column check on the INGRESS row
    
def test_pydantic_boundary_rejection():
    payload = {"joint_1": 190, "joint_2": -5, "joint_3": 90}
    response = client.post("/api/v1/waypoint", json=payload)
    
    assert response.status_code == 422
    assert len(waypoint_queue) == 0

def test_queue_saturation_protection():
    # Artificially inflate the queue to its 10,000 item maximum
    for _ in range(10000):
        waypoint_queue.append({"joint_1": 0, "joint_2": 0, "joint_3": 0})
        
    payload = {"joint_1": 90, "joint_2": 90, "joint_3": 90}
    response = client.post("/api/v1/waypoint", json=payload)
    
    assert response.status_code == 503
    assert "Active queue backlog full" in response.json()["detail"]

def test_telemetry_read_gateway():
    client.post("/api/v1/waypoint", json={"joint_1": 10, "joint_2": 20, "joint_3": 30})
    time.sleep(0.6)
    
    response = client.get("/api/v1/telemetry")
    assert response.status_code == 200
    assert len(response.json()["telemetry_logs"]) > 0