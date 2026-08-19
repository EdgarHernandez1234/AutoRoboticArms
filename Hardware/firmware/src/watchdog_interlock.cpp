#include "../include/watchdog_interlock.h"

// Platform-Specific Millis Hook
#ifdef __AVR_ATmega328P__
    extern "C" uint32_t millis(void);
#else
    extern uint32_t get_simulated_millis(void);
    #define millis() get_simulated_millis()
#endif

// Static Internal State (Encapsulated in C-API file scope)
static uint32_t g_watchdog_timeout_ms = 3000;
static uint32_t g_last_heartbeat_ms   = 0;
static bool     g_is_tripped          = false;
static bool     g_has_bootstrapped    = false;

void watchdog_init(uint32_t timeout_ms) {
    g_watchdog_timeout_ms = timeout_ms;
    g_last_heartbeat_ms   = 0;
    g_is_tripped          = false;
    g_has_bootstrapped    = false;
}

bool watchdog_check(void) {
    // Before the first valid frame arrives, stay dormant to allow host bootup
    if (!g_has_bootstrapped) {
        return true;
    }

    uint32_t current_ms = millis();
    uint32_t delta_ms   = current_ms - g_last_heartbeat_ms;

    if (delta_ms > g_watchdog_timeout_ms) {
        g_is_tripped = true;
        return false; // Trip the safety interlock
    }

    return true; // Healthy and within bounds
}

void watchdog_reset(void) {
    g_last_heartbeat_ms = millis();
    g_has_bootstrapped  = true;
    g_is_tripped        = false;
}

bool watchdog_is_tripped(void) {
    return g_is_tripped;
}