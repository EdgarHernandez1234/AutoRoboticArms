#ifndef WATCHDOG_INTERLOCK_H
#define WATCHDOG_INTERLOCK_H

#include <stdint.h>

// HARDWARE WATCHDOG SPECIFICATION CONSTANTS
#define WATCHDOG_TIMEOUT_MS 3000

class WatchdogInterlock {
private:
    uint32_t last_heartbeat_timestamp;
    bool system_tripped;
    uint8_t safety_relay_pin;

public:
    // 1. HARDWARE BINDING: Assigns physical interlock control pins
    void init(uint8_t pin) {
        safety_relay_pin = pin;
        system_tripped = false;
        last_heartbeat_timestamp = 0;
    }

    // 2. COUNTER RESET (WDT Kicking): Called when a valid verified message frame lands
    void reset_timer(uint32_t current_time_ms) {
        last_heartbeat_timestamp = current_time_ms;
        
        // Recover cleanly if we were previously locked down and communications re-align
        if (system_tripped) {
            system_tripped = false;
            // Write to physical hardware registers to restore connection tracks here later
        }
    }

    // 3. CONTINUOUS TIMING CHECK: Evaluates time delta drift inside main execution loop
    bool evaluate_state(uint32_t current_time_ms) {
        // Guard against premature checking prior to the first valid message landing
        if (last_heartbeat_timestamp == 0) {
            return true;
        }

        // Calculate exact time elapsed since the last valid host packet injection
        uint32_t time_elapsed = current_time_ms - last_heartbeat_timestamp;

        if (time_elapsed > WATCHDOG_TIMEOUT_MS) {
            if (!system_tripped) {
                trigger_emergency_shutdown();
            }
            return false;
        }
        return true;
    }

    // 4. EMERGENCY SYSTEM ISOLATION: Cuts torque limits immediately
    void trigger_emergency_shutdown() {
        system_tripped = true;
        // CRITICAL ACTION: Physical manipulation of output pins or I2C registers 
        // to immediately cut ground rails or drop servo torque to zero occurs here.
    }

    // 5. OBSERVABILITY INTERFACE: Exposes active health flags to diagnostics channels
    bool is_tripped() const {
        return system_tripped;
    }
};

#endif // WATCHDOG_INTERLOCK_H