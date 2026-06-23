import pytest
from fastapi.testclient import TestClient
from orchestrator_node import app, is_serial_bus_nominal, shared_movement_deque

# Initialize the mock client to simulate web traffic to your API
client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_system_state():
    """
    This fixture runs before EVERY test. It guarantees a pristine, 
    un-contaminated state so tests do not interfere with each other.
    """
    is_serial_bus_nominal.set()
    shared_movement_deque.clear()
    yield

def test_system_health_endpoint():
    """Verifies the orchestrator boots and reports nominal health."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ONLINE",
        "serial_bus_nominal": True,
        "active_queue_backlog": 0
    }

def test_valid_trajectory_ingestion():
    """Verifies that a mathematically safe coordinate is accepted and queued."""
    payload = {"joint_id": 2, "target_angle": 45.5}
    response = client.post("/api/v1/trajectory/step", json=payload)
    
    # Assert network layer accepts the command
    assert response.status_code == 202
    assert "successfully cached" in response.json()["message"]
    
    # Assert memory layer properly stored the command
    assert len(shared_movement_deque) == 1
    cached_command = shared_movement_deque.popleft()
    assert cached_command["joint_id"] == 2
    assert cached_command["target_angle"] == 45.5

def test_workspace_envelope_violation_lockout():
    """
    Verifies the Fail-Fast Circuit Breaker: An angle > 180 should instantly 
    throw a 400 error and drop the system into a hardware lockout state.
    """
    dangerous_payload = {"joint_id": 2, "target_angle": 185.0}
    response = client.post("/api/v1/trajectory/step", json=dangerous_payload)
    
    # Assert the API blocks the request
    assert response.status_code == 400
    assert "Workspace envelope breached" in response.json()["detail"]
    
    # Assert the internal atomic state flag has been tripped
    assert not is_serial_bus_nominal.is_set()
    # Assert the queue was purged to prevent trailing damage
    assert len(shared_movement_deque) == 0

def test_submission_during_lockout_rejected():
    """Verifies that once locked out, even SAFE commands are rejected."""
    # Manually trip the circuit breaker
    is_serial_bus_nominal.clear()
    
    safe_payload = {"joint_id": 2, "target_angle": 90.0}
    response = client.post("/api/v1/trajectory/step", json=safe_payload)
    
    # Assert the system returns a 503 Service Unavailable
    assert response.status_code == 503
    assert "locked out due to an unmitigated hardware exception" in response.json()["detail"]