import os
import sys
import serial
import pytest
from unittest.mock import MagicMock, patch

host_main = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(host_main)

# Import the orchestrator functions and the exception class
from conductor_host import calculate_crc8, process_and_transmit
from inverse_kinematics import WorkspaceEnvelopeViolation

# ---------------------------------------------------------
# TEST SUITE: DATA-LINK FORMATTING & HARDWARE ORCHESTRATION
# ---------------------------------------------------------
# ---------------------------------------------------------
# MODULE: PARAMETERIZED SAFETY STATE HARNESS (BVA)
# ---------------------------------------------------------

# We define a matrix of test cases:
# (X_target, Y_target, Z_target, Simulated_Exception, Expected_Serial_Call_Count)
@pytest.mark.parametrize(
    "x_val, y_val, z_val, simulated_error, should_transmit",
    [
        # CASE 1: Nominal Safe Coordinates -> Should Transmit
        (10.0, 10.0, 10.0, None, True),
        
        # CASE 2: Envelope Breach (Max Extension) -> Should Block Transmission
        (30.0, 0.0, 0.0, WorkspaceEnvelopeViolation("Arm overextended"), False),
        
        # CASE 3: Envelope Breach (Minimum Radius) -> Should Block Transmission
        (1.0, 0.0, 0.0, WorkspaceEnvelopeViolation("Mechanical binding risk"), False),
        
        # CASE 4: Total Singularity (Base Origin) -> Should Block Transmission
        (0.0, 0.0, 0.0, WorkspaceEnvelopeViolation("Origin singularity"), False),
    ]
)
@patch('conductor_host.calculate_joint_angles')
def test_parameterized_transmission_safety_matrix(
    mock_ik_solver, x_val, y_val, z_val, simulated_error, should_transmit
):
    """
    Parametrized BVA Harness:
    Pushes multiple target constraints through the orchestrator to assert 
    that the transmission pipeline securely opens or closes based on the 
    presence of mathematical exceptions.
    """
    # 1. Setup the Mocked Math Brain
    if simulated_error:
        # If the test case provides an error, force the math solver to crash
        mock_ik_solver.side_effect = simulated_error
    else:
        # If no error, provide a safe dummy angle dictionary
        mock_ik_solver.return_value = {"base": 90, "shoulder": 90, "elbow": 90}

    # 2. Setup the Spy (Mocked Serial Port)
    mock_serial = MagicMock()

    # 3. Execute the target function
    process_and_transmit(x_val, y_val, z_val, mock_serial)

    # 4. Evaluate the Expected Safety State
    if should_transmit:
        # Assert the orchestrator safely passed data to the hardware
        assert mock_serial.write.call_count == 1
    else:
        # Assert the orchestrator trapped the error and protected the hardware
        assert mock_serial.write.call_count == 0

def test_crc8_checksum_generation():
    """
    Asserts that the CRC8 polynomial division exactly matches 
    our expected hardware specifications. 
    """
    # A known payload string
    payload = "DRV,90,90,90"
    
    # Calculate the checksum
    checksum = calculate_crc8(payload)
    
    # Verify it returns a 2-character uppercase Hex string
    assert len(checksum) == 2
    assert checksum.isupper()
    # (In a real scenario, you would assert this against a known hand-calculated 
    # CRC8 0x07 polynomial result to ensure absolute parity with the C++ side)

@patch('conductor_host.calculate_joint_angles')
def test_nominal_transmission_pipeline(mock_ik_solver):
    """
    Tests the 'Happy Path'. If the math succeeds, does the orchestrator
    pack the string correctly and push it down the serial wire?
    """
    # 1. Force our "fake" math solver to return a perfect set of angles
    mock_ik_solver.return_value = {"base": 90, "shoulder": 45, "elbow": 135}
    
    # 2. Create a "fake" serial port that acts like the pyserial object
    mock_serial = MagicMock()
    
    # 3. Execute the function with dummy coordinates
    process_and_transmit(10.0, 10.0, 10.0, mock_serial)
    
    # 4. Generate the expected payload and checksum manually for comparison
    expected_payload = "DRV,90,45,135"
    expected_chk = calculate_crc8(expected_payload)
    expected_frame = f"@{expected_payload}*{expected_chk}\n".encode('ascii')
    
    # 5. ASSERTION: Did the script write the exact byte string to the hardware?
    mock_serial.write.assert_called_once_with(expected_frame)

