#define BUFFER_SIZE 32
#define MAX_TIMEOUT_MS 3000 // Watchdog timer window for incoming heartbeat packets

// Physical System Hardware Mapping from your Starter Kit
const int LED_GREEN  = 8;  // High when a nominal valid command executes
const int LED_YELLOW = 9;  // Pulses during memory tokenization and checking
const int LED_RED    = 10; // High when any protocol boundary or timing fault trips

// Communication and Memory Management
char rx_buffer[BUFFER_SIZE];
int buffer_index = 0;
bool packet_is_ready = false;

// System State Watchdog Variables
unsigned long last_packet_time = 0;
bool system_is_halted = false;

void setup() {
    Serial.begin(115200);
    
    pinMode(LED_GREEN, OUTPUT);
    pinMode(LED_YELLOW, OUTPUT);
    pinMode(LED_RED, OUTPUT);
    
    // Boot confirmation signal
    digitalWrite(LED_GREEN, HIGH);
    delay(300);
    digitalWrite(LED_GREEN, LOW);
    
    last_packet_time = millis(); // Initialize system timing loop
}

void loop() {
    // --- QA UPGRADE 1: Communications Timing Watchdog (Prognostics Layer) ---
    // If the Python node freezes or the wire disconnects longer than MAX_TIMEOUT_MS, 
    // the microcontroller must execute a deterministic, safe system halt state.
    if (!system_is_halted && (millis() - last_packet_time > MAX_TIMEOUT_MS)) {
        execute_emergency_shutdown("COMMUNICATION_TIMEOUT_HALT");
    }

    // Process incoming stream data characters
    while (Serial.available() > 0 && !packet_is_ready && !system_is_halted) {
        char incoming_byte = (char)Serial.read();
        
        if (incoming_byte == '@') {
            buffer_index = 0; 
            packet_is_ready = false;
            continue;
        }
        
        if (incoming_byte == '\n') {
            rx_buffer[buffer_index] = '\0'; 
            packet_is_ready = true;
            break;
        }
        
        // --- QA UPGRADE 2: Buffer Overrun Memory Shielding ---
        // Ensure index tracking parameters do not step past memory allocations.
        // If an asset frame attempts to overwrite index 31, trigger a memory boundary fault.
        if (buffer_index < (BUFFER_SIZE - 1)) {
            rx_buffer[buffer_index] = incoming_byte;
            buffer_index++;
        } else {
            buffer_index = 0;
            execute_emergency_shutdown("BUFFER_OVERRUN_FAULT");
            return;
        }
    }

    if (packet_is_ready && !system_is_halted) {
        digitalWrite(LED_YELLOW, HIGH); 
        process_received_frame();
        packet_is_ready = false;        
        digitalWrite(LED_YELLOW, LOW);
    }
}

void process_received_frame() {
    char* asterisk_ptr = strchr(rx_buffer, '*');
    if (asterisk_ptr == NULL) {
        digitalWrite(LED_RED, HIGH);
        return;
    }
    
    *asterisk_ptr = '\0'; 
    char* received_checksum_str = asterisk_ptr + 1;
    
    uint8_t calculated_checksum = 0;
    char* check_ptr = rx_buffer;
    while (*check_ptr != '\0') {
        calculated_checksum ^= (uint8_t)(*check_ptr);
        check_ptr++;
    }
    
    uint8_t received_checksum = (uint8_t)strtol(received_checksum_str, NULL, 16);
    if (calculated_checksum != received_checksum) {
        digitalWrite(LED_RED, HIGH);
        return; // Reject packet if corrupted over transmission
    }
    
    char* command_token = strtok(rx_buffer, ",");
    if (command_token != NULL && strcmp(command_token, "DRV") == 0) {
        char* left_arm_str = strtok(NULL, ",");
        char* right_arm_str = strtok(NULL, ",");
        
        if (left_arm_str != NULL && right_arm_str != NULL) {
            int left_angle  = atoi(left_arm_str);
            int right_angle = atoi(right_arm_str);
            
            // --- QA UPGRADE 3: Zero-Copy Numerical Constraint Clamping ---
            // Even if the payload contains valid data, ensure parameters do not break 
            // the mechanical physical limits [0, 180] of servo motor units.
            if (left_angle < 0 || left_angle > 180 || right_angle < 0 || right_angle > 180) {
                execute_emergency_shutdown("MECHANICAL_EXCURSION_LIMIT_BREACH");
                return;
            }
            
            // If all checks pass, refresh packet arrival timeline metrics
            last_packet_time = millis();
            
            digitalWrite(LED_GREEN, HIGH);
            digitalWrite(LED_RED, LOW);
            
            Serial.print("[MCU ACK] Safe State Locked. L: ");
            Serial.print(left_angle);
            Serial.print(" | R: ");
            Serial.println(right_angle);
        }
    }
}

void execute_emergency_shutdown(const char* fault_reason) {
    system_is_halted = true;
    
    // Physical state execution interlocks: instantly drop outputs down to protective ground targets
    digitalWrite(LED_GREEN, LOW);
    digitalWrite(LED_YELLOW, LOW);
    digitalWrite(LED_RED, HIGH); // Lock warning light indicator high
    
    // Emit diagnostic alert string vectors back up the communication line channel
    Serial.print("[CRITICAL SAFETY INTERLOCK HALT] Reason Code: ");
    Serial.println(fault_reason);
}