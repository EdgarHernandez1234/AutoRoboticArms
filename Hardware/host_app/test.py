import time
import serial
from inverse_kinematics import calculate_joint_angles, WorkspaceEnvelopeViolation

# =====================================================================
# 1. HARDWARE SERIAL FRAME TRANSMITTER
# =====================================================================
def send_frame(ser, base: int, shoulder: int, elbow: int) -> bool:
    """
    Constructs the Option A ASCII frame, calculates the XOR checksum,
    transmits it down USB serial, and blocks for the 1-byte 'K' ACK.
    """
    # 1. Clamp integer angles strictly within physical bounds (0 - 180)
    b = max(0, min(180, int(round(base))))
    s = max(0, min(180, int(round(shoulder))))
    e = max(0, min(180, int(round(elbow))))

    # 2. Build payload body
    payload = f"DRV,{b},{s},{e}"

    # 3. Compute 8-bit XOR checksum
    cs = 0
    for char in payload:
        cs ^= ord(char)

    # 4. Wrap in standard Interface Control Document frame
    frame = f"@{payload}*{cs:02X}\n"
    
    # 5. Transmit frame
    print(f"[TX] {frame.strip()}")
    ser.write(frame.encode("ascii"))

    # 6. Block and await the 1-byte ACK from ATmega328P firmware ('K', 'E', or 'H')
    ack = ser.read(1).decode("ascii", errors="ignore")
    print(f"[RX] {ack if ack else 'TIMEOUT'}")

    return ack == 'K'


# =====================================================================
# 2. MAIN EXECUTION PIPELINE
# =====================================================================
if __name__ == "__main__":
    PORT = "/dev/ttyACM0"
    BAUD = 115200

    print(f"Connecting to Arduino on {PORT} at {BAUD} baud...")
    ser = serial.Serial(PORT, BAUD, timeout=1.0)

    # Mandatory 2.0-second delay for the Arduino DTR bootloader reset to settle
    print("Waiting 2.0s for Arduino DTR reset to complete...")
    time.sleep(2.0)
    ser.reset_input_buffer()

    try:
        # Step 1: Establish baseline homing pose (90, 90, 90)
        print("\n--- Homing Robotic Arm ---")
        send_frame(ser, 90, 90, 90)
        time.sleep(2.0)

        # Step 2: Test Cartesian Target 1 (X=10cm, Y=0cm, Z=10cm)
        print("\n--- Moving to Target 1 (15, 1, 15) cm ---")
        target1 = calculate_joint_angles(15.0, 1.0, 15.0)
        print(f"Computed Angles: {target1}")
        send_frame(ser, target1["base"], target1["shoulder"], target1["elbow"])
        time.sleep(2.0)

        # Step 3: Test Cartesian Target 2 (X=10cm, Y=5cm, Z=8cm)
        print("\n--- Moving to Target 2 (15, 6, 10) cm ---")
        target2 = calculate_joint_angles(15.0, 6.0, 10.0)
        print(f"Computed Angles: {target2}")
        send_frame(ser, target2["base"], target2["shoulder"], target2["elbow"])
        time.sleep(2.0)

        # Step 4: Return to Safe Rest Pose (8cm, 0cm, 12cm)
        print("\n--- Returning to Rest Target (10, 2, 10) cm ---")
        rest_target = calculate_joint_angles(10.0, 2.0, 10.0)
        print(f"Computed Angles: {rest_target}")
        send_frame(ser, rest_target["base"], rest_target["shoulder"], rest_target["elbow"])
        time.sleep(1.0)

    except WorkspaceEnvelopeViolation as exc:
        print(f"[KINEMATIC VIOLATION] Target unreachable: {exc}")
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")
    finally:
        ser.close()
        print("Serial port closed.")
