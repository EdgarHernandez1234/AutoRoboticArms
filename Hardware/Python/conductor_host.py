import time
import sys
import serial

class ConductorHost:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        """
        Initializes the Serial Communication Host handler.
        Emulates the high-level autonomy transmitter layer with strict QA guards.
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
            # Allow time for Arduino's bootloader to complete its reboot cycle upon serial opening
            time.sleep(2)
            print(f"[INFO] Successfully bound to serial interface target: {self.port}")
        except serial.SerialException as e:
            print(f"[ERROR] Critical failure connecting to port {self.port}: {e}")
            sys.exit(1)

    def calculate_xor_checksum(self, payload: str) -> str:
        """
        Computes an 8-bit bitwise XOR check across every individual 
        ASCII character byte within the active message payload string bounds.
        Returns a 2-digit uppercase hexadecimal token string format.
        """
        checksum = 0
        for character in payload:
            checksum ^= ord(character)
        return f"{checksum:02X}"

    def send_command(self, cmd_type: str, left_angle: int, right_angle: int):
        """
        Validates input boundaries, constructs, checks, and transmits a formatted 
        command packet frame down the physical wire interface.
        
        Format Shape: @<payload>*<checksum>\n
        Example Output: @DRV,90,45*4A\n
        
        Raises:
            ValueError: If the command mnemonic or angle coordinates breach QA safety contracts.
            IOError: If physical transmission over the serial port drops or truncates bytes.
        """
        # --- QA GUARD 1: Mnemonic Equivalence Partitioning Filter ---
        VALID_MNEMONICS = ["DRV"]
        if cmd_type not in VALID_MNEMONICS:
            raise ValueError(f"[QA FAILURE] Invalid system command code type exception: '{cmd_type}'")
            
        # --- QA GUARD 2: Physical Hardware Range Boundary Analysis ---
        # Standard micro servos have a physical mechanical operating range constraint of [0, 180] degrees
        if not (0 <= left_angle <= 180) or not (0 <= right_angle <= 180):
            raise ValueError(
                f"[QA FAILURE] Mechanical execution range boundary error. "
                f"Angles must be in [0, 180] degrees. Received: L={left_angle}, R={right_angle}"
            )
            
        if not self.connection or not self.connection.is_open:
            print("[WARN] Transmission dropped: Serial hardware port is not open.")
            return

        # Build the exact data payload block
        payload = f"{cmd_type},{left_angle},{right_angle}"
        
        # Calculate the bitwise verification checksum field
        checksum_hex = self.calculate_xor_checksum(payload)
        
        # Seal the packet using our strict frame start/stop indicators
        final_packet = f"@{payload}*{checksum_hex}\n"
        encoded_packet = final_packet.encode('ascii')
        
        try:
            # Cast the string down to raw data-stream bytes over the physical wire
            bytes_written = self.connection.write(encoded_packet)
            self.connection.flush()  # Flush buffer to force immediate electrical release
            
            # --- QA GUARD 3: Hardware Pipeline Write Truncation Check ---
            if bytes_written != len(encoded_packet):
                raise IOError(
                    f"[QA FAILURE] Serial pipeline data truncation event detected! "
                    f"Wrote {bytes_written}/{len(encoded_packet)} bytes."
                )
                
            print(f"[TX SEND] Outbound packet transmitted cleanly: {final_packet.strip()}")
            
        except serial.SerialException as e:
            raise IOError(f"[HARDWARE ERROR] Bus communication loss during active transmission writing: {e}")

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
    TARGET_PORT = "/dev/cu.usbmodem14101" 
    
    host = ConductorHost(port=TARGET_PORT, baudrate=115200)
    host.connect()
    
    try:
        print("\n--- Initiating Conductor Sequence Sprints ---")
        
        # Scenario 1: Nominal valid command executions
        host.send_command("DRV", 90, 45)
        time.sleep(1.5)
        
        host.send_command("DRV", 120, 120)
        time.sleep(1.5)
        
        # Scenario 2: Demonstrating QA Guard Interceptions (Uncomment to view terminal trace error breaks)
        # print("\n--- Testing Out-of-Bounds Error Interception ---")
        # host.send_command("DRV", -10, 45)  # Expected Result: Instantly raises ValueError
        
        # print("\n--- Testing Invalid Mnemonic Token Catch ---")
        # host.send_command("CMD", 90, 90)   # Expected Result: Instantly raises ValueError
        
        # Return to safe baseline boundary state parameters
        host.send_command("DRV", 0, 0)
        time.sleep(1.0)
        
    except KeyboardInterrupt:
        print("\n[WARN] Sequence manually broken by user interface interrupt.")
    except Exception as error:
        print(f"\n[ALERT] Sequence halted due to caught defensive assertion: {error}")
    finally:
        host.close()