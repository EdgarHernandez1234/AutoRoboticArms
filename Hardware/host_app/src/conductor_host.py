import serial
import time
import sys

# 1. DECOUPLED ARCHITECTURAL IMPORT
# We import our independent math module and its custom safety exception
from inverse_kinematics import calculate_joint_angles, WorkspaceEnvelopeViolation
from database_manager import log_telemetry_state, initialize_database
# 2. HARDWARE CONFIGURATION
TARGET_PORT = "/dev/tty.usbmodem14101"  # Update to 'COM3' if using Windows or /dev/tty.usbmodem14101 for MacOS, ttyACM0 for Linux
BAUD_RATE = 115200
SERIAL_TIMEOUT = 0.5  # Strict 50ms timeout window to intercept hardware drops

def calculate_crc8(payload: str) -> str:
    """
    Calculates a robust CRC8 checksum using the 0x07 polynomial divisor.
    This replaces the weak simple-XOR approach and matches the Arduino's C++ logic.
    """
    crc = 0x00
    for char in payload:
        # XOR the next byte of the string into the current CRC register
        crc ^= ord(char)
        # Shift bits left 8 times, applying the 0x07 polynomial via XOR if the highest bit is 1
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x07
            else:
                crc <<= 1
            # Apply an 8-bit mask to prevent integer overflow in Python
            crc &= 0xFF 
            
    return f"{crc:02X}"

# 4. SENTINEL HANDSHAKE & RE-SYNC METHOD
def await_sentinel_beacon(ser: serial.Serial) -> bool:
    """
    Blocks normal execution until the physical silicon finishes booting
    and broadcasts its verified '@INIT_READY*5F' initialization token.
    """
    print("[SYSTEM] Entering blocking synchronization hook. Awaiting Sentinel Beacon...")
    
    # Temporarily extend timeout to catch the physical reset lifecycle window
    old_timeout = ser.timeout
    ser.timeout = 3.0
    
    # Flush any electrical noise out of the host OS buffers
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    try:
        incoming_line = ser.readline().decode('ascii', errors='ignore').strip()
        if incoming_line == "@INIT_READY*5F":
            print("[RX]   Captured Verified Microcontroller Beacon: @INIT_READY*5F")
            
            # Send back the confirmation handshake token required by the setup() loop
            ser.write(b'A') 
            print("[TX]   Handshake Confirmed. Data-Link Synchronized.")
            return True
        else:
            print(f"[ERROR] Discovered Malformed Ingress Garbage on initialization: '{incoming_line}'")
            return False
    finally:
        # Crucial: Always restore the tight mechatronic processing timeout limits
        ser.timeout = old_timeout

# 5. ATOMIC PROCESSING TIMING LOOPS
def process_and_transmit(x: float, y: float, z: float, ser: serial.Serial) -> bool:
    """
    Coordinates geometry delegation, bitwise packing, streaming, 
    and handles live recovery states if an ACK timeout is triggered.
    """
    target_coordinates = {"x": x, "y": y, "z": z}
    print(f"\n[HOST] Command Input: Spatial Target (X:{x}, Y:{y}, Z:{z})")
    
    try:
        # STEP A: Delegate heavy trigonometry to the isolated IK solver
        angles = calculate_joint_angles(x, y, z)
        print(f"[MATH] Kinematics Solved -> Base:{angles['base']}°, Shldr:{angles['shoulder']}°, Elbow:{angles['elbow']}°")

        # STEP B: Construct the comma-separated data payload
        payload = f"DRV,{angles['base']},{angles['shoulder']},{angles['elbow']}"
        
        # STEP C: Generate the cryptographic checksum and seal the frame
        chk = calculate_crc8(payload)
        hardware_frame = f"@{payload}*{chk}\n"
        
        # STEP D: Transmit binary bytes down the physical wire
        print(f"[TX]   Streaming Frame -> {hardware_frame.strip()}")
        ser.write(hardware_frame.encode('ascii'))
        
        # STEP E: Await the deterministic hardware loop acknowledgement
        ack = ser.readline().decode('ascii', errors='ignore').strip()
        print(f"[RX]   Arduino Sentinel Replied -> {ack}")
        # MID-RUN RESET TRAP: If empty string returns, a serial dropout has occurred
        if not ack:
            print("[ALERT] Serial Ack Timeout! Hardware drop encountered.")
            # Record the mid-run crash state forensic data down to the log table
            log_telemetry_state(target_coordinates, angles=None, status="MICRO_RESET", checksum=chk)
            
            # Execute re-synchronization recovery routine immediately
            if await_sentinel_beacon(ser):
                return False # Recovery successful, frame aborted but channels are clear
            else:
                raise serial.SerialException("Microservice completely unresponsive.")
                
        print(f"[RX]   Sentinel Replied -> {ack}")
        log_telemetry_state(target_coordinates, angles, status="NOMINAL", checksum=chk)
        return True
    except WorkspaceEnvelopeViolation as error:
        # THE FALLBACK TRAP: Math failed. The serial_port.write() is never called!
        print(f"[SAFETY INTERLOCK] {error}")
        log_telemetry_state(target_coordinates, angles=None, status="BLOCKED", checksum="00")
        print("[SAFETY INTERLOCK] Transmission aborted. Hardware remains parked.")
        return False

def main():
    print("=== AutoRoboticArms: Host Orchestrator Initialized ===")
    
    initialize_database() # Ensure the telemetry database is ready for logging

    try:
        # Open the hardware data-link layer
        with serial.Serial(TARGET_PORT, BAUD_RATE, timeout=SERIAL_TIMEOUT) as ser:
            print(f"[SYSTEM] Hardware linked on {TARGET_PORT} at {BAUD_RATE} baud.")
            time.sleep(2) # Allow Arduino bootloader to initialize
            
            # Execute a structured physical test path
            test_trajectory_matrix = [
                (10.0, 10.0, 10.0),  # Nominal safe move
                (12.0, 5.0, 8.0),    # Nominal safe move
                (30.0, 0.0, 0.0)     # Intentional Envelope Breach (Out of bounds)
            ]
            
            for coordinates in test_trajectory_matrix:
                process_and_transmit(coordinates[0], coordinates[1], coordinates[2], ser)
                time.sleep(1) # Paces the loop to match physical actuator speeds
                
    except serial.SerialException:
        print(f"[FATAL] Could not open port {TARGET_PORT}. Check USB connections.")
        sys.exit(1)

if __name__ == "__main__":
    main()