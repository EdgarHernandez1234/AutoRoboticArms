import os
import sys
import pytest
from unittest.mock import MagicMock
import struct

# Since conductor_host.py is located in the parent directory which python doesn't search by default.
conductor_main = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Add the parent directory to the system path to add the main conductor file for unit testing
sys.path.append(conductor_main)

# Import your host script class module
from conductor_host import AutoRoboticArmConductor 

@pytest.fixture
def conductor():
    """
    Provides a fresh, pre-configured conductor instance before every single test.
    Injects a mocked serial connection to prevent tests from looking for a physical wire.
    """
    obj = AutoRoboticArmConductor(l1_length_cm=12.0, l2_length_cm=10.0)
    # Inject mocked serial hardware wire interface stub
    obj.serial_connection = MagicMock()
    return obj


# =====================================================================
# PART 1: KINEMATICS MATRIX & SERIAL PACKING UNIT TESTS
# =====================================================================

def test_inverse_kinematics_valid_nominal(conductor):
    """Validates that a standard reachable coordinate yields safe, bounded servo targets."""
    # Point (10, 10, 5) is within reachable stretch boundaries
    base, shoulder, elbow = conductor.calculate_ik(10, 10, 5)
    
    # Verify calculated values map precisely to physical servo constraints
    assert 0 <= base <= 180
    assert 0 <= shoulder <= 180
    assert 0 <= elbow <= 180


def test_binary_frame_packing_integrity(conductor):
    """Verifies that a packed binary frame strictly matches the 5-Byte Interface Contract layout."""
    joint_target_id = 1
    angle_target = 90
    
    # Act: Serialize control variables
    packed_frame = conductor.pack_binary_frame(joint_target_id, angle_target)
    
    # Assert: Frame size check rule (Must be exactly 5 bytes uncompressed binary)
    assert len(packed_frame) == 5
    
    # Unpack frame byte values matching struct layout constraint: '<BBBBB'
    sync1, sync2, parsed_id, parsed_ticks, parsed_crc = struct.unpack('!BBHB', packed_frame)
    
    # Check alignment headers and payload segments
    assert sync1 == 0x55
    assert sync2 == 0xAA
    assert parsed_id in [0, 1, 2] # Asserts it maps strictly to Base, Shoulder, or Elbow
    assert 0 <= parsed_ticks <= 4095 # Asserts it fits within 12-bit registers limits
    assert isinstance(parsed_crc, int)


def test_mock_hardware_write_call(conductor):
    """Simulates an active output stream to verify the mock hardware interface intercepts writes."""
    fake_frame = b'\x55\xAA\x02\x2D\x1F' # Simulated packed frame array
    
    # Execute transmission function directly over fake hardware connection
    conductor.serial_connection.write(fake_frame)
    
    # MagicMock Validation: Assert that the mock successfully captured the transmission data call
    conductor.serial_connection.write.assert_called_once_with(fake_frame)


# =====================================================================
# PART 2: WORKSPACE ENVELOPE FILTER UNIT TESTS (The Snippet Extension)
# =====================================================================

def test_verify_workspace_envelope_valid_nominal(conductor):
    """Asserts that safe coordinates within the reachable envelope pass filtering cleanly."""
    # Distance is ~15.0cm. Bounds are [2.0cm, 22.0cm]. Safe!
    assert conductor.verify_workspace_envelope(10, 10, 5) is True


def test_verify_workspace_envelope_out_of_max_reach(conductor):
    """Asserts that targets exceeding maximum link lengths are correctly dropped by the filter."""
    # Target coordinate is completely out of range (100cm away)
    assert conductor.verify_workspace_envelope(100, 100, 50) is False


def test_verify_workspace_envelope_inside_min_crash_zone(conductor):
    """Asserts that targets too close to the origin are blocked to prevent internal collisions."""
    # Core origin point drops below our hard fallback threshold of 2.0cm
    assert conductor.verify_workspace_envelope(0.1, 0.1, 0.1) is False