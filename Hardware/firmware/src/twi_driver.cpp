#include "../include/twi_driver.h"

#ifdef __AVR_ATmega328P__
#include <avr/io.h>

void twi_init(void) {
    // Set Bit Rate Register for 100kHz standard mode with 16MHz CPU clock speed
    TWBR = 72;
    // Enforce 0-value prescaler bitweights (TWPS1 = 0, TWPS0 = 0)
    TWSR &= ~((1 << TWPS1) | (1 << TWPS0));
}

bool twi_write_reg(uint8_t device_addr, uint8_t reg_addr, uint8_t value) {
    // 1. Send START Condition Bit Pattern
    TWCR = (1 << TWINT) | (1 << TWSTA) | (1 << TWEN);
    while (!(TWCR & (1 << TWINT))); // Blind blocking hardware flag check

    // 2. Load Combined Device Address and Write Command Mode Bitweight (Shift left by 1)
    TWDR = (device_addr << 1);
    TWCR = (1 << TWINT) | (1 << TWEN); // Fire transmission down copper tracks
    while (!(TWCR & (1 << TWINT)));

    // 3. Load Destination Internal Peripheral Memory Map Register Address
    TWDR = reg_addr;
    TWCR = (1 << TWINT) | (1 << TWEN); // Pump byte across bus
    while (!(TWCR & (1 << TWINT)));

    // 4. Load Raw Data Configuration Configuration Byte Value Payload
    TWDR = value;
    TWCR = (1 << TWINT) | (1 << TWEN); // Push data bits out
    while (!(TWCR & (1 << TWINT)));

    // 5. Assert Physical STOP condition bit sequence to release traces
    TWCR = (1 << TWINT) | (1 << TWSTO) | (1 << TWEN);
    
    return true; // MVP assumes deterministic hardware handshake completion
}

#else
#include <string.h>

// Workstation memory-mapped tracking structures for simulation isolation
uint8_t mock_twi_bus[256];

void twi_init(void) {
    clear_mock_twi_bus();
}

void clear_mock_twi_bus(void) {
    memset(mock_twi_bus, 0, sizeof(mock_twi_bus));
}

bool twi_write_reg(uint8_t device_addr, uint8_t reg_addr, uint8_t value) {
    // Intercept hardware tracking loop and dump straight into virtual index slot
    mock_twi_bus[reg_addr] = value;
    return true;
}
#endif