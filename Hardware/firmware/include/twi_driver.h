#ifndef TWI_DRIVER_H
#define TWI_DRIVER_H

#include <stdint.h>
#include <stdbool.h>

// Initialize TWI Peripheral hardware clock or local mock variables
void twi_init(void);

// Monolithic single-register byte write sequence contract
bool twi_write_reg(uint8_t device_addr, uint8_t reg_addr, uint8_t value);

#ifndef __AVR_ATmega328P__
// Workstation testing exposure layout to access virtual memory bounds
extern uint8_t mock_twi_bus[256];
void clear_mock_twi_bus(void);
#endif

#endif // TWI_DRIVER_H