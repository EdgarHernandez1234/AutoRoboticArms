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
    build_option_a_frame,
)
@pytest.fixture(autouse=True)
def clean_state():
    with orchestrator_node.queue_lock:
        orchestrator_node.waypoint_queue.clear()
    with orchestrator_node.hardware_state_lock:
        orchestrator_node.last_known_angles = [90, 90, 90]
        orchestrator_node.target_joint_angles = [90, 90, 90]
        orchestrator_node.is_serial_connected = True
        orchestrator_node.interlock_tripped = False
    yield


@pytest.fixture
def client(tmp_path):
    orchestrator_node.DB_PATH = str(tmp_path / "test_telemetry.db")
    with patch("serial.Serial") as mock_serial_cls:
        mock_instance = MagicMock()
        mock_instance.is_open = True
        mock_instance.read.return_value = b"K"
        mock_serial_cls.return_value = mock_instance
        with TestClient(app) as test_client:
            yield test_client


def test_build_option_a_frame_nominal():
    frame = build_option_a_frame(90, 45, 120)
    assert frame == b"@DRV,90,45,120*57\n"
    assert len(frame) <= 24


def test_build_option_a_frame_clamping():
    frame = build_option_a_frame(-10, 250, 90)
    assert frame == b"@DRV,0,180,90*6C\n"


def test_cartesian_ingress_nominal(client):
    """Reachable coordinate -> returns 200, solved angles, and enqueues."""
    payload = {"x": 10.0, "y": 0.0, "z": 10.0}
    response = client.post("/api/v1/cartesian", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ENQUEUED"
    assert "solved_angles" in data
    assert data["solved_angles"]["joint_1"] == 90  # Forward on X-axis


def test_cartesian_ingress_breach_returns_422(client):
    """Over-extension target (> 21.5 cm) -> rejected with HTTP 422."""
    payload = {"x": 30.0, "y": 0.0, "z": 0.0}
    response = client.post("/api/v1/cartesian", json=payload)
    assert response.status_code == 422
    assert "GEOMETRIC_WORKSPACE_BREACH" in response.json()["detail"]


def test_cartesian_ingress_singularity_too_close_returns_422(client):
    """Under-extension target (< 2.5 cm) -> rejected with HTTP 422."""
    payload = {"x": 0.5, "y": 0.5, "z": 0.5}
    response = client.post("/api/v1/cartesian", json=payload)
    assert response.status_code == 422
    assert "GEOMETRIC_WORKSPACE_BREACH" in response.json()["detail"]


def test_nominal_waypoint_ingestion(client):
    payload = {"joint_1": 45, "joint_2": 90, "joint_3": 135}
    response = client.post("/api/v1/waypoint", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ENQUEUED"


def test_health_endpoint_nominal(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "NOMINAL"
    assert data["serial_bus_nominal"] is True