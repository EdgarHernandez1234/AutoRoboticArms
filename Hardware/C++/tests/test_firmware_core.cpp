#include <iostream>
#include <cassert>
#include "ring_buffer.h"

// 1. Emulate bare-metal AVR registers as global host variables
volatile uint8_t UBRR0H = 0; volatile uint8_t UBRR0L = 0;
volatile uint8_t UCSR0A = 0; volatile uint8_t UCSR0B = 0;
volatile uint8_t UCSR0C = 0; volatile uint8_t UDR0 = 0;

unsigned long lastValidPacketTime = 0;
volatile unsigned long timer_millis = 0;

void run_firmware_integrity_test_suite() {
    std::cout << "🧪 Initializing Bare-Metal Firmware In-Memory Harness SIM..." << std::endl;
    
    // ---------------------------------------------------------
    // TEST CASE 1: Validate Nominal Frame Parsing
    // ---------------------------------------------------------
    head = 0; tail = 0; currentSystemState = SYSTEM_NOMINAL;
    
    push_serial_byte(0x55); // SYNC_1
    push_serial_byte(0xAA); // SYNC_2
    push_serial_byte(0x5A); // Base Angle (90)
    push_serial_byte(0x2D); // Shoulder Angle (45)
    push_serial_byte(0x87); // Elbow Angle (135)
    push_serial_byte(0x8F); // Pre-computed matching CRC8 checksum token
    
    process_buffered_frames();
    
    // Assert that the system accepted the frame and remained in NOMINAL state
    assert(currentSystemState == SYSTEM_NOMINAL);
    std::cout << "  ✅ Test Case 1: Nominal Packed Frame Parsing Passed." << std::endl;

    // ---------------------------------------------------------
    // TEST CASE 2: Validate Security Lockdown on CRC8 Corruption
    // ---------------------------------------------------------
    push_serial_byte(0x55); 
    push_serial_byte(0xAA);
    push_serial_byte(0x00); 
    push_serial_byte(0x00); 
    push_serial_byte(0x00);
    push_serial_byte(0xFF); // Intentionally malformed corrupted CRC character
    
    process_buffered_frames();
    
    // Assert that the firmware successfully caught the error and tripped the lockdown
    assert(currentSystemState == SYSTEM_FAULT_CHECKSUM);
    std::cout << "  ✅ Test Case 2: Security Mismatch Ingress Lockdown Passed." << std::endl;

    // ---------------------------------------------------------
    // TEST CASE 3: Validate Secure Handshake Auto-Recovery
    // ---------------------------------------------------------
    push_serial_byte(0xAA); push_serial_byte(0x55);
    push_serial_byte(0xDE); push_serial_byte(0xAD); 
    push_serial_byte(0xBE); push_serial_byte(0xEF); // Secure clearing handshake
    
    verify_isolated_recovery_handshake();
    
    // Assert that the exact 6-byte token successfully restored operations
    assert(currentSystemState == SYSTEM_NOMINAL);
    std::cout << "  ✅ Test Case 3: State-Isolated Handshake Healing Passed." << std::endl;
    
    std::cout << "\n🏆 SYSTEM INTEGRITY SUMMARY: ALL HARNESS TESTS PASSED ACCORDING TO ICD SPEC." << std::endl;
}

int main() {
    // Execute the test harness natively on the x86_64 host
    run_firmware_integrity_test_suite();
    return 0;
}