#!/usr/bin/env python3
"""
scripts/servo_calibration.py
Standalone interactive bench calibration utility for 3-axis arm actuation.
Enables manual stepping, individual joint verification, and homing over PySerial.
"""

import sys
import time
import serial

DEFAULT_PORT = "/dev/ttyACM0"
BAUD_RATE = 115200


def build_frame(j1: int, j2: int, j3: int) -> bytes:
    """Encodes a compliant Option A serial frame with XOR checksum."""
    j1 = max(0, min(180, int(round(j1))))
    j2 = max(0, min(180, int(round(j2))))
    j3 = max(0, min(180, int(round(j3))))

    payload = f"DRV,{j1},{j2},{j3}"
    checksum = 0
    for char in payload:
        checksum ^= ord(char)

    return f"@{payload}*{checksum:02X}\n".encode("ascii")


def send_command(ser: serial.Serial, j1: int, j2: int, j3: int) -> str:
    """Dispatches frame to Arduino and waits for 1-byte return ACK."""
    frame = build_frame(j1, j2, j3)
    ser.write(frame)
    ser.flush()
    ack = ser.read(1).decode("ascii", errors="ignore")
    return ack if ack else "TIMEOUT"


def run_interactive_calibration(port: str = DEFAULT_PORT):
    print(f"=== AutoRoboticArms Joint Calibration Bench Utility ===")
    print(f"Opening hardware link on {port} @ {BAUD_RATE} baud...")

    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.5)
        time.sleep(2.0)  # Settle DTR line
        ser.reset_input_buffer()
        ser.reset_output_buffer()
    except (serial.SerialException, FileNotFoundError, PermissionError) as e:
        print(f"[FATAL] Unable to open serial port: {e}")
        sys.exit(1)

    angles = [90, 90, 90]
    print("[SYSTEM] Hardware linked. Sending neutral baseline (90, 90, 90)...")
    ack = send_command(ser, *angles)
    print(f"[RX ACK] -> '{ack}'\n")

    menu = """
Select Action:
  1) Test Joint 0 (Base Yaw)
  2) Test Joint 1 (Shoulder Pitch)
  3) Test Joint 2 (Elbow Pitch)
  4) Test All Joints (Direct Angles)
  h) Send Baseline Home (90, 90, 90)
  q) Quit
Choice: """

    try:
        while True:
            choice = input(menu).strip().lower()

            if choice == "q":
                print("[SYSTEM] Exiting calibration tool.")
                break
            elif choice == "h":
                angles = [90, 90, 90]
                ack = send_command(ser, *angles)
                print(f"[HOME] Set: {angles} | ACK: '{ack}'")
            elif choice in ["1", "2", "3"]:
                joint_idx = int(choice) - 1
                joint_name = ["Base Yaw", "Shoulder Pitch", "Elbow Pitch"][joint_idx]
                val_str = input(f"Enter target angle (0 - 180) for {joint_name}: ").strip()
                try:
                    val = int(val_str)
                    if 0 <= val <= 180:
                        angles[joint_idx] = val
                        ack = send_command(ser, *angles)
                        print(f"[TX] Set {joint_name} to {val}° | Current Pose: {angles} | ACK: '{ack}'")
                    else:
                        print("[ERROR] Angle must be within 0 to 180 degrees.")
                except ValueError:
                    print("[ERROR] Invalid integer input.")
            elif choice == "4":
                raw = input("Enter comma-separated angles (e.g. 90,45,120): ").strip()
                try:
                    parts = [int(p.strip()) for p in raw.split(",")]
                    if len(parts) == 3 and all(0 <= p <= 180 for p in parts):
                        angles = parts
                        ack = send_command(ser, *angles)
                        print(f"[TX] Set All: {angles} | ACK: '{ack}'")
                    else:
                        print("[ERROR] Must provide exactly 3 angles between 0 and 180.")
                except ValueError:
                    print("[ERROR] Format error. Use: <j1>,<j2>,<j3>")
            else:
                print("[ERROR] Unknown command.")

    finally:
        ser.close()
        print("[SYSTEM] Port closed cleanly.")


if __name__ == "__main__":
    target_port = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT
    run_interactive_calibration(target_port)