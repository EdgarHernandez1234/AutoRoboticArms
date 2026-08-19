#ifndef WATCHDOG_INTERLOCK_H
#define WATCHDOG_INTERLOCK_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initializes the watchdog interlock with a specified timeout limit.
 * @param timeout_ms Safety window duration (e.g., 3000 ms).
 */
void watchdog_init(uint32_t timeout_ms);

/**
 * @brief Checks if the communication heartbeat has expired.
 * Non-blocking check evaluated on every pass of the main super-loop.
 * @return true if communication is healthy (safe), false if timed out (tripped).
 */
bool watchdog_check(void);

/**
 * @brief Kicks/feeds the watchdog timer upon receiving a valid, verified packet.
 * Resets the internal heartbeat timestamp to the current millisecond.
 */
void watchdog_reset(void);

/**
 * @brief Returns whether the watchdog has latched into a tripped state.
 * @return true if currently tripped.
 */
bool watchdog_is_tripped(void);

#ifdef __cplusplus
}
#endif

#endif // WATCHDOG_INTERLOCK_H