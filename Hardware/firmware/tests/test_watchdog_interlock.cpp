#include <iostream>
#include <cassert>
#include "../include/watchdog_interlock.h"

// Staging UI Terminal Definitions
#define LOG_PASS(msg) std::cout << "\033[32m[PASS] " << msg << "\033[0m\n"
#define LOG_STAGE(msg) std::cout << "\033[34m[STAGE] " << msg << "\033[0m\n"

void test_watchdog_initialization_safety() {
    WatchdogInterlock watchdog;
    watchdog.init(10); // Bind interlock tracking to virtual pin 10
    
    // ASSERTION 1: System must start un-tripped
    assert(watchdog.is_tripped() == false);
    
    // ASSERTION 2: Prior to the first valid packet landing, evaluate_state must 
    // bypass timeout triggers to allow the Python control plane staging time to boot.
    assert(watchdog.evaluate_state(100) == true);
    assert(watchdog.evaluate_state(5000) == true); 
    assert(watchdog.is_tripped() == false);

    LOG_PASS("Watchdog initialization and pre-flight bypass gates verified.");
}

void test_watchdog_nominal_heartbeat_window() {
    WatchdogInterlock watchdog;
    watchdog.init(10);
    
    // First valid string payload packet hits at t = 1000ms
    watchdog.reset_timer(1000);
    assert(watchdog.is_tripped() == false);
    
    // Main loop ticks forward 1500ms later (t = 2500ms). Delta is 1500ms. Ceil is 3000ms.
    assert(watchdog.evaluate_state(2500) == true);
    assert(watchdog.is_tripped() == false);
    
    // Host pipeline fires a clean command update at t = 2600ms, kicking the timer forward
    watchdog.reset_timer(2600);
    
    // Main loop evaluates at t = 5000ms. Delta is 2400ms. Still within secure margins.
    assert(watchdog.evaluate_state(5000) == true);
    assert(watchdog.is_tripped() == false);

    LOG_PASS("Nominal heartbeat execution tracking within safe time margins validated.");
}

void test_watchdog_catastrophic_breach_and_recovery() {
    WatchdogInterlock watchdog;
    watchdog.init(10);
    
    // Host anchors initial tracking beacon at t = 1000ms
    watchdog.reset_timer(1000);
    
    // System experiences connection drop. Scheduler loops check state at t = 4001ms. 
    // Delta calculation: 4001 - 1000 = 3001ms. Timeout ceiling breached!
    bool safe_state = watchdog.evaluate_state(4001);
    
    // ASSERTION 3: System state evaluator must report a breach condition
    assert(safe_state == false);
    
    // ASSERTION 4: Interlock state machine must latch down in an active safety trip
    assert(watchdog.is_tripped() == true);
    
    // ASSERTION 5: Continued timing evaluations while broken must maintain latch locking parameters
    assert(watchdog.evaluate_state(6000) == false);
    assert(watchdog.is_tripped() == true);
    
    // Connection drops clear. Python host re-stamps a valid data verification pack at t = 7000ms
    watchdog.reset_timer(7000);
    
    // ASSERTION 6: Valid pipeline ingestion must auto-recover and clear the safety interlock latch
    assert(watchdog.is_tripped() == false);
    assert(watchdog.evaluate_state(7100) == true);

    LOG_PASS("Emergency timeout breach latching and automatic data-link recovery validated.");
}

int main() {
    std::cout << "==================================================\n";
    std::cout << "[QA LAB] Executing Isolated Watchdog Interlock Tests...\n";
    std::cout << "==================================================\n";
    
    test_watchdog_initialization_safety();
    test_watchdog_nominal_heartbeat_window();
    test_watchdog_catastrophic_breach_and_recovery();
    
    std::cout << "\n\033[32m[SUCCESS] Component Gate Closed. Watchdog interlock is un-driftable.\033[0m\n";
    return 0;
}