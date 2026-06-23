#include <avr/io.h>
#include <stdbool.h>
#include "ring_buffer.h" // For error handling and state reporting

#define I2C_TIMEOUT_LIMIT 20000 // Deterministic processor cycle breakout limit
#define TWI_STATUS_MASK   0xF8  // Strips off the lower 3 prescaler bits to isolate status

// ATmega328P Bit-Rate Formula: SCL Frequency = CPU_Clock / (16 + 2*(TWBR) * Prescaler)
// For 100kHz standard mode on a 16MHz crystal with Prescaler = 1:
// 100,000 = 16,000,000 / (16 + 2*TWBR) -> TWBR = 72
void twi_init_hardware_peripheral(void) {
    TWBR = 72; 
    TWSR = 0x00; // Force Prescaler bits to 00 (Prescaler value = 1)
    TWCR = (1 << TWEN); // Natively activate the physical I2C silicon gates
}

bool twi_wait_for_interrupt_flag(void) {
    uint16_t timeout_counter = 0;
    
    // Safety Loop Gating: Poll the TWI Interrupt Flag bit defensively
    while (!(TWCR & (1 << TWINT))) {
        timeout_counter++;
        if (timeout_counter >= I2C_TIMEOUT_LIMIT) {
            twi_force_bus_reset();
            return false; // Hardware stall detected, break loop to prevent complete lockup
        }
    }
    return true;
}

void twi_force_bus_reset(void) {
    TWCR &= ~(1 << TWEN); // Pull the Two-Wire Enable bit low to drop logic gates
    TWSR = 0;
    TWBR = 72;
    TWCR = (1 << TWINT) | (1 << TWSTO) | (1 << TWEN); // Re-assert STOP condition to release tracks
}

bool twi_assert_start_condition(void) {
    // Assert TWINT to clear flag, TWSTA for START condition, and TWEN to keep bus active
    TWCR = (1 << TWINT) | (1 << TWSTA) | (1 << TWEN);
    
    if (!twi_wait_for_interrupt_flag()) return false;
    
    // 0x08 = START condition successfully transmitted on the wire
    if ((TWSR & TWI_STATUS_MASK) != 0x08) return false; 
    return true;
}

void twi_assert_stop_condition(void) {
    // Spill a STOP condition bit sequence down the SCL/SDAtracks. Bypasses interrupt gating.
    TWCR = (1 << TWINT) | (1 << TWSTO) | (1 << TWEN);
}

bool twi_transmit_byte_payload(uint8_t data_byte, uint8_t expected_status_mask) {
    TWDR = data_byte; // Shovel raw bits directly into the I/O data lane buffer
    TWCR = (1 << TWINT) | (1 << TWEN); // Clear flag to initiate bitwise serialization shift
    
    if (!twi_wait_for_interrupt_flag()) return false;
    
    // Mask out the status register to verify that the slave hardware correctly ACKed
    if ((TWSR & TWI_STATUS_MASK) != expected_status_mask) return false;
    return true;
}