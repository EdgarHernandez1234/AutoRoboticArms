// ---------------------------------------------------------
// QA BENCH COGNITIVE IMPORTS
// ---------------------------------------------------------
#include <iostream>
#include <cassert>
#include "../include/circular_buffer.h"
#include "../include/watchdog_interlock.h"

// Simple terminal coloring macro definitions for cross-platform visual validation
#define TEST_PASS(msg) std::cout << "\033[32m[PASS] " << msg << "\033[0m\n"
#define TEST_FAIL(msg) std::cerr << "\033[31m[FAIL] " << msg << "\033[0m\n"

// ---------------------------------------------------------
// AUTOMATED COMPONENT INTEGRITY CHECKS
// ---------------------------------------------------------

void test_circular_buffer_nominal_and_wrap_around() {
    CircularBuffer ring;
    ring.init();
    
    // Assert structural baseline initialization
    assert(ring.get_count() == 0);
    assert(!ring.is_full());
    
    // Fill the buffer to capacity limits sequentially
    for (uint8_t i = 0; i < BUFFER_SIZE; ++i) {
        assert(ring.enqueue(i));
    }
    
    // Assert overflow interlock backpressure kicks in
    assert(ring.is_full());
    assert(ring.enqueue(0xFF) == false); // Enqueue must fail safely
    
    // Dequeue half the data blocks to check rolling tracking variables
    uint8_t extracted_byte = 0;
    for (uint8_t i = 0; i < 32; ++i) {
        assert(ring.dequeue(extracted_byte));
        assert(extracted_byte == i);
    }
    assert(ring.get_count() == 32);
    
    // Re-fill past original index structures to force bitwise wrap-around masks
    for (uint8_t i = 0; i < 16; ++i) {
        assert(ring.enqueue(i + 100));
    }
    
    // Confirm the total internal counter tracks correctly after sliding alignment
    assert(ring.get_count() == 48);
    TEST_PASS("CircularBuffer: Nominal capacity thresholds and bitwise masking wrap verified.");
}

void test_watchdog_interlock_timing_boundaries() {
    WatchdogInterlock watchdog;
    watchdog.init(13); // Bind to virtual physical pin 13 (LED channel tracker)
    
    assert(watchdog.is_tripped() == false);
    
    // Simulate first valid baseline tracking entry landing at t = 1000ms
    watchdog.reset_timer(1000);
    
    // Case A: Next cycle arrives at t = 2500ms (Delta = 1500ms -> Safe under 3000ms ceiling)
    assert(watchdog.evaluate_state(2500) == true);
    assert(watchdog.is_tripped() == false);
    
    // Case B: Data loop drops out, check hits at t = 6000ms (Delta = 3500ms -> Breached!)
    bool execution_status = watchdog.evaluate_state(6000);
    assert(execution_status == false); // System state transition boundary must signal danger
    assert(watchdog.is_tripped() == true); // Latching interlock must activate emergency mode
    
    // Case C: Server recovers and sends clean telemetry frame packet at t = 7000ms
    watchdog.reset_timer(7000);
    assert(watchdog.is_tripped() == false); // Safe structural recovery verification
    
    TEST_PASS("WatchdogInterlock: Non-blocking delta calculations and latching faults verified.");
}

// ---------------------------------------------------------
// MASTER CORE TEST RUNNER EXECUTION ENTRY
// ---------------------------------------------------------
int main() {
    std::cout << "==================================================\n";
    std::cout << "[STAGING] Initializing C++ Component Test Gates...\n";
    std::cout << "==================================================\n";
    
    try {
        test_circular_buffer_nominal_and_wrap_around();
        test_watchdog_interlock_timing_boundaries();
        
        std::cout << "\n\033[32m[ALL PASSED] 100% C++ Inline Core Engines Validated.\033[0m\n";
        return 0; // Return success status back to local laptop operating system terminal
    } catch (...) {
        TEST_FAIL("Catastrophic boundary error encountered inside test suite.");
        return 1; // Signal failure to local build engine pipelines
    }
}