import struct
import math
import time

class AutoRoboticArmConductor:
    def __init__(self, l1_length_cm=10.0, l2_length_cm=10.0):
        # Kinematic Linkage Lengths (Update to match your PVC cuts)
        self.L1 = l1_length_cm
        self.L2 = l2_length_cm
        
        # Polynomial 0x07 (Standard CRC8)
        self.CRC8_POLYNOMIAL = 0x07 
        
        # Synchronization Headers
        self.SYNC_1 = 0x55
        self.SYNC_2 = 0xAA

    def calculate_ik(self, x, y, z):
        """
        Translates target Cartesian coordinates to 3-Axis Joint Angles.
        Returns: (base_angle, shoulder_angle, elbow_angle) bounded 0-180.
        """

        # Execute Spatial Safety Gate
        if not self.verify_workspace_envelope(x, y, z):
            # Gracefully abort loop rather than allowing a 'math domain error' crash
            return None
        # Base Yaw Angle
        base_rad = math.atan2(y, x)
        
        # Radial distance from base
        r = math.sqrt(x**2 + y**2)
        
        # Straight-line distance squared from shoulder to target
        d_squared = r**2 + z**2
        
        # Law of Cosines for Elbow Angle
        cos_elbow = (d_squared - self.L1**2 - self.L2**2) / (2 * self.L1 * self.L2)
        
        # Clamp to prevent math domain errors on unreachable targets
        cos_elbow = max(-1.0, min(1.0, cos_elbow))
        elbow_rad = math.acos(cos_elbow)
        
        # Shoulder Pitch Angle
        shoulder_rad = math.atan2(z, r) + math.atan2(self.L2 * math.sin(elbow_rad), 
                                                     self.L1 + self.L2 * math.cos(elbow_rad))
        
        # Convert radians to degrees
        base_deg = math.degrees(base_rad)
        shoulder_deg = math.degrees(shoulder_rad)
        elbow_deg = math.degrees(elbow_rad)
        
        # Clamp bounds strictly for servo limits (0 to 180 degrees)
        return (
            int(max(0, min(180, base_deg))),
            int(max(0, min(180, shoulder_deg))),
            int(max(0, min(180, elbow_deg)))
        )

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

    def pack_binary_frame(self, joint_id, angle):
        """
        Constructs the strict 5-Byte Fixed-Width Binary Frame.
        Format: [0x55] [0xAA] [Joint ID] [Angle] [CRC8]
        """
        payload = [joint_id, angle]
        crc_result = self.calculate_crc8(payload)
        
        # '<BBBBB' = Little-endian, 5 unsigned chars
        frame = struct.pack('<BBBBB', 
                            self.SYNC_1, 
                            self.SYNC_2, 
                            joint_id, 
                            angle, 
                            crc_result)
        return frame

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
            
        # Logging structural diagnostic evaluation to host console
        # print(f"[DIAG] Target Distance: {target_distance:.2cm} | Bounds: [{min_reach}, {max_reach}]")

        # Evaluate coordinate alignment targets against spatial thresholds
        if target_distance > max_reach:
            print(f"[ERR] SPATIAL BOUNDARY VIOLATION: Target ({x}, {y}, {z}) is outside maximum reach envelope ({target_distance:.2f}cm > {max_reach:.1f}cm).")
            return False
            
        if target_distance < min_reach:
            print(f"[ERR] SPATIAL BOUNDARY VIOLATION: Target ({x}, {y}, {z}) drops inside unsafe internal crash envelope ({target_distance:.2f}cm < {min_reach:.1f}cm).")
            return False
            
        return True
    

# ==========================================
# Execution Test Block (Runs Locally on Pi 4)
# ==========================================
if __name__ == "__main__":
    conductor = AutoRoboticArmConductor(l1_length_cm=12.0, l2_length_cm=10.0)
    
    # 1. Target coordinate in space (X, Y, Z in cm)
    target_x, target_y, target_z = 10, 10, 5
    
    # 2. Compute IK mapping
    base_ang, shoulder_ang, elbow_ang = conductor.calculate_ik(target_x, target_y, target_z)
    
    # 3. Pack and visualize frames for Arm Alpha (Joints 0, 1, 2)
    print("--- SPRINT 1: PROTOCOL GENERATION TEST ---")
    
    frame_base = conductor.pack_binary_frame(joint_id=0, angle=base_ang)
    conductor.hex_dump_debugger(frame_base, 0, base_ang)
    
    frame_shoulder = conductor.pack_binary_frame(joint_id=1, angle=shoulder_ang)
    conductor.hex_dump_debugger(frame_shoulder, 1, shoulder_ang)
    
    frame_elbow = conductor.pack_binary_frame(joint_id=2, angle=elbow_ang)
    conductor.hex_dump_debugger(frame_elbow, 2, elbow_ang)