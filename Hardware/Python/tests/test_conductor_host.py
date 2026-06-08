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
    obj = AutoRoboticArmConductor(port='MOCK_PORT',baudrate=115200,l1_length_cm=12.0, l2_length_cm=10.0)
    # Inject mocked serial hardware wire interface stub
    obj.serial_connection = MagicMock()
    return obj


# =====================================================================
# MODULE 1: INTERFACE PROTOCOL & PACKING INTEGRITY TESTS
# =====================================================================

def test_protocol_configuration_constants(conductor):
    """Verifies that configuration sync markers are cleanly bound to instance attributes rather than magic numbers."""
    assert conductor.SYNC_1 == 0x55
    assert conductor.SYNC_2 == 0xAA


def test_binary_frame_packing_and_endianness(conductor):
    """Aggressively asserts that frames use strict 6-Byte Big-Endian formatting and valid CRC8 remainder tokens."""
    target_joint = 1
    target_ticks = 375  # Mid-point servo value
    
    packed_frame = conductor.pack_binary_frame(target_joint, target_ticks)
    
    # Assert Step 1: Verify explicit 6-byte structure contract payload length
    assert len(packed_frame) == 6
    
    # Assert Step 2: Unpack frame using network order contract alignment mapping '!BBBHB'
    sync1, sync2, joint_id, pwm_ticks, crc8 = struct.unpack('!BBBHB', packed_frame)
    
    assert sync1 == conductor.SYNC_1
    assert sync2 == conductor.SYNC_2
    assert joint_id == target_joint
    assert pwm_ticks == target_ticks
    
    # Assert Step 3: Run the unpacked data payload through the generator to prove CRC8 validity
    payload_slice = packed_frame[2:5]  # Grabs Joint_ID and multi-byte Ticks
    calculated_check = conductor.calculate_crc8(payload_slice)
    assert crc8 == calculated_check

@pytest.mark.parametrize("angle, expected_ticks", [
    (0.0, 150),    # Minimum physical axis point
    (90.0, 375),   # Perfectly orthogonal centerline position
    (180.0, 600),  # Maximum physical axis point
    (-10.0, 150),  # Low Out-of-Bounds Clamping Check
    (200.0, 600),  # High Out-of-Bounds Clamping Check
])

def test_angle_to_ticks_mapping_and_clamping(conductor, angle, expected_ticks):
    """Validates that floating degrees map cleanly to 12-bit register ticks and clamp safely within safe thresholds."""
    computed_ticks = conductor.angle_to_ticks(angle)
    assert computed_ticks == expected_ticks
    assert isinstance(computed_ticks, int)

def test_mock_hardware_write_call(conductor):
    """Simulates an active output stream to verify the mock hardware interface intercepts writes."""
    fake_frame = b'\x55\xAA\x02\x2D\x1F' # Simulated packed frame array
    
    # Execute transmission function directly over fake hardware connection
    conductor.serial_connection.write(fake_frame)
    
    # MagicMock Validation: Assert that the mock successfully captured the transmission data call
    conductor.serial_connection.write.assert_called_once_with(fake_frame)


def test_serial_transmission_payload(conductor):
    """Verifies that running a valid motion target causes exactly 3 frames to pass to the mock link."""
    # Command a valid Cartesian movement
    success = conductor.move_to_target(10, 10, 5)
    
    assert success is True
    
    # Assert that our patch successfully intercepted the stream exactly 3 times
    assert conductor.serial_connection.write.call_count == 3
    
    # Inspect the exact outbound frames from memory
    call_history = conductor.serial_connection.write.call_args_list
    first_frame = call_history[0].args[0]
    
    # Verify our fixed length 6-byte Big-Endian sync boundaries
    assert len(first_frame) == 6
    assert first_frame[0] == conductor.SYNC_1


# =====================================================================
# MODULE 2: BOUNDARY VALUE ANALYSIS (BVA) SPATIAL RISK TESTS
# =====================================================================

@pytest.mark.parametrize("x, y, z, expected_safety_state", [
    (10.0, 10.0, 5.0, True),    # Nominal Target: Safe interior reachable space vector
    (50.0, 50.0, 50.0, False),  # Maximum Reach Overflow: Exceeds L1 + L2 limit threshold
    (0.0, 0.0, 0.0, False),     # Crash Core Enclosure Overflow: Inside internal self-collision zone
    (15.1, 15.1, 0.0, True),    # Boundary Check: 21.35cm reach value (Inside our 21.5cm clearance envelope)
    (15.3, 15.3, 0.0, False),   # Boundary Check: 21.63cm reach value (Dropped gracefully by safety margin)
])
def test_spatial_safety_interlock_boundaries(conductor, x, y, z, expected_safety_state):
    """Verifies that our Workspace Filter intercepts and drops out-of-bounds coordinates before math processing."""
    assert conductor.verify_workspace_envelope(x, y, z) == expected_safety_state

def test_inverse_kinematics_rejection_flow(conductor):
    """Guarantees that a coordinate outside the clearance boundary instantly terminates the calculation loop."""
    # Run an extension request completely outside physical limits
    ik_output = conductor.calculate_ik(100.0, 100.0, 100.0)
    assert ik_output is None


# ==============================================================================
# MODULE 3: TRANSPORT SPY EXECUTION VALIDATION
# ==============================================================================

def test_move_to_target_serial_stream_spy(conductor):
    """Intercepts serial stream execution to verify that 3 clean sequential packets are emitted to the bus hardware."""
    # 1. Instantiate a MagicMock spy and hot-swap the serial connection descriptor block
    mock_serial = MagicMock()
    conductor.serial_connection = mock_serial
    
    # 2. Command a valid physical path move coordination target
    execution_success = conductor.move_to_target(10.0, 10.0, 2.0)
    
    assert execution_success is True
    # 3. Assert that write was called exactly 3 times (Base packet, Shoulder packet, Elbow packet)
    assert mock_serial.write.call_count == 3
    
    # Extract the exact byte segments passed down the serial bus wire array
    written_bytes = [call.args[0] for call in mock_serial.write.call_args_list]
    for frame in written_bytes:
        assert len(frame) == 6
        assert frame[0] == conductor.SYNC_1
        assert frame[1] == conductor.SYNC_2

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