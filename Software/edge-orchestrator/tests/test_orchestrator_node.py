import os
import sys
import tempfile
import time
import pytest
from fastapi.testclient import TestClient
host_main = os.path.abspath(os.path.join(os.path.dirname(__file__), "../orchestrator_node"))
sys.path.append(host_main)
from orchestrator_node import (
    app,
    build_option_a_frame,
    waypoint_queue,
    queue_lock,
)

@pytest.fixture
def client():
    # Clear the global queue before each test
    with queue_lock:
        waypoint_queue.clear()
    with TestClient(app) as test_client:
        yield test_client


def test_build_option_a_frame_nominal():
    frame = build_option_a_frame("DRV", 90, 90, 90)
    assert frame.startswith(b"@DRV,90,90,90*")
    assert frame.endswith(b"\n")
    assert len(frame) <= 24


def test_build_option_a_frame_clamping():
    frame = build_option_a_frame("DRV", -10, 250, 90)
    assert frame.startswith(b"@DRV,0,180,90*")


def test_nominal_waypoint_ingestion(client):
    res = client.post("/api/v1/waypoint", json={"joint_1": 45, "joint_2": 90, "joint_3": 135})
    assert res.status_code == 200
    assert res.json()["status"] == "ENQUEUED"
    assert res.json()["queue_depth"] == 1


def test_cartesian_ingress_nominal(client):
    res = client.post("/api/v1/cartesian", json={"x": 10.0, "y": 0.0, "z": 10.0})
    assert res.status_code == 200
    assert res.json()["status"] == "ENQUEUED"
    assert "solved_angles" in res.json()


def test_cartesian_ingress_breach_returns_422(client):
    res = client.post("/api/v1/cartesian", json={"x": 30.0, "y": 0.0, "z": 0.0})
    assert res.status_code == 422
    assert "GEOMETRIC_WORKSPACE_BREACH" in res.json()["detail"]


def test_cartesian_ingress_singularity_too_close_returns_422(client):
    res = client.post("/api/v1/cartesian", json={"x": 1.0, "y": 0.0, "z": 0.5})
    assert res.status_code == 422
    assert "GEOMETRIC_WORKSPACE_BREACH" in res.json()["detail"]


def test_health_endpoint_nominal(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "current_pose" in data
    assert "queue_backlog" in data


# --- SPRINT 8 TRAJECTORY ENDPOINT TESTS ---
def test_trajectory_ingress_nominal(client):
    payload = {
        "waypoints": [
            {"x": 10.0, "y": 0.0, "z": 10.0},
            {"x": 12.0, "y": 0.0, "z": 10.0}
        ],
        "step_size_cm": 0.5
    }
    res = client.post("/api/v1/trajectory", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ENQUEUED"
    assert data["total_steps"] >= 5
    assert data["queue_depth"] == data["total_steps"]


def test_trajectory_ingress_atomic_rejection_on_breach(client):
    """
    If any intermediate or endpoint waypoint breaches the envelope,
    the entire batch must be rejected with 422 and 0 items queued.
    """
    payload = {
        "waypoints": [
            {"x": 10.0, "y": 0.0, "z": 10.0},
            {"x": 28.0, "y": 0.0, "z": 10.0}  # Breaches 21.5 cm maximum
        ],
        "step_size_cm": 0.5
    }
    res = client.post("/api/v1/trajectory", json=payload)
    assert res.status_code == 422
    assert "GEOMETRIC_WORKSPACE_BREACH" in res.json()["detail"]

    # Assert atomic safety: queue remains untouched
    health = client.get("/api/v1/health").json()
    assert health["queue_backlog"] == 0