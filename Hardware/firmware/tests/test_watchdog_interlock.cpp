#include "../include/watchdog_interlock.h"
#include <cassert>
#include <iostream>
#include <stdint.h>

// Terminal Output Macros
#define LOG_PASS(msg) std::cout << "\033[32m[PASS] " << msg << "\033[0m\n"
#define LOG_STAGE(msg) std::cout << "\033[34m[STAGE] " << msg << "\033[0m\n"

// ----------------------------------------------------------------------------
// Concrete Mock Clock Definition for Desktop Harness
// ----------------------------------------------------------------------------
#ifndef ARDUINO
uint32_t g_mock_system_millis = 0;

uint32_t get_simulated_millis(void) {
    return g_mock_system_millis;
}
#endif

static void set_mock_time(uint32_t ms) {
#ifndef ARDUINO
    g_mock_system_millis = ms;
#endif
}

/**
 * @brief TEST 1: Verifies initial state and pre-flight bypass
 * before the first packet lands.
 */
void test_watchdog_initialization_safety(void) {
    LOG_STAGE("Testing initialization safety & startup bypass window...");
    
    set_mock_time(0);
    watchdog_init(3000); // 3000ms safety timeout boundary
    
    // System must start un-tripped
    assert(watchdog_is_tripped() == false);
    
    // Prior to first packet/reset, system must stay safe (boot bypass)
    set_mock_time(100);
    assert(watchdog_check() == true);
    
    set_mock_time(5000);
    assert(watchdog_check() == true); 
    assert(watchdog_is_tripped() == false);

    LOG_PASS("Watchdog initialization and pre-flight bypass gates verified.");
}

/**
 * @brief TEST 2: Verifies nominal packet streams within the 3000ms heartbeat window.
 */
void test_watchdog_nominal_heartbeat_window(void) {
    LOG_STAGE("Testing nominal heartbeat execution inside 3000ms window...");
    
    set_mock_time(0);
    watchdog_init(3000);
    
    // First valid packet hits at t = 1000ms (arms watchdog)
    set_mock_time(1000);
    watchdog_reset();
    assert(watchdog_is_tripped() == false);
    
    // Periodic update inside window (delta = 500ms)
    set_mock_time(1500);
    assert(watchdog_check() == true);
    
    // Reset timer at t = 2000ms
    set_mock_time(2000);
    watchdog_reset();
    assert(watchdog_is_tripped() == false);
    
    // Evaluate right before timeout ceiling (delta = 999ms < 3000ms)
    set_mock_time(2999);
    assert(watchdog_check() == true);
    assert(watchdog_is_tripped() == false);

    LOG_PASS("Nominal heartbeat cycles within 3000ms window verified.");
}

/**
 * @brief TEST 3: Verifies catastrophic timeout (>3000ms), fail-safe latching,
 * and valid recovery.
 */
void test_watchdog_catastrophic_breach_and_recovery(void) {
    LOG_STAGE("Testing timeout breach latching (>3000ms) & recovery...");
    
    set_mock_time(0);
    watchdog_init(3000);
    
    // Last packet at t = 1000ms
    set_mock_time(1000);
    watchdog_reset();
    assert(watchdog_is_tripped() == false);
    
    // t = 3999ms (delta = 2999ms): still safe
    set_mock_time(3999);
    assert(watchdog_check() == true);
    assert(watchdog_is_tripped() == false);
    
    // Breach: 4001 - 1000 = 3001ms (> 3000ms)
    set_mock_time(4001);
    bool safe_state = watchdog_check();
    
    assert(safe_state == false);
    assert(watchdog_is_tripped() == true);
    
    // Continued evaluations while broken stay latched
    set_mock_time(6000);
    assert(watchdog_check() == false);
    assert(watchdog_is_tripped() == true);
    
    // Packet arrives at t = 7000ms: recovery
    set_mock_time(7000);
    watchdog_reset();
    
    assert(watchdog_is_tripped() == false);
    
    set_mock_time(7100);
    assert(watchdog_check() == true);

    LOG_PASS("Emergency timeout breach latching and automatic data-link recovery validated.");
}

int main(void) {
    std::cout << "==================================================\n";
    std::cout << "[QA LAB] Executing Isolated Watchdog Interlock Tests...\n";
    std::cout << "==================================================\n";
    
    test_watchdog_initialization_safety();
    test_watchdog_nominal_heartbeat_window();
    test_watchdog_catastrophic_breach_and_recovery();
    
    std::cout << "==================================================\n";
    std::cout << "\033[32m[SUCCESS] All Isolated Watchdog Tests Passed 100%! ✅\033[0m\n";
    std::cout << "==================================================\n";
    return 0;
}