#include "../include/twi_driver.h"

#ifdef __AVR_ATmega328P__
#include <avr/io.h>
#include <util/twi.h>

// Mitigation 1: Absolute deterministic timeout ceiling
const uint16_t I2C_TIMEOUT_LIMIT = 20000; 

void twi_init(uint32_t bus_speed_hz) {
    (void)bus_speed_hz;
    TWSR = 0x00; // Prescaler = 1
    TWBR = 72;   // 100 kHz SCL clock frequency at 16 MHz CPU clock
    TWCR = (1 << TWEN); // Enable Two-Wire Interface hardware
}

bool twi_start(void) {
    TWCR = (1 << TWINT) | (1 << TWSTA) | (1 << TWEN);
    uint32_t timeout = 0;
    while (!(TWCR & (1 << TWINT))) { // New location of twi force buss reset
        // Mitigation 1: Absolute deterministic timeout ceiling
        if (++timeout >= I2C_TIMEOUT_LIMIT) {
            twi_force_bus_reset();
            return false;
        }
    }
    uint8_t status = TW_STATUS;
    return (status == TWI_START_SENT || status == TWI_REP_START_SENT);
}

bool twi_write_address(uint8_t data, bool is_read) {
    TWDR = (data << 1) | (is_read ? 1 : 0);
    TWCR = (1 << TWINT) | (1 << TWEN);
    uint32_t timeout = 0;
    while (!(TWCR & (1 << TWINT))) {
        if (++timeout >= I2C_TIMEOUT_LIMIT) {
            twi_force_bus_reset();
            return false;
        }
    }
    uint8_t expected_status = is_read ? TWI_MR_SLA_ACK : TWI_MT_SLA_ACK;
    return (TW_STATUS == expected_status);
}

bool twi_write_byte(uint8_t data) {
    TWDR = data;
    TWCR = (1 << TWINT) | (1 << TWEN);
    uint32_t timeout = 0;
    while (!(TWCR & (1 << TWINT))) {
        if (++timeout >= I2C_TIMEOUT_LIMIT) {
            twi_force_bus_reset();
            return false;
        }
    }
    return (TW_STATUS == TWI_MT_DATA_ACK);
}

bool twi_read_byte(uint8_t* out_data, bool send_ack) {
if (out_data == NULL) return false;
    
    if (send_ack) {
        TWCR = (1 << TWINT) | (1 << TWEN) | (1 << TWEA);
    } else {
        TWCR = (1 << TWINT) | (1 << TWEN);
    }

    uint32_t timeout = 0;
    while (!(TWCR & (1 << TWINT))) {
        if (++timeout >= I2C_TIMEOUT_LIMIT) {
            twi_force_bus_reset();
            return false;
        }
    }

    *out_data = TWDR;
    return true;
}

void twi_stop(void) {
    TWCR = (1 << TWINT) | (1 << TWEN) | (1 << TWSTO);
}

void twi_force_bus_reset(void) {
    TWCR = 0; // Disable TWI peripheral to release SDA and SCL lines
    TWCR = (1 << TWEN); // Re-enable peripheral
}

bool twi_write_register(uint8_t second_addr, uint8_t reg_addr, uint8_t data) {
    if (!twi_start()) return false;
    if (!twi_write_address(second_addr, false)) { twi_stop(); return false; }
    if (!twi_write_byte(reg_addr)) { twi_stop(); return false; }
    if (!twi_write_byte(data)) { twi_stop(); return false; }
    twi_stop();
    return true;
}

bool twi_read_register(uint8_t second_addr, uint8_t reg_addr, uint8_t* out_data) {
    if (out_data == NULL) return false;
    if (!twi_start()) return false;
    if (!twi_write_address(second_addr, false)) { twi_stop(); return false; }
    if (!twi_write_byte(reg_addr)) { twi_stop(); return false; }
    
    // Repeated START for Read phase
    if (!twi_start()) return false;
    if (!twi_write_address(second_addr, true)) { twi_stop(); return false; }
    if (!twi_read_byte(out_data, false)) { twi_stop(); return false; } // NACK single byte
    twi_stop();
    return true;
}

// ============================================================================
// HOST WORKSTATION SIMULATION TARGET IMPLEMENTATION (Laptop / Mac / CI)
// ============================================================================
#else

#include <string.h>

static uint8_t  mock_bus_memory[256];
static uint32_t mock_write_counter = 0;

void twi_init(uint32_t bus_speed_hz) {
    (void)bus_speed_hz;
    reset_mock_bus();
}

bool twi_start(void) { return true; }
bool twi_write_address(uint8_t second_addr, bool is_read) { (void)second_addr; (void)is_read; return true; }
bool twi_write_byte(uint8_t data) { (void)data; return true; }
bool twi_read_byte(uint8_t* out_data, bool send_ack) { (void)send_ack; if (out_data) *out_data = 0; return true; }
void twi_stop(void) {}
void twi_force_bus_reset(void) {}

bool twi_write_register(uint8_t second_addr, uint8_t reg_addr, uint8_t data) {
    (void)second_addr;
    mock_bus_memory[reg_addr] = data;
    mock_write_counter++;
    return true;
}

bool twi_read_register(uint8_t second_addr, uint8_t reg_addr, uint8_t* out_data) {
    (void)second_addr;
    if (out_data == NULL) return false;
    *out_data = mock_bus_memory[reg_addr];
    return true;
}

uint8_t read_mock_register(uint8_t reg_addr) {
    return mock_bus_memory[reg_addr];
}

void reset_mock_bus(void) {
    memset(mock_bus_memory, 0, sizeof(mock_bus_memory));
    mock_write_counter = 0;
}

uint32_t get_mock_write_count(void) {
    return mock_write_counter;
}

#endif // __AVR_ATmega328P__