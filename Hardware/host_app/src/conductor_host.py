import serial
import time
import sys

# 1. DECOUPLED ARCHITECTURAL IMPORT
from inverse_kinematics import calculate_joint_angles, WorkspaceEnvelopeViolation

# 2. HARDWARE CONFIGURATION
TARGET_PORT = "/dev/ttyACM0"  # Update to /dev/tty.usbmodem14101 for macOS if needed
BAUD_RATE = 115200
SERIAL_TIMEOUT = 0.5          # Strict 500ms timeout for closed-loop blocking
IDLE_KEEPALIVE_SEC = 2.0      # Feed the microcontroller's 3000ms watchdog

def calculate_xor_checksum(payload: str) -> str:
    """
    Calculates an 8-bit uppercase bitwise XOR hex checksum.
    """
    checksum = 0
    for char in payload:
        checksum ^= ord(char)
    return f"{checksum:02X}"

class ConductorHost:
    def __init__(self, port: str, baud: int, timeout: float):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.ser = None
        self.last_valid_angles = {"base": 90, "shoulder": 90, "elbow": 90}
        self.last_tx_time = time.time()

    def connect_and_home(self) -> bool:
        """
        Two-Stage Bootstrapped Homing Protocol.
        Safely initializes the serial port, waits for DTR stabilization, 
        and establishes a hardware baseline at 90, 90, 90.
        """
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
            print(f"[SYSTEM] Port {self.port} opened. Waiting 2.0s for DTR reset stabilization...")
            time.sleep(2.0)
            
            # Flush OS buffers to eliminate transient bootloader electrical noise
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            print("[SYSTEM] Transmitting Stage-2 Baseline Home Frame: @DRV,90,90,90*5A")
            return self._transmit_and_wait(90, 90, 90)
            
        except serial.SerialException as e:
            print(f"[FATAL] Could not connect to {self.port}: {e}")
            sys.exit(1)

    def _transmit_and_wait(self, base: int, shoulder: int, elbow: int) -> bool:
        """
        Packs the ASCII envelope, enforces the 24-byte payload clamp, 
        transmits the frame, and blocks for the 1-byte return ACK.
        """
        # Ensure strict integer casting
        payload = f"DRV,{int(base)},{int(shoulder)},{int(elbow)}"
        
        # Jax's Security Gate: 24-Byte Ceiling Drop Policy
        if len(payload) > 24:
            print(f"[SECURITY ALERT] Dropping oversized payload ({len(payload)} bytes): '{payload}'")
            return False
            
        chk = calculate_xor_checksum(payload)
        frame = f"@{payload}*{chk}\n"
        
        # Transmit frame
        self.ser.write(frame.encode('ascii'))
        self.last_tx_time = time.time()
        
        # Marcus's Closed-Loop Flow Control: Block for ACK
        ack = self.ser.read(1).decode('ascii', errors='ignore')
        
        if not ack:
            print("[ALERT] Serial Read Timeout (b''). Communication drop detected.")
            self.handle_safety_halt()
            return False
            
        if ack == 'K':
            # Nominal execution: update state cache
            self.last_valid_angles = {"base": base, "shoulder": shoulder, "elbow": elbow}
            return True
        elif ack == 'E':
            print(f"[WARNING] MCU flagged Checksum/Format Error on frame: {frame.strip()}")
            return False
        elif ack == 'H':
            print("[ALERT] MCU responded with 'H' (Safe-Hold active).")
            self.handle_safety_halt()
            return False
        else:
            print(f"[WARNING] Unknown MCU response: '{ack}'")
            return False

    def handle_safety_halt(self):
        """
        Human-in-the-Loop Confirmation & 3-Frame Trust Burst Re-Arming.
        """
        print("[SAFETY] Interlock tripped ('H' or timeout). Workspace inspection required.")
        input("[USER ACTION REQUIRED] Inspect workspace. Press ENTER to transmit 3-frame re-arm burst...")
        
        base, shldr, elbow = self.last_valid_angles["base"], self.last_valid_angles["shoulder"], self.last_valid_angles["elbow"]
        payload = f"DRV,{base},{shldr},{elbow}"
        chk = calculate_xor_checksum(payload)
        sync_frame = f"@{payload}*{chk}\n".encode('ascii')
        
        print("[SYSTEM] Transmitting 3-Frame Trust Burst...")
        for i in range(3):
            self.ser.write(sync_frame)
            ack = self.ser.read(1).decode('ascii', errors='ignore')
            print(f"[RE-ARM STEP {i+1}/3] MCU Response: '{ack}'")
            time.sleep(0.02) # 20ms cadence
            
        if ack == 'K':
            print("[SYSTEM] Hardware Re-Armed Successfully. Link restored.")
            self.last_tx_time = time.time()
        else:
            print("[FATAL] Re-arming failed. MCU remains locked.")
            sys.exit(1)

    def dispatch_trajectory(self, x: float, y: float, z: float):
        """
        Primary execution entry point for spatial targets.
        """
        print(f"\n[HOST] Processing Cartesian Target (X:{x}, Y:{y}, Z:{z})")
        try:
            # Delegate math to the IK solver
            angles = calculate_joint_angles(x, y, z)
            print(f"[MATH] Kinematics Solved -> {angles}")
            
            # Execute transmit (assuming trajectory velocity slew-rate is managed upstream or handled by MCU)
            success = self._transmit_and_wait(angles["base"], angles["shoulder"], angles["elbow"])
            if success:
                print(f"[TX]   Successfully synchronized hardware to target.")
                
        except WorkspaceEnvelopeViolation as error:
            # Dr. Julian's Trap: Log the error, do NOT send bad geometry, send a heartbeat instead
            print(f"[SAFETY INTERLOCK] {error}")
            print(f"[SAFETY INTERLOCK] Injecting Null-Delta Heartbeat to maintain 3000ms Watchdog...")
            self.send_heartbeat()

    def send_heartbeat(self):
        """
        Feeds the ATmega328P 3000ms Watchdog using the last known valid physical position.
        """
        base = self.last_valid_angles["base"]
        shldr = self.last_valid_angles["shoulder"]
        elbow = self.last_valid_angles["elbow"]
        self._transmit_and_wait(base, shldr, elbow)

    def process_idle_loop(self):
        """
        Background tick checker to maintain the hardware watchdog if no commands are generated.
        """
        if (time.time() - self.last_tx_time) > IDLE_KEEPALIVE_SEC:
            print("[SYSTEM] Idle limit reached. Transmitting Keep-Alive Heartbeat...")
            self.send_heartbeat()