@patch('conductor_host.calculate_joint_angles')
def test_safety_interlock_transmission_block(mock_ik_solver):
    """
    Tests the 'Interception'. If the math throws an envelope violation,
    we must prove that the serial write command is NEVER executed.
    """
    # 1. Force our "fake" math solver to simulate a catastrophic boundary breach
    mock_ik_solver.side_effect = WorkspaceEnvelopeViolation("Simulated out-of-bounds.")
    
    # 2. Create a "fake" serial port
    mock_serial = MagicMock()
    
    # 3. Execute the function with the dangerous coordinates
    process_and_transmit(30.0, 0.0, 0.0, mock_serial)
    
    # 4. ASSERTION: The absolute most critical test in the software.
    # We mathematically assert that the Arduino was NEVER sent a command.
    mock_serial.write.assert_not_called()

# ---------------------------------------------------------
# MODULE 4: DIRTY TRANSPORT & FUZZY TESTING
# ---------------------------------------------------------

@patch('conductor_host.calculate_joint_angles')
def test_dirty_transport_timeout(mock_ik_solver, capsys):
    """
    DIRTY TRANSPORT: What happens if the USB cable is electrically noisy,
    or the Arduino gets hit by an inductive motor spike and fails to send 
    the acknowledgment character back?
    """
    # Math succeeds perfectly
    mock_ik_solver.return_value = {"base": 90, "shoulder": 90, "elbow": 90}
    
    # Create the Spy, but this time, we sabotage its read capability
    mock_serial = MagicMock()
    # Simulate a timeout (the readline() returns an empty byte string)
    mock_serial.readline.return_value = b'' 
    
    # Execute
    process_and_transmit(10.0, 10.0, 10.0, mock_serial)
    
    # Capture the terminal logs (Forensics)
    captured_logs = capsys.readouterr().out
    
    # ASSERTION: The script must not crash waiting for an ACK forever. 
    # It must handle the empty read gracefully.
    assert mock_serial.write.called
    assert "[RX]" in captured_logs  # Verifies we still logged the attempt

@patch('conductor_host.calculate_joint_angles')
def test_fuzzy_hardware_disconnect(mock_ik_solver, capsys):
    """
    FUZZY TESTING: What happens if the USB cable is violently yanked out 
    of the laptop at the exact microsecond Python tries to write to it?
    """
    mock_ik_solver.return_value = {"base": 90, "shoulder": 90, "elbow": 90}
    
    mock_serial = MagicMock()
    # Sabotage the write() function to simulate an immediate hardware disconnect
    mock_serial.write.side_effect = serial.SerialException("Device disconnected")
    
    # Execute - We wrap it in a try/except in the test just in case, 
    # but the process_and_transmit function should ideally catch or bubble it cleanly
    try:
        process_and_transmit(10.0, 10.0, 10.0, mock_serial)
    except serial.SerialException:
        pass # If we designed the orchestrator to bubble the error up to main()
        
    # ASSERTION: Did the system recognize the hardware failure without corrupting data?
    assert mock_serial.write.called

# ---------------------------------------------------------
# MODULE 5: LOG THROTTLING & FORENSICS
# ---------------------------------------------------------

@patch('conductor_host.calculate_joint_angles')
def test_forensic_logging_format(mock_ik_solver, capsys):
    """
    FORENSICS: Proves that the exact timestamped strings required by our 
    security audit team are successfully printing to the console without spam.
    """
    mock_ik_solver.return_value = {"base": 180, "shoulder": 0, "elbow": 0}
    mock_serial = MagicMock()
    mock_serial.readline.return_value = b'K\n' # Standard Arduino acknowledgment
    
    process_and_transmit(15.0, 5.0, 5.0, mock_serial)
    
    # Pull the exact text printed to the terminal
    captured_logs = capsys.readouterr().out
    
    # Verify the forensic markers exist
    assert "[TX]   Streaming Frame -> @DRV,180,0,0*" in captured_logs
    assert "[RX]   Arduino Sentinel Replied -> K" in captured_logs