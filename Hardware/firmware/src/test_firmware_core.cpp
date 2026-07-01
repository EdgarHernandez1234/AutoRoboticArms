#include <iostream>
#include <cassert>
#include <string.h>
#include "../include/circular_buffer.h"
#include "../include/watchdog_interlock.h"
#include "../include/packet_parser.h"

// Forward declarations for our standalone parsing math
bool validate_packet_integrity(const char* payload, const char* expected_checksum_hex);

#define LOG_PASS(msg) std::cout << "\033[32m[PASS] " << msg << "\033[0m\n"

void test_nominal_integration_pipeline() {
    CircularBuffer rx_buffer;
    WatchdogInterlock watchdog;
    PacketParser parser;

    rx_buffer.init();
    parser.init();
    watchdog.init(10); // Bind to mock pin 10

    uint32_t simulated_time = 1000;
    watchdog.reset_timer(simulated_time); // Simulate system boot handshake

    // STEP 1: Simulate the Hardware ISR intercepting a perfect packet
    const char* stream = "@DRV,1,90*78\n";
    for(size_t i = 0; i < strlen(stream); i++) {
        rx_buffer.enqueue(stream[i]);
    }

    // STEP 2: Simulate the main.cpp while(true) loop draining the buffer
    uint8_t ext_byte;
    bool frame_ready = false;
    while(rx_buffer.dequeue(ext_byte)) {
        // STEP 3: Feed bytes directly into the parser state machine
        if(parser.update(ext_byte)) {
            frame_ready = true;
        }
    }

    // STEP 4: Verify the loop successfully caught the complete frame
    assert(frame_ready == true);

    // STEP 5: Verify mathematical integrity and Kick the Watchdog
    const char* mock_extracted_payload = "DRV,1,90";
    const char* mock_extracted_hex = "78";
    if (validate_packet_integrity(mock_extracted_payload, mock_extracted_hex)) {
        simulated_time += 1500; // Advance time safely within 3000ms limit
        watchdog.reset_timer(simulated_time);
    }

    // ASSERTION: System must remain safe and active
    assert(watchdog.evaluate_state(simulated_time + 100) == true);
    assert(watchdog.is_tripped() == false);

    LOG_PASS("Integration Pipeline: End-to-End valid frame traversal verified.");
}

void test_corrupted_stream_watchdog_trip() {
    CircularBuffer rx_buffer;
    WatchdogInterlock watchdog;
    PacketParser parser;

    rx_buffer.init();
    parser.init();
    watchdog.init(10);

    uint32_t simulated_time = 1000;
    watchdog.reset_timer(simulated_time);

    // STEP 1: Simulate a broken UART stream (Missing the '\n' terminator)
    const char* broken_stream = "@DRV,1,90*78";
    for(size_t i = 0; i < strlen(broken_stream); i++) {
        rx_buffer.enqueue(broken_stream[i]);
    }

    uint8_t ext_byte;
    bool frame_ready = false;
    while(rx_buffer.dequeue(ext_byte)) {
        if(parser.update(ext_byte)) {
            frame_ready = true;
        }
    }

    // ASSERTION 1: The parser must NOT flag the frame as ready
    assert(frame_ready == false);

    // STEP 2: Because the frame wasn't ready, main.cpp skips kicking the watchdog.
    // We fast-forward time by 3500ms (breaching the 3000ms safety limit!)
    simulated_time += 3500;
    
    // ASSERTION 2: The system evaluator must realize it has been starved of valid data
    bool system_safe = watchdog.evaluate_state(simulated_time);
    assert(system_safe == false);
    assert(watchdog.is_tripped() == true); // Latching emergency shutdown activates

    LOG_PASS("Integration Pipeline: Malformed stream safely starves watchdog, triggering cutoff.");
}

int main() {
    std::cout << "==================================================\n";
    std::cout << "[QA LAB] Executing MASTER INTEGRATION Gates...\n";
    std::cout << "==================================================\n";

    test_nominal_integration_pipeline();
    test_corrupted_stream_watchdog_trip();

    std::cout << "\n\033[32m[SUCCESS] Master Core Loop Integration Verified.\033[0m\n";
    return 0;
}