import time
import serial

# Target device port configuration discovered via kernel dmesg triage pass
SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 115200

print(f"[START] Initializing loopback diagnostic sweep on port {SERIAL_PORT}...")

try:
    # Attempt absolute hardware channel instantiation
    ser = serial.Serial(port=SERIAL_PORT, baudrate=BAUD_RATE, timeout=2.0)
    
    # Establish mandatory stabilization sleep to allow target board bootloader bypass
    print("[INFO] Connection opened. Synchronizing baseline clocks (2s delay)...")
    time.sleep(2)
    
    # Send a plain text string wrapped in a standard carriage format byte array
    test_message = "PING\n"
    print(f"[TX] Pushing raw string to wire: {test_message.strip()}")
    ser.write(test_message.encode('ascii'))
    ser.flush() # Force electrical data line discharge immediately
    
    # Block and sample the input lines for returning asynchronous target logs
    print("[RX] Listening for target responses/acknowledgments...")
    incoming_line = ser.readline()
    
    if incoming_line:
        decoded_response = incoming_line.decode('ascii', errors='ignore').strip()
        print(f"[SUCCESS] Intercepted returning stream data vectors: {decoded_response}")
    else:
        print("[WARN] Data packet sent cleanly, but the microcontroller returned an empty buffer link response.")
        print("       (This is expected if your Arduino is currently running an empty or default sketch!)")

    # Gracefully terminate tracking metrics
    ser.close()
    print("[END] Diagnostic execution loop finalized successfully.")

except serial.SerialException as error:
    print(f"\n[CRITICAL FAILURE] Operating system could not access the bus hardware: {error}")
    print(" -> Triage Checks: Is the Arduino completely plugged in via USB?")
    print(" -> Triage Checks: Did you remember to apply the host group permissions patch ('sudo usermod -aG dialout $USER')?")