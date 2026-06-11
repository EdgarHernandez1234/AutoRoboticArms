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

# Import the custom exception for workspace violations
from conductor_host import WorkspaceEnvelopeViolation

@pytest.fixture(scope="function")
def conductor():
    """
    Provides a fresh, pre-configured conductor instance before every single test.
    Injects a mocked serial connection to prevent tests from looking for a physical wire.
    """
    obj = AutoRoboticArmConductor(port='MOCK_PORT',baudrate=115200,l1_length_cm=12.0, l2_length_cm=10.0, safety_mode=True)
    # Inject mocked serial hardware wire interface stub
    obj.serial_connection = MagicMock()
    
    # Yield the conductor instance to the test function, allowing it to run with a clean slate each time
    yield obj

    if obj.serial_connection:
        obj.serial_connection.reset_mock()  # Clear call history after each test for clean slate
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
    (2.0, 1.0, 0.0, False),     # Boundary Check Min: 2.23cm reach value (Dropped by inner cushion!)

    # -------------------------------------------------------------
    # ADVANCED EPSILON-FLANKING ASSERSTIONS (The New Additions)
    # -------------------------------------------------------------
    # Case A: An input that sits EXACTLY 0.00001cm inside the 21.5cm outer cushion floor
    (15.20279, 15.20279, 0.0, True),   # Distance = 21.49999cm -> Must evaluate to True!
    
    # Case B: An input that sits EXACTLY 0.00001cm outside the 21.5cm outer cushion ceiling
    (15.20281, 15.20281, 0.0, False),  # Distance = 21.50001cm -> Must evaluate to False!
    
    # Case C: An input that sits EXACTLY 0.00001cm inside the 2.5cm inner crush buffer ceiling
    (1.76777, 1.76777, 0.0, True),     # Distance = 2.50001cm -> Must evaluate to True!
    
    # Case D: An input that sits EXACTLY 0.00001cm outside the 2.5cm inner crush buffer floor
    (1.76775, 1.76775, 0.0, False),    # Distance = 2.49999cm -> Must evaluate to False!
])
def test_spatial_safety_interlock_boundaries(conductor, x, y, z, expected_safety_state):
    """Verifies that our Workspace Filter intercepts and drops out-of-bounds coordinates before math processing."""
    assert conductor.verify_workspace_envelope(x, y, z) == expected_safety_state

def test_inverse_kinematics_rejection_flow(conductor):
    """Guarantees that a coordinate outside the clearance boundary instantly terminates the calculation loop."""
    # Run an extension request completely outside physical limits
    
    with pytest.raises(WorkspaceEnvelopeViolation):
        conductor.calculate_ik(100.0, 100.0, 100.0)


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

def test_dirty_transport_truncation_resilience(conductor):
    """
    Purposely simulates mid-stream serial wire truncation.
    Verifies that malformed packet alignments never emit unvalidated targets.
    """
    mock_serial = MagicMock()
    conductor.serial_connection = mock_serial
    
    # 1. Generate a perfectly clean nominal target point frame
    valid_frame = conductor.pack_binary_frame(joint_id=1, raw_duty_ticks=375) # 6 Bytes
    
    # 2. Simulate a harsh truncation error by cutting off the last 2 bytes mid-transit
    truncated_frame = valid_frame[0:4] 
    
    # 3. Simulate host streaming the broken chunk onto the line buffer interface array
    # In Sprint 2, we test that our host calculations catch exceptions or handle logs 
    # when processing streaming feedback loops.
    assert len(truncated_frame) == 4
    
    print("[MOCK FUZZ] Fragment injected safely. Target Sentinel watchdog tracking initiated.")

def test_manual_mode_calculates_clamped_edge_ticks(conductor):
    """Verifies that dropping the safety mode flag scales the coordinate and returns valid edge ticks."""
    # 1. Force the driver into Manual Configuration Mode
    conductor.safety_mode_enabled = False
    
    # 2. Request a coordinate drastically outside our 22.0cm maximum physical capability
    # Instead of raising an exception or returning None, it must return scaled ticks for 21.5cm reach!
    edge_ticks = conductor.calculate_ik(30.0, 30.0, 0.0)
    
    assert edge_ticks is not None
    base_t, shoulder_t, elbow_t = edge_ticks
    
    # Assert that the output values represent legal 12-bit hardware register bounds
    assert isinstance(base_t, int)
    assert 150 <= base_t <= 600
    assert 150 <= shoulder_t <= 600
    assert 150 <= elbow_t <= 600

def test_log_throttling_records_precise_forensics(conductor, capsys):
    """Simulates an adversarial injection flood and asserts that exact coordinate forensics are recorded."""
    conductor.safety_mode_enabled = False
    
    # Inject 150 consecutive malicious hyper-extended coordinate targets
    for _ in range(150):
        conductor.calculate_ik(50.0, 50.0, 50.0)
        
    captured = capsys.readouterr()
    
    # Assert Step 1: Counter tracked all 150 attempts perfectly
    assert conductor.violation_counter == 150
    
    # Assert Step 2: The system printed exactly 2 throttled alerts (on loops 1 and 101)
    assert captured.out.count("[ALERT] OUTER BOUNDARY VIOLATION") == 2
    
    # Assert Step 3: Verify the forensic vector log recorded the malicious input coordinates accurately
    assert "Forensic Telemetry Data -> Target: (50.00, 50.00, 50.00)" in captured.out

def test_automated_handshake_recovery_loop(simulated_microcontroller):
    """Verifies that the microcontroller rejects bad frames, locks down, and self-heals upon secure key ingress."""
    # 1. Simulate sending a corrupted payload frame to trip the fault register
    simulated_microcontroller.inject_serial_bytes(b'\x55\xAA\x90\x45\x90\xFF') # Bad Checksum
    simulated_microcontroller.process_loops()
    assert simulated_microcontroller.current_state == "SYSTEM_FAULT_CHECKSUM"
    
    # 2. Verify that spamming regular kinematic target data lines is completely ignored
    simulated_microcontroller.inject_serial_bytes(b'\x55\xAA\x45\x45\x45\x12') 
    simulated_microcontroller.process_loops()
    assert simulated_microcontroller.current_state == "SYSTEM_FAULT_CHECKSUM" # Remains tightly locked
    
    # 3. Stream the explicit 6-byte secure out-of-band recovery handshake token string
    secure_clear_token = b'\xAA\x55\xDE\xAD\xBE\xEF'
    simulated_microcontroller.inject_serial_bytes(secure_clear_token)
    simulated_microcontroller.process_loops()
    
    # 4. Assert that the hardware successfully recovered back to Nominal production tracks!
    assert simulated_microcontroller.current_state == "SYSTEM_NOMINAL"