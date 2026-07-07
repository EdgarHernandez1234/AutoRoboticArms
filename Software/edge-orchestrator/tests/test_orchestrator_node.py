import pytest
from fastapi.testclient import TestClient
from orchestrator_node import app, is_serial_bus_nominal, shared_movement_queue

# Initialize the mock client to simulate web traffic to your API

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