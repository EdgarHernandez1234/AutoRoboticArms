#define BUFFER_SIZE 32

// Physical System Hardware Mapping from your Starter Kit
const int LED_GREEN  = 8;  // Latched High when a valid command executes
const int LED_YELLOW = 9;  // Pulses when active parsing is underway
const int LED_RED    = 10; // Latched High when a Checksum or Framing validation fails

// Communication Memory Buffers
char rx_buffer[BUFFER_SIZE];
int buffer_index = 0;
bool packet_is_ready = false;

void setup() {
    // Open the primary hardware UART bus line to match the Python Host rate
    Serial.begin(115200);
    
    // Configure System Diagnostic Telemetry Visualizer Pins
    pinMode(LED_GREEN, OUTPUT);
    pinMode(LED_YELLOW, OUTPUT);
    pinMode(LED_RED, OUTPUT);
    
    // Run initialization visual flash
    digitalWrite(LED_GREEN, HIGH);
    digitalWrite(LED_YELLOW, HIGH);
    digitalWrite(LED_RED, HIGH);
    delay(500);
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_YELLOW, LOW);
    digitalWrite(LED_RED, LOW);
}

void loop() {
    // Non-blocking evaluation of the microcontroller's internal hardware UART registers
    while (Serial.available() > 0 && !packet_is_ready) {
        char incoming_byte = (char)Serial.read();
        
        // Structure Safeguard: Look for the Start Marker flag contract
        if (incoming_byte == '@') {
            buffer_index = 0; // Force-align index pointer to the root memory boundary
            packet_is_ready = false;
            continue;
        }
        
        // Structure Safeguard: Look for the End Marker terminating character
        if (incoming_byte == '\n') {
            rx_buffer[buffer_index] = '\0'; // Seal the buffer vector explicitly into a C-string
            packet_is_ready = true;
            break;
        }
        
        // Safety Barrier: Prevent a malicious or malformed stream from causing a buffer overflow
        if (buffer_index < (BUFFER_SIZE - 1)) {
            rx_buffer[buffer_index] = incoming_byte;
            buffer_index++;
        } else {
            // Buffer saturation fault condition tripped: Flush memory tracks
            buffer_index = 0;
            digitalWrite(LED_RED, HIGH);
        }
    }

    // Delegate processing logic outside the ingestion window once flag status flips
    if (packet_is_ready) {
        digitalWrite(LED_YELLOW, HIGH); // Visually capture data extraction operations
        process_received_frame();
        packet_is_ready = false;        // Release hardware state engine lock
        digitalWrite(LED_YELLOW, LOW);
    }
}

void process_received_frame() {
    // Locate the internal security token delimiter pointer
    char* asterisk_ptr = strchr(rx_buffer, '*');
    if (asterisk_ptr == NULL) {
        // Framing fault condition identified: Drop package frame safely
        digitalWrite(LED_RED, HIGH);
        digitalWrite(LED_GREEN, LOW);
        return;
    }
    
    // Splice the payload block away from the incoming verification token using memory pointer offsets
    *asterisk_ptr = '\0'; // Mutate the '*' into a null-terminator. Payload is now isolated.
    char* received_checksum_str = asterisk_ptr + 1; // Slide forward 1 byte to reveal the Hex sequence
    
    // Recalculate local XOR matrix checksum score to ensure no packet drops over copper
    uint8_t calculated_checksum = 0;
    char* check_ptr = rx_buffer;
    while (*check_ptr != '\0') {
        calculated_checksum ^= (uint8_t)(*check_ptr);
        check_ptr++;
    }
    
    // Parse the host uppercase hexadecimal string back into an integer representation matching our calculation
    uint8_t received_checksum = (uint8_t)strtol(received_checksum_str, NULL, 16);
    
    // Validate system parity flags
    if (calculated_checksum != received_checksum) {
        // Parity fault confirmed: Flag hardware interlock breach and freeze sequence
        digitalWrite(LED_RED, HIGH);
        digitalWrite(LED_GREEN, LOW);
        return;
    }
    
    // Zero copy tokenization processing via Standard Library pointers
    char* command_token = strtok(rx_buffer, ",");
    if (command_token != NULL && strcmp(command_token, "DRV") == 0) {
        // Extract multi-variable coordinate integers seamlessly out of text string representations
        char* left_arm_str = strtok(NULL, ",");
        char* right_arm_str = strtok(NULL, ",");
        
        if (left_arm_str != NULL && right_arm_str != NULL) {
            int left_angle  = atoi(left_arm_str);
            int right_angle = atoi(right_arm_str);
            
            // Core execution milestone validation point reached safely
            digitalWrite(LED_GREEN, HIGH);
            digitalWrite(LED_RED, LOW);
            
            // Print status updates safely back through the pipeline channel to track activity loops
            Serial.print("[MCU ACK] Angles Synchronized. L: ");
            Serial.print(left_angle);
            Serial.print(" | R: ");
            Serial.println(right_angle);
        }
    }
}