#ifndef TWI_DRIVER_H
#define TWI_DRIVER_H

#include <stdint.h>
#include <stdbool.h>

// 1. Explicit State Machine Definition
// Tracks the exact physical phase of the internal hardware peripheral
typedef enum {
    TWI_UNINIT = 0,     // Power-on state, hardware registers untouched
    TWI_IDLE,           // Bus initialized and resting at 100kHz, waiting for START
    TWI_BUS_SECURED,    // START condition asserted, physical copper claimed
    TWI_TRANSMITTING,   // Data actively pumping across the shift registers
    TWI_FAULT_STATE     // Hardware timeout or sequence violation detected
} TWI_State;

// 2. Core Initialization & Recovery
void twi_init(void);
void twi_force_bus_reset(void); // Mitigation 2: Manual TWEN toggle to clear frozen lines

// 3. Unbundled, Stateful Interface Hooks
// Returns 'true' on physical handshake success, 'false' if timeout or sequence error occurs
bool twi_start(void);
bool twi_write(uint8_t data);
void twi_stop(void);

// 4. Diagnostics Exposure
// Allows the high-level Watchdog to poll the driver for silent lockups
TWI_State twi_get_state(void);


#ifndef __AVR_ATmega328P__
// 5. Workstation Simulation Memory Isolation
extern uint8_t mock_twi_bus[256];
extern uint16_t mock_active_address_pointer; // Tracks where twi_write should drop the payload
void clear_mock_twi_bus(void);
#endif

#endif // TWI_DRIVER_H