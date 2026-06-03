#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// =====================================================================
// SUBSYSTEM HARDWARE CONFIGURATION
// =====================================================================
// Initialize PCA9685 interface instance via the standard I2C default address (0x40)
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);

#define SERVO_FREQ 50  // Analog SG90 servos require a standard 50Hz update loop

// Map physical hardware microsecond pulse limits for standard SG90 micro-servos
// This acts as our low-level structural safety fence against mechanical binding
#define SERVOMIN  150  // Minimum pulse length count out of 4096 (approx 0 degrees)
#define SERVOMAX  600  // Maximum pulse length count out of 4096 (approx 180 degrees)

// Total number of physical articulated joint channels tracked on our driver array
#define TOTAL_SERVOS 4 

// =====================================================================
// HARDWARE SAFETY INTERLOCK CONSTANTS
// =====================================================================
const int PIN_LED_GREEN = 2; // High-Parity Packet Validation Indicator Pin
const int PIN_LED_RED   = 3; // Fault Verification / Timeout Indicator Pin

unsigned long last_valid_transmission_time = 0;
const unsigned long TIMEOUT_THRESHOLD_MS = 3000; // Asynchronous safety threshold

// =====================================================================
// BOUNDED MEMORY BUFFER LAYOUT
// =====================================================================
const size_t BUFFER_CAPACITY = 32;
char serial_input_buffer[BUFFER_CAPACITY];
size_t write_position_index = 0;

// =====================================================================
// SYSTEM INITIALIZATION CORE
// =====================================================================
void setup() {
  Serial.begin(115200);
  
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  
  digitalWrite(PIN_LED_GREEN, LOW);
  digitalWrite(PIN_LED_RED, HIGH); // Assert initialization / alert state

  // Initialize the I2C Bus control registers
  pwm.begin();
  pwm.setOscillatorFrequency(27000000); // Set calibration frequency to 27MHz
  pwm.setPWMFreq(SERVO_FREQ);

  last_valid_transmission_time = millis();
  
  digitalWrite(PIN_LED_RED, LOW); // System is live, clean, and listening
  Serial.println(F("[INITIALIZED] Armored Kinematics Controller Operational."));
}

// =====================================================================
// MAIN EXECUTION CONTEXT
// =====================================================================
void loop() {
  // Check our prognostic watchdog boundary condition
  assert_watchdog_boundary();

  // Ingest incoming byte registers asynchronously
  while (Serial.available() > 0) {
    char captured_byte = (char)Serial.read();
    process_raw_byte(captured_byte);
  }
}

// =====================================================================
// ASYNCHRONOUS INGESTION ENGINE
// =====================================================================
void process_raw_byte(char byte_stream_input) {
  if (byte_stream_input == '\n') {
    if (write_position_index > 0) {
      serial_input_buffer[write_position_index] = '\0';
      evaluate_and_execute_frame();
      write_position_index = 0; // Flash memory pointer reset
    }
  } 
  else if (byte_stream_input != '\r') {
    if (write_position_index < (BUFFER_CAPACITY - 1)) {
      serial_input_buffer[write_position_index++] = byte_stream_input;
    } else {
      // Memory boundary breached: flush the context safely to prevent corruption
      write_position_index = 0;
      trigger_hardware_fault_alert();
      Serial.println(F("[ERROR] Serial buffer capacity overflow. Frame aborted."));
    }
  }
}

// =====================================================================
// DATA ENVELOPE STRUCTURAL VALIDATION & PARSING
// =====================================================================
void evaluate_and_execute_frame() {
  if (serial_input_buffer[0] != '@') return; // Strict header alignment gate

  // Extract the bitwise checksum separator token
  char* parity_delimiter_ptr = strchr(serial_input_buffer, '*');
  if (parity_delimiter_ptr == NULL) {
    trigger_hardware_fault_alert();
    return;
  }

  *parity_delimiter_ptr = '\0'; // In-place string mutation split
  char* extracted_checksum_str = parity_delimiter_ptr + 1;

  // Calculate local mathematical verification value
  uint8_t computed_xor_checksum = 0;
  for (size_t idx = 1; serial_input_buffer[idx] != '\0'; idx++) {
    computed_xor_checksum ^= (uint8_t)serial_input_buffer[idx];
  }

  // Parse host checksum string back into matching integral data spaces
  uint8_t received_xor_checksum = (uint8_t)strtol(extracted_checksum_str, NULL, 16);

  if (computed_xor_checksum != received_xor_checksum) {
    trigger_hardware_fault_alert();
    Serial.print(F("[CRC FAULT] Expected: "));
    Serial.println(computed_xor_checksum, HEX);
    return;
  }

  // Check passed! Reset anomalies markers and flash validation status
  last_valid_transmission_time = millis();
  digitalWrite(PIN_LED_RED, LOW);
  digitalWrite(PIN_LED_GREEN, HIGH);

  // Tokenize arguments cleanly using zero-copy standard library pointers
  char* command_header = strtok(serial_input_buffer + 1, ",");
  
  if (strcmp(command_header, "DRV") == 0) {
    char* servo_id_str = strtok(NULL, ",");
    char* angle_str = strtok(NULL, ",");

    if (servo_id_str != NULL && angle_str != NULL) {
      int target_servo_id = atoi(servo_id_str);
      int target_angle = atoi(angle_str);

      // Enforce operational least-privilege boundary fences
      if (target_servo_id >= 0 && target_servo_id < TOTAL_SERVOS && target_angle >= 0 && target_angle <= 180) {
        execute_servo_actuation(target_servo_id, target_angle);
      } else {
        Serial.println(F("[REJECTED] Out-of-bounds joint parameter payload fields."));
      }
    }
  }
}

// =====================================================================
// LOW-LEVEL KINEMATIC TIMING TRANSFORMATION
// =====================================================================
void execute_servo_actuation(int servo_channel, int angle_degrees) {
  // Translate human-readable angle arrays (0-180) to 12-bit pulse intervals
  // Formula: map(value, fromLow, fromHigh, toLow, toHigh)
  long pulse_ticks = map(angle_degrees, 0, 180, SERVOMIN, SERVOMAX);
  
  // Directly command the discrete PCA9685 register bits over the I2C bus wire
  pwm.setPWM(servo_channel, 0, pulse_ticks);

  Serial.print(F("[KINEMATICS] Joint Channel "));
  Serial.print(servo_channel);
  Serial.print(F(" moved cleanly to "));
  Serial.print(angle_degrees);
  Serial.print(F(" deg (Pulse Ticks: "));
  Serial.print(pulse_ticks);
  Serial.println(F(")"));
}

// =====================================================================
// SAFETY SYSTEMS & REAL-TIME INTERLOCK PROGNOSES
// =====================================================================
void assert_watchdog_boundary() {
  if (millis() - last_valid_transmission_time > TIMEOUT_THRESHOLD_MS) {
    // Communication link lost! Instantly execute emergency safe ground dump
    for (int ch = 0; ch < TOTAL_SERVOS; ch++) {
      pwm.setPWM(ch, 0, 0); // Setting pulse count to 0 completely kills power to the servo motor coils
    }
    digitalWrite(PIN_LED_GREEN, LOW);
    digitalWrite(PIN_LED_RED, HIGH); // Assert system lock lockouts state
  }
}

void trigger_hardware_fault_alert() {
  digitalWrite(PIN_LED_GREEN, LOW);
  digitalWrite(PIN_LED_RED, HIGH);
}