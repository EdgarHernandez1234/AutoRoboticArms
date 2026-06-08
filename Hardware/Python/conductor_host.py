import serial
import struct
import math
import time
# Sprint 1 Complete: Host Driver with Inverse Kinematics, CRC8, and Binary Framing for 3-Axis Robotic Arm
portPath = "/dev/ttyACM0"  # Update to match actual serial port path

class WorkspaceEnvelopeViolation(Exception):
    """Raised when a commanded coordinate breaches the safe dual-horizon physical cushions."""
    pass

class AutoRoboticArmConductor:
    def __init__(self, port=portPath, baudrate=115200, l1_length_cm=10.0, l2_length_cm=10.0, safety_mode=True):
        """Initializes the Host Driver for a Single 3-Axis Robotic Arm."""
        # Kinematic Linkage Lengths (Update to match your PVC cuts)
        self.L1 = l1_length_cm
        self.L2 = l2_length_cm
        
        # Polynomial 0x07 (Standard CRC8)
        self.CRC8_POLYNOMIAL = 0x07 
        
        # Synchronization Headers
        self.SYNC_1 = 0x55
        self.SYNC_2 = 0xAA

        # Operational Safety Flag: 
        # True = Strict AI/Downstream Zero-Trust Mode (Throws Hard Exceptions)
        # False = Manual Overrides / Engineering Calibrations Mode (Logs Warnings but Continues)
        self.safety_mode_enabled = safety_mode

        # Attempt to open hardware serial; fallback to Mock mode if cable is disconnected
        try:
            self.serial_connection = serial.Serial(port, baudrate, timeout=1)
            time.sleep(2)  # Allow 2 seconds for Arduino auto-reset upon connection
            print(f"[SYS] Serial Hardware Bound on {port} at {baudrate} Baud.")
        except serial.SerialException:
            print(f"[WARN] Hardware not detected on {port}. Initializing in MOCK mode.")
            self.serial_connection = None

    def angle_to_ticks(self, angle_degrees):
            """
            Translates a geometric angle (0-180) into a 12-bit PCA9685 PWM tick value.
            Standard micro-servo pulse constraints: ~150 (0 deg) to ~600 (180 deg).
            """
            # PCA9685 absolute hardware limits
            SERVO_MIN_TICKS = 150  
            SERVO_MAX_TICKS = 600  
            
            # Clamp the angle safely between 0 and 180 to prevent physical tearing
            clamped_angle = max(0.0, min(180.0, angle_degrees))
            
            # Map the angle linearly to the 12-bit register tick window
            tick_range = SERVO_MAX_TICKS - SERVO_MIN_TICKS
            ticks = SERVO_MIN_TICKS + (clamped_angle / 180.0) * tick_range
            
            # Round to the nearest whole micro-step and cast to integer
            return int(round(ticks))
    
    def calculate_ik(self, x, y, z):
            """
            Translates target Cartesian coordinates to 12-Bit Servo Register Ticks.
            """
            # 1. Execute Spatial Safety Gate (Kept completely unchanged!)
            if not self.verify_workspace_envelope(x, y, z):
                # If strict safety mode is enabled, pull the emergency brake!
                if self.safety_mode_enabled:
                    raise WorkspaceEnvelopeViolation(f"AI/Downstream Target Input ({x}, {y}, {z}) blocked by safety firewall.")
                else:
                    # If in Manual/Engineering mode, bypass the crash block, log a heavy alert, and return None
                    print(f"[MANUAL OVERRIDE] Warning: Coordinate ({x}, {y}, {z}) is out of bounds! Bypassing packet generation safely.")
                    return None

            # 2. Inverse Kinematics Trigonometry (Your math logic here)
            base_angle = math.degrees(math.atan2(y, x))
            # ... (Shoulder and Elbow calculations remain the same)
            
            # 2D Planar distance for arm calculations
            r = math.sqrt(x**2 + y**2)
            
            # Elbow Angle using Law of Cosines
            cos_elbow = (r**2 + z**2 - self.L1**2 - self.L2**2) / (2 * self.L1 * self.L2)
            # Clamp cos_elbow to handle microscopic floating point edge-cases near -1.0 or 1.0
            cos_elbow = max(-1.0, min(1.0, cos_elbow))
            elbow_angle = math.degrees(math.acos(cos_elbow))
            
            # Shoulder Angle using Law of Cosines
            phi = math.atan2(z, r)
            cos_shoulder = (r**2 + z**2 + self.L1**2 - self.L2**2) / (2 * self.L1 * math.sqrt(r**2 + z**2))
            cos_shoulder = max(-1.0, min(1.0, cos_shoulder))
            shoulder_angle = math.degrees(phi + math.acos(cos_shoulder))
    
            # 3. Convert calculated degrees directly to 12-bit hardware pulses
            base_ticks = self.angle_to_ticks(base_angle)
            shoulder_ticks = self.angle_to_ticks(shoulder_angle)
            elbow_ticks = self.angle_to_ticks(elbow_angle)
            
            return base_ticks, shoulder_ticks, elbow_ticks

    def calculate_crc8(self, data_bytes):
        """
        Calculates CRC8 remainder.
        data_bytes: list or bytearray of data to hash.
        """
        crc = 0x00
        for byte in data_bytes:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ self.CRC8_POLYNOMIAL
                else:
                    crc <<= 1
                crc &= 0xFF # Force 8-bit wrap
        return crc

    def pack_binary_frame(self, joint_id, raw_duty_ticks):
            """
            Compiles the control parameters into a strict 6-Byte Big-Endian packet.
            Format: [0x55] [0xAA] [Joint_ID] [Ticks_High] [Ticks_Low] [CRC8]
            """
            # Step 1: Pack just the data payload to calculate the checksum
            # '!BH' = Big-Endian: Unsigned Byte (Joint_ID) + Unsigned Short (16-bit Ticks)
            data_payload = struct.pack('!BH', joint_id, raw_duty_ticks)
            
            # Step 2: Run data payload through your CRC8 algorithm
            crc8_checksum = self.calculate_crc8(data_payload)
            
            # Step 3: Pack the complete 6-byte outbound frame
            # '!BBBHB' = Big-Endian: Sync1, Sync2, Joint_ID, 16-bit Ticks, CRC8
            full_frame = struct.pack('!BBBHB',  self.SYNC_1,  self.SYNC_2, joint_id, raw_duty_ticks, crc8_checksum)
            
            return full_frame

    def hex_dump_debugger(self, frame, joint_id, angle):
        """
        Real-time Protocol Analyzer wrapper for terminal monitoring.
        """
        hex_string = " | ".join([f"0x{b:02X}" for b in frame])
        timestamp = time.strftime("%H:%M:%S.{}".format(int((time.time() % 1) * 1000)))
        
        print(f"[TX] Time: {timestamp}")
        print(f"RAW HEX:  [ {hex_string} ]")
        print(f"MAPPED:   [ SYNC | ID: {joint_id} | ANG: {angle}° | CRC: 0x{frame[4]:02X} ]")
        print("-" * 60)

    def angle_to_ticks(self, angle_degrees):
            """
            Translates a geometric angle (0-180) into a 12-bit PCA9685 PWM tick value.
            Standard micro-servo pulse constraints: ~150 (0 deg) to ~600 (180 deg).
            """
            # PCA9685 absolute hardware limits
            SERVO_MIN_TICKS = 150  
            SERVO_MAX_TICKS = 600  
            
            # Clamp the angle safely between 0 and 180 to prevent physical tearing
            clamped_angle = max(0.0, min(180.0, angle_degrees))
            
            # Map the angle linearly to the 12-bit register tick window
            tick_range = SERVO_MAX_TICKS - SERVO_MIN_TICKS
            ticks = SERVO_MIN_TICKS + (clamped_angle / 180.0) * tick_range
            
            # Round to the nearest whole micro-step and cast to integer
            return int(round(ticks))
    
    def verify_workspace_envelope(self, x, y, z):
        """
        Defensive Workspace Envelope Filter (Spatial Boundary Check).
        Calculates the 3D Euclidean distance from origin to target.
        Returns: True if reachable/safe, False if outside physical envelope.
        """
        # Calculate absolute straight-line distance in 3D space (Pythagorean extension)
        target_distance = math.sqrt(x**2 + y**2 + z**2)
        
        # Define upper physical reach constraint (Maximum arm extension)
        max_reach = self.L1 + self.L2
        
        # Define lower clearance constraint (Prevents arm from self-colliding with base mechanics)
        min_reach = abs(self.L1 - self.L2)
        
        # Handle zero clearance fallback if links are completely identical lengths
        if min_reach == 0:
            min_reach = 2.0  # Safe explicit baseline clearance boundary (cm)
            
        # Enforce our defensive Singularity Mitigation Margin (0.5cm clearance)
       
        # Brings safe operating boundary down from 22.0cm to 21.5cm
        safe_operating_max = max_reach - 0.5
        
        # Brings safe operating boundary down from 2 cm to 2.5cm
        safe_operating_min = min_reach + 0.5
        
        # Logging structural diagnostic evaluation to host console
        # print(f"[DIAG] Target Distance: {target_distance:.2cm} | Bounds: [{min_reach}, {max_reach}]")

        # Evaluate coordinate alignment targets against spatial thresholds
        if target_distance > safe_operating_max:
            print(f"[ERR] SPATIAL BOUNDARY VIOLATION: Target ({x}, {y}, {z}) is outside maximum reach envelope ({target_distance:.2f}cm > {max_reach:.1f}cm).")
            return False
            
        if target_distance < safe_operating_min:
            print(f"[ERR] SPATIAL BOUNDARY VIOLATION: Target ({x}, {y}, {z}) drops inside unsafe internal crash envelope ({target_distance:.2f}cm < {min_reach:.1f}cm).")
            return False
            
        return True
    
    def move_to_target(self, x, y, z):
            """Master execution wrapper to calculate IK and stream to physical wire."""
            target_ticks = self.calculate_ik(x, y, z)
            
            if target_ticks is None:
                return False # Bypassed by spatial envelope filter
                
            base_t, shoulder_t, elbow_t = target_ticks
            
            # Generate 3 dedicated frames for Joints 0, 1, and 2
            frames = [
                self.pack_binary_frame(0, base_t),
                self.pack_binary_frame(1, shoulder_t),
                self.pack_binary_frame(2, elbow_t)
            ]
            
            # Transmit to hardware
            if self.serial_connection:
                for frame in frames:
                    self.serial_connection.write(frame)
                    time.sleep(0.01) # 10ms micro-pause to prevent Arduino ring buffer flooding
                print(f"[TX] Pushed Frame -> Ticks: B:{base_t} S:{shoulder_t} E:{elbow_t}")
            else:
                print(f"[MOCK TX] Target: ({x}, {y}, {z}) -> Ticks: B:{base_t} S:{shoulder_t} E:{elbow_t}")
                
            return True

# ==========================================
# Execution Test Block (Runs Locally on Pi 4)
# ==========================================
if __name__ == "__main__":
    print("--- AutoRoboticArms Host Conductor Initialization ---")
    
    # Instantiate the host driver
    arm = AutoRoboticArmConductor(port=portPath, baudrate=115200, l1_length_cm=10.0, l2_length_cm=10.0, safety_mode=True)
    
    # Test 1: Valid Nominal Reach
    print("\n[Test 1] Nominal Reach Check (10, 10, 5)")
    arm.move_to_target(10, 10, 5)
    
    # Test 2: Over-Extension Reach 
    print("\n[Test 2] Over-Extension Check (50, 50, 50)")
    arm.move_to_target(50, 50, 50)
