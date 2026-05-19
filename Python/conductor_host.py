import time
import sys
import serial

class ConductorHost:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        """
        Initializes the Serial Communication Host handler.
        Emulates the high-level autonomy transmitter layer.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.connection = None
        
    def connect(self):
        """Establishes connection with the microcontroller target."""
        try:
            self.connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            # Allow time for Arduino's bootloader to reset upon serial opening
            time.sleep(2)
            print(f"[INFO] Successfully bound to serial interface target: {self.port}")
        except serial.SerialException as e:
            print(f"[ERROR] Critical failure connecting to port {self.port}: {e}")
            sys.exit(1)

    def calculate_xor_checksum(self, payload: str) -> str:
        """
        Computes a strict 8-bit bitwise XOR check across every individual 
        ASCII character byte within the active message payload string bounds.
        Returns a 2-digit uppercase hexadecimal token string format.
        """
        checksum = 0
        for character in payload:
            checksum ^= ord(character)
        return f"{checksum:02X}"

    def send_command(self, cmd_type: str, left_angle: int, right_angle: int):
        """
        Formats, computes, validates, and transmits a formatted frame command packet.
        Format Shape: @<payload>*<checksum>\n
        Example Target output: @DRV,90,45*4A\n
        """
        if not self.connection or not self.connection.is_open:
            print("[WARN] Transmission dropped: Serial hardware port is not open.")
            return

        # Build the exact data payload block
        payload = f"{cmd_type},{left_angle},{right_angle}"
        
        # Calculate the cryptographic/data-integrity bitwise verification field
        checksum_hex = self.calculate_xor_checksum(payload)
        
        # Seal the packet using our strict frame start/stop indicators
        final_packet = f"@{payload}*{checksum_hex}\n"
        
        try:
            # Cast the string down to raw data-stream bytes over the physical wire
            self.connection.write(final_packet.encode('ascii'))
            self.connection.flush() # Flush buffer to force immediate electrical release
            print(f"[TX SEND] Outbound packet transmitted: {final_packet.strip()}")
        except Exception as e:
            print(f"[ERROR] Packet transmission failure: {e}")

    def close(self):
        """Gracefully tears down connection."""
        if self.connection and self.connection.is_open:
            self.connection.close()
            print("[INFO] Serial interface port closed cleanly.")

# --- Desk Simulation Execution Harness ---
if __name__ == "__main__":
    # USER NOTE: Swap out the device identifier below with your local system configuration path:
    # Windows Target Ex: 'COM3' or 'COM4'
    # macOS/Linux Target Ex: '/dev/ttyACM0' or '/dev/tty.usbmodem14101'
    TARGET_PORT = "COM3" 
    
    host = ConductorHost(port=TARGET_PORT, baudrate=115200)
    host.connect()
    
    try:
        print("\n--- Initiating Conductor Sequence Sprints ---")
        # Command 1: Move left arm to 90 degrees, right arm to 45 degrees
        host.send_command("DRV", 90, 45)
        time.sleep(1.5)
        
        # Command 2: Shift arms to execute a wide sweeping wave
        host.send_command("DRV", 120, 120)
        time.sleep(1.5)
        
        # Command 3: Return to safe hold / zero initialization boundary
        host.send_command("DRV", 0, 0)
        time.sleep(1.0)
        
    except KeyboardInterrupt:
        print("\n[WARN] Execution sequence manually broken by user interface interrupt.")
    finally:
        host.close()