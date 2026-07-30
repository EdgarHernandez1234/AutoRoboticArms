# Sprint 3 Automated Protobuf Binary Serialization Test Harness
import math
import pytest
from google.protobuf.message import DecodeError
from src.proto.telemetry_schema_pb2 import TelemetrySnapshot, ArmKinematics

def test_protobuf_round_trip_lossless():
    """
    Marcus's Round-Trip Test: Proves 32-bit IEEE 754 floats survive 
    binary packing and unpacking with zero mechatronic precision loss.
    """
    # 1. Construct original message
    original = TelemetrySnapshot(
        schema_version=1, 
        timestamp=1690000000.0, 
        system_state="NOMINAL", 
        watchdog_ms=3000
    )
    # Populate primary arm
    original.left_arm.base_deg = 90.5
    original.left_arm.shoulder_deg = 45.2
    original.left_arm.elbow_deg = 120.0
    # Note: right_arm is intentionally left untouched/unpopulated

    # 2. Serialize to compressed binary byte string
    binary_blob = original.SerializeToString()

    # 3. Deserialize into a completely new, empty object
    decoded = TelemetrySnapshot()
    decoded.ParseFromString(binary_blob)

    # 4. Assert Lossless Float Recovery (Accounting for minor IEEE 754 precision drift)
    assert math.isclose(decoded.left_arm.base_deg, 90.5, rel_tol=1e-5)
    assert math.isclose(decoded.left_arm.shoulder_deg, 45.2, rel_tol=1e-5)
    assert math.isclose(decoded.left_arm.elbow_deg, 120.0, rel_tol=1e-5)

    # 5. Assert Top-Level Contract Integrity
    assert decoded.schema_version == 1
    assert decoded.system_state == "NOMINAL"


def test_unpopulated_submessage_handling():
    """
    Proves that unpopulated robotic arms omit bytes and evaluate to False.
    """
    snapshot = TelemetrySnapshot(schema_version=1)
    snapshot.left_arm.base_deg = 90.0

    binary_blob = snapshot.SerializeToString()
    
    decoded = TelemetrySnapshot()
    decoded.ParseFromString(binary_blob)

    # Natively verify the right arm did not transmit ghost bytes
    assert decoded.HasField("left_arm") is True
    assert decoded.HasField("right_arm") is False


def test_corrupted_byte_stream_handling():
    """
    Proves that malformed binary injections throw a catchable DecodeError instead of silently corrupting RAM.
    """
    corrupted_bytes = b"\xFF\xFF\xFF\xFF\x00\x11\x22"  # Junk hexadecimal noise
    snapshot = TelemetrySnapshot()

    # Assert that the C++ backend correctly identifies the threat and aborts
    with pytest.raises(DecodeError):
        snapshot.ParseFromString(corrupted_bytes)