# =============================================================================
# OPTION A - SINGLE-THREADED SYNCHRONOUS RUNTIME LOOP
# =============================================================================
def main():
    print("=== AutoRoboticArms: Option A Deterministic Hardware Conductor ===")
    
    conductor = ConductorHost(TARGET_PORT, BAUD_RATE, SERIAL_TIMEOUT)
    
    if conductor.connect_and_home():
        print("[SYSTEM] Option A Baseline Online. Ready for Trajectories.\n")
    else:
        print("[FATAL] Bootstrapped homing failed. Exiting.")
        sys.exit(1)

    # Simulated trajectory list (includes an intentional BVA failure)
    trajectory_matrix = [
        (10.0, 10.0, 10.0),   # Nominal safe move
        (30.0, 0.0, 0.0),     # Intentional Envelope Breach (Out of bounds)
        (12.0, 5.0, 8.0)      # Nominal safe move
    ]
    
    try:
        # Step through trajectory array
        for coords in trajectory_matrix:
            conductor.dispatch_trajectory(coords[0], coords[1], coords[2])
            time.sleep(1.0) # Simulate time between trajectory commands
            
        print("\n[SYSTEM] Trajectory complete. Entering Watchdog Keep-Alive Monitoring State...")
        # Simulate an idle system state where the user is no longer sending commands
        while True:
            conductor.process_idle_loop()
            time.sleep(0.1) # 100ms background tick loop
            
    except KeyboardInterrupt:
        print("\n[SYSTEM] User terminated runtime. Closing hardware link.")
        if conductor.ser and conductor.ser.is_open:
            conductor.ser.close()

if __name__ == "__main__":
    main()