
import pytest
from fastapi.testclient import TestClient
import asyncio
from src.control_plane import app, manager
from src.proto.telemetry_schema_pb2 import TelemetrySnapshot
from unittest.mock import AsyncMock, MagicMock

client = TestClient(app)

def test_health_check_endpoint():
    """
    Test 1: Validates that the GET /health REST endpoint responds correctly.
    """
    response = client.get("/health")
    
    assert response.status_code == 200
    assert response.json() == {
        "status": "HEALTHY", 
        "subsystem": "Local Control Plane Web Gateway"
    }

def test_cors_whitelisted_origin_allowed():
    """
    Verifies that pre-flight requests from Whitelisted Origins
    receive the Access-Control-Allow-Origin header (HTTP 200).
    """
    headers = {
        "Origin": "http://localhost:8000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-API-Key, Content-Type",
    }
    response = client.options("/api/v1/override", headers=headers)
    
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8000"

def test_cors_unauthorized_origin_rejected():
    """
    Verifies that pre-flight requests from Malicious/UnWhitelisted Origins
    do NOT receive the Access-Control-Allow-Origin header.
    """
    headers = {
        "Origin": "http://malicious-site.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-API-Key, Content-Type",
    }
    response = client.options("/api/v1/override", headers=headers)
    
    # CORS middleware rejects by withholding the Access-Control-Allow-Origin header
    assert "access-control-allow-origin" not in response.headers

def test_override_endpoint_security_rejection():
    """
    Verifies that POST /api/v1/override REJECTS 
    requests missing the X-API-Key header or providing an invalid key (HTTP 401).
    """
    mock_command = {"action": "EMERGENCY_HALT", "axis": "BASE"}
    
    # 1. Missing Key Test -> Must return 401
    res_no_key = client.post("/api/v1/override", json=mock_command)
    assert res_no_key.status_code == 401
    assert "Unauthorized" in res_no_key.json()["detail"]

    # 2. Invalid Key Test -> Must return 401
    res_bad_key = client.post("/api/v1/override", json=mock_command, headers={"X-API-Key": "WRONG_KEY"})
    assert res_bad_key.status_code == 401

def test_override_endpoint_security_acceptance():
    """
    Verifies that POST /api/v1/override ACCEPTS 
    requests presenting a valid X-API-Key header (HTTP 200).
    """
    mock_command = {"action": "EMERGENCY_HALT", "axis": "BASE"}
    valid_headers = {"X-API-Key": "DEV_SECRET_KEY_123"}
    
    response = client.post("/api/v1/override", json=mock_command, headers=valid_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMMAND_RECEIVED"
    assert data["command"]["action"] == "EMERGENCY_HALT"


def test_websocket_connection_acceptance_and_pruning():
    """
    Validates that the WebSocket endpoint accepts connections 
    and the ConnectionManager properly adds/prunes clients from RAM.
    """
    # Verify starting state (no clients connected)
    assert len(manager.active_connections) == 0

    # Open an in-memory WebSocket stream
    with client.websocket_connect("/ws/telemetry") as websocket:
        
        # 1. Connection Acceptance Assertion
        # If we reach inside this block without an exception, the handshake succeeded!
        assert len(manager.active_connections) == 1

    # 2. Pruning Assertion
    # Once the 'with' block exits, the test client drops the connection.
    # The ASGI loop catches WebSocketDisconnect and triggers manager.disconnect()
    assert len(manager.active_connections) == 0

def test_websocket_protobuf_broadcast_rendering():
    """
    Validates that binary Protobuf blobs are correctly
    parsed and broadcast as JSON dictionaries over active WebSockets.
    """
    # 1. Build a binary Protobuf snapshot
    snapshot = TelemetrySnapshot()
    snapshot.timestamp = 1700000000000
    snapshot.left_arm.base_deg = 45.5
    snapshot.left_arm.shoulder_deg = -12.3
    binary_blob = snapshot.SerializeToString()

    # 2. Open an in-memory WebSocket stream
    with client.websocket_connect("/ws/telemetry") as websocket:
        assert len(manager.active_connections) == 1

        # 3. Trigger broadcast with raw binary blob
        asyncio.run(manager.broadcast_telemetry(binary_blob))

        # 4. Receive and assert JSON frame conversion
        data = websocket.receive_json()
        assert data["timestamp"] == 1700000000000
        assert data["left_arm"]["base_deg"] == 45.5
        assert data["left_arm"]["shoulder_deg"] == -12.3

def test_websocket_lagging_client_pruning():
    """
    Simulates a lagging WebSocket client whose send_json call exceeds the 100ms timeout,
    verifying that ConnectionManager automatically prunes it from active connections without crashing.
    """
    # 1. Reset ConnectionManager active connections pool
    manager.active_connections.clear()

    # 2. Create a mock lagging client that times out on send_json
    lagging_client = MagicMock()
    lagging_client.send_json = AsyncMock(side_effect=asyncio.TimeoutError)

    # 3. Create a normal responsive mock client
    responsive_client = MagicMock()
    responsive_client.send_json = AsyncMock(return_value=None)

    # Register both clients in the manager
    manager.active_connections = [lagging_client, responsive_client]
    assert len(manager.active_connections) == 2

    # 4. Prepare a binary Protobuf snapshot
    snapshot = TelemetrySnapshot()
    snapshot.timestamp = 1700000000000
    snapshot.left_arm.base_deg = 45.5
    binary_blob = snapshot.SerializeToString()

    # 5. Execute broadcast (runs lagging client through timeout handler)
    asyncio.run(manager.broadcast_telemetry(binary_blob))

    # 6. Verify assertions
    # The lagging client should have been pruned; the responsive client remains!
    assert len(manager.active_connections) == 1
    assert manager.active_connections[0] == responsive_client
    assert lagging_client not in manager.active_connections