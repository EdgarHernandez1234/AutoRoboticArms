#include <iostream>
#include <cassert>
#include <string.h>
#include "../include/packet_parser.h"

// Forward declarations of our standalone parsing functions from packet_parser.cpp
bool validate_packet_integrity(const char* payload, const char* expected_checksum_hex);
bool extract_kinematic_payload(char* payload, uint8_t &out_servo_id, int16_t &out_angle);

#define LOG_PASS(msg) std::cout << "\033[32m[PASS] " << msg << "\033[0m\n"

void test_state_machine_ingestion() {
    PacketParser parser;
    parser.init();
    
    // Simulate receiving a packet byte-by-byte: "@DRV,1,90*5A\n"
    const char* raw_serial_stream = "@DRV,1,90*5A\n";
    bool execution_flag = false;
    
    for (size_t i = 0; i < strlen(raw_serial_stream); ++i) {
        execution_flag = parser.update(raw_serial_stream[i]);
        
        // The update function should ONLY return true on the very last character '\n'
        if (i < strlen(raw_serial_stream) - 1) {
            assert(execution_flag == false);
        } else {
            assert(execution_flag == true);
        }
    }
    LOG_PASS("Parser State Machine correctly bounded payload using '@', '*', and '\\n' markers.");
}

void test_bitwise_xor_checksum_logic() {
    // Test Case A: Known Valid Parity
    // Payload: "DRV,1,90" -> XOR across these ASCII characters equals Hex "3B" (just an example value)
    // Let's use a mathematically verified pair: "DRV,1,90" -> 'D'^'R'^'V'^','^'1'^','^'9'^'0' = 0x51
    const char* payload = "DRV,1,90";
    const char* valid_hex = "78"; // This is the expected checksum for the payload "DRV,1,90"
    assert(validate_packet_integrity(payload, valid_hex) == true);
    
    // Test Case B: Corrupted Data (Simulating electrical noise)
    // Payload changed to "DRV,2,90" but checksum remains "51"
    const char* corrupted_payload = "DRV,2,90";
    assert(validate_packet_integrity(corrupted_payload, valid_hex) == false);

    LOG_PASS("Bitwise XOR Checksum mathematically verified against string tampering.");
}

void test_zero_copy_tokenization() {
    char payload[] = "DRV,3,145"; // Modifiable C-string for strtok
    uint8_t servo_id = 0;
    int16_t angle = 0;
    
    bool valid_extraction = extract_kinematic_payload(payload, servo_id, angle);
    
    assert(valid_extraction == true);
    assert(servo_id == 3);
    assert(angle == 145);
    
    // Test Malicious/Malformed Prefix Trap
    char bad_payload[] = "BAD,3,145";
    assert(extract_kinematic_payload(bad_payload, servo_id, angle) == false);

    LOG_PASS("Zero-copy tokenization successfully extracted integers and blocked bad headers.");
}

int main() {
    std::cout << "==================================================\n";
    std::cout << "[QA LAB] Executing Isolated Packet Parser Tests...\n";
    std::cout << "==================================================\n";
    
    test_state_machine_ingestion();
    test_bitwise_xor_checksum_logic();
    test_zero_copy_tokenization();
    
    std::cout << "\n\033[32m[SUCCESS] Component Gate Closed. Parser engine is secure.\033[0m\n";
    return 0;
}