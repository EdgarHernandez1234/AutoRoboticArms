import os
import sys
import serial
import pytest
from unittest.mock import MagicMock, patch

host_main = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src"))
sys.path.append(host_main)

from conductor_host import ConductorHost
from inverse_kinematics import WorkspaceEnvelopeViolation

# =============================================================================
# OPTION A: DETERMINISTIC HARDWARE DRIVER UNIT TESTS
# =============================================================================

@patch('conductor_host.time.sleep') # Mock sleep to make tests run instantly
@patch('conductor_host.serial.Serial')
def test_two_stage_bootstrapped_homing(mock_serial_class, mock_sleep):
    """
    Verifies DTR stabilization, buffer flushing, and the baseline home frame.
    """
    # 1. Setup the Transport Spy
    mock_serial_instance = MagicMock()
    mock_serial_instance.read.return_value = b'K'  # MCU acks successfully
    mock_serial_class.return_value = mock_serial_instance

    conductor = ConductorHost(port="/dev/ttyACM0", baud=115200, timeout=0.5)
    
    # 2. Execute
    success = conductor.connect_and_home()

    # 3. Assertions
    assert success is True
    # Verify OS buffers were flushed to clear bootloader noise
    mock_serial_instance.reset_input_buffer.assert_called_once()
    mock_serial_instance.reset_output_buffer.assert_called_once()
    # Verify the exact baseline homing frame was transmitted
    mock_serial_instance.write.assert_called_once_with(b'@DRV,90,90,90*65\n')


@patch('conductor_host.serial.Serial')
def test_payload_size_security_drop(mock_serial_class, capsys):
    """
    Verifies >24 byte fail-fast drop policy to protect MCU SRAM.
    """
    mock_serial_instance = MagicMock()
    conductor = ConductorHost(port="MOCK", baud=115200, timeout=0.5)
    conductor.ser = mock_serial_instance

    # 1. Execute an intentionally oversized artificial payload
    # (e.g., simulating a float leakage bug bypassing integer casting)
    success = conductor._transmit_and_wait(12345678, 12345678, 12345678)

    # 2. Assertions
    assert success is False
    # The Transport Spy proves the script safely aborted without ever touching the USB wire
    mock_serial_instance.write.assert_not_called()
    
    # Verify forensic logging
    captured = capsys.readouterr()
    assert "[SECURITY ALERT] Dropping oversized payload" in captured.out


@patch('conductor_host.calculate_joint_angles')
@patch('conductor_host.serial.Serial')
def test_kinematic_exception_heartbeat(mock_serial_class, mock_ik):
    """
    Verifies trapping math exceptions and sending keep-alives.
    """
    mock_serial_instance = MagicMock()
    mock_serial_instance.read.return_value = b'K'
    conductor = ConductorHost(port="MOCK", baud=115200, timeout=0.5)
    conductor.ser = mock_serial_instance
    conductor.last_valid_angles = {"base": 90, "shoulder": 90, "elbow": 90}

    # 1. Force the IK solver to raise the workspace boundary violation
    mock_ik.side_effect = WorkspaceEnvelopeViolation("Target out of bounds")

    # 2. Execute the dispatch (e.g., commanding it to reach 30cm away)
    conductor.dispatch_trajectory(30.0, 0.0, 0.0)

    # 3. Assertions
    # The script should catch the error (not crash) and send the last known valid angle (90,90,90) 
    # to feed the 3000ms watchdog without physically moving the arm.
    mock_serial_instance.write.assert_called_once_with(b'@DRV,90,90,90*65\n')


@patch('builtins.input', return_value='') # Mocks the user pressing ENTER on the terminal
@patch('conductor_host.time.sleep')
@patch('conductor_host.serial.Serial')
def test_safe_hold_rearming_burst(mock_serial_class, mock_sleep, mock_input):
    """
    Verifies the 'H' Safety-Hold trap and 3-frame synchronization burst.
    """
    mock_serial_instance = MagicMock()
    # Simulate the MCU sending an 'H' (Halt), followed by 3 ACKs during the re-arm burst
    mock_serial_instance.read.side_effect = [b'H', b'H', b'H', b'K']
    
    conductor = ConductorHost(port="MOCK", baud=115200, timeout=0.5)
    conductor.ser = mock_serial_instance
    conductor.last_valid_angles = {"base": 90, "shoulder": 45, "elbow": 135}

    # 1. Execute a transmission that receives an 'H'
    success = conductor._transmit_and_wait(90, 45, 135)

    # 2. Assertions
    assert success is False # The initial frame request failed
    
    # 1 initial write + 3 re-arming burst writes = 4 total writes
    assert mock_serial_instance.write.call_count == 4
    
    # Verify the burst used the locked holding angles
    expected_sync_frame = b'@DRV,90,45,135*53\n'
    mock_serial_instance.write.assert_called_with(expected_sync_frame)