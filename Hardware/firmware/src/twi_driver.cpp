#include "../include/twi_driver.h"

// Internal engine tracking variable (hidden from external files)
static TWI_State current_state = TWI_UNINIT;

// Diagnostics hook
TWI_State twi_get_state(void) {
    return current_state;
}

#ifdef __AVR_ATmega328P__
#include <avr/io.h>

// Mitigation 1: Absolute deterministic timeout ceiling
const uint16_t I2C_TIMEOUT_LIMIT = 20000; 

void twi_init(void) {
    TWBR = 72; // Set Bit Rate to 100kHz
    
    // Mitigation 3: Isolated Bitwise Masking (preserves neighboring configurations)
    TWSR &= ~((1 << TWPS1) | (1 << TWPS0)); 
    
    current_state = TWI_IDLE;
}

void twi_force_bus_reset(void) {
    TWCR = 0; // Disable TWI logic gates entirely
    TWCR = (1 << TWEN); // Re-enable peripheral
    current_state = TWI_IDLE; // Snap internal state back to baseline
}

bool twi_start(void) {
    // Mitigation 4: Sequence violation guard
    if (current_state != TWI_IDLE) return false;

    TWCR = (1 << TWINT) | (1 << TWSTA) | (1 << TWEN);
    
    // Mitigation 1: Escapable Timeout Loop
    uint16_t timeout_counter = I2C_TIMEOUT_LIMIT;
    while (!(TWCR & (1 << TWINT)) && --timeout_counter);
    
    if (timeout_counter == 0) {
        current_state = TWI_FAULT_STATE;
        return false;
    }
    
    current_state = TWI_BUS_SECURED;
    return true;
}

bool twi_write(uint8_t data) {
    // Mitigation 4: Sequence violation guard
    if (current_state != TWI_BUS_SECURED && current_state != TWI_TRANSMITTING) return false;

    TWDR = data;
    TWCR = (1 << TWINT) | (1 << TWEN);
    
    uint16_t timeout_counter = I2C_TIMEOUT_LIMIT;
    while (!(TWCR & (1 << TWINT)) && --timeout_counter);
    
    if (timeout_counter == 0) {
        current_state = TWI_FAULT_STATE;
        return false;
    }
    
    current_state = TWI_TRANSMITTING;
    return true;
}

void twi_stop(void) {
    TWCR = (1 << TWINT) | (1 << TWSTO) | (1 << TWEN);
    current_state = TWI_IDLE;
}

#else
#include <string.h>

uint8_t mock_twi_bus[256];
uint16_t mock_active_address_pointer = 0;
static uint8_t mock_write_step = 0; // Tracks sequence of the I2C payload

void clear_mock_twi_bus(void) {
    memset(mock_twi_bus, 0, sizeof(mock_twi_bus));
}

void twi_init(void) {
    clear_mock_twi_bus();
    current_state = TWI_IDLE;
}

void twi_force_bus_reset(void) {
    current_state = TWI_IDLE;
}

bool twi_start(void) {
    if (current_state != TWI_IDLE) return false;
    current_state = TWI_BUS_SECURED;
    mock_write_step = 0; // Reset payload transaction sequence tracker
    return true;
}

bool twi_write(uint8_t data) {
    if (current_state != TWI_BUS_SECURED && current_state != TWI_TRANSMITTING) return false;

    if (mock_write_step == 0) {
        // Step 1: Device Address (Ignore tracking, just increment step)
    } else if (mock_write_step == 1) {
        // Step 2: Target Peripheral Register Address
        mock_active_address_pointer = data;
    } else {
        // Step 3+: Data Payload
        // Mitigation 2: Virtual Out-of-Bounds memory guard
        if (mock_active_address_pointer < 256) {
            mock_twi_bus[mock_active_address_pointer] = data;
            mock_active_address_pointer++; // Simulate PCA9685 auto-increment behavior
        } else {
            current_state = TWI_FAULT_STATE;
            return false;
        }
    }
    
    mock_write_step++;
    current_state = TWI_TRANSMITTING;
    return true;
}

void twi_stop(void) {
    current_state = TWI_IDLE;
}
#endif