#ifndef TWI_DRIVER_H
#define TWI_DRIVER_H

#include <stdint.h>
#include <stdbool.h>

// ============================================================================
// 📡 Two-Wire Interface (I2C) Hardware Status Codes (ATmega328P Datasheet)
// ============================================================================
#define TWI_START_SENT      0x08  // START condition transmitted
#define TWI_REP_START_SENT  0x10  // Repeated START condition transmitted
#define TWI_MT_SLA_ACK      0x18  // Master Transmit: SLA+W transmitted, ACK received
#define TWI_MT_DATA_ACK     0x28  // Master Transmit: Data transmitted, ACK received
#define TWI_MR_SLA_ACK      0x40  // Master Receive: SLA+R transmitted, ACK received
#define TWI_MR_DATA_NACK    0x58  // Master Receive: Data received, NACK returned
#define I2C_TIMEOUT_LIMIT   20000 // Loop iteration bound to prevent CPU freezes

// ============================================================================
// 🔌 Core Primitive Bus Control Functions
// ============================================================================

/**
 * @brief Initializes the TWI/I2C hardware hardware registers or mock array.
 * @param bus_speed_hz Targeted clock frequency (e.g. 100000 for 100 kHz).
 */
void twi_init(uint32_t bus_speed_hz);

/**
 * @brief Issues an I2C START condition on the bus lines.
 * @return true if START was acknowledged by hardware, false on timeout.
 */
bool twi_start(void);

/**
 * @brief Transmits the 7-bit slave address plus read/write bit.
 * @param data 7-bit peripheral address (e.g. 0x40 for PCA9685).
 * @param is_read true for READ mode (SLA+R), false for WRITE mode (SLA+W).
 * @return true if SLA+W/R was acknowledged by slave device.
 */
bool twi_write_address(uint8_t data, bool is_read);

/**
 * @brief Sends a single byte over active I2C data tracks.
 * @param data Byte payload to transmit.
 * @return true if byte was acknowledged by slave device.
 */
bool twi_write_byte(uint8_t data);

/**
 * @brief Reads a single byte from the active I2C slave.
 * @param out_data Pointer to store received byte.
 * @param send_ack true to return ACK (continue reading), false for NACK (final byte).
 * @return true if read transaction succeeded.
 */
bool twi_read_byte(uint8_t* out_data, bool send_ack);

/**
 * @brief Issues an I2C STOP condition to release control of the bus.
 */
void twi_stop(void);

/**
 * @brief Forces a hard hardware reset of the TWI state machine during lockups.
 */
void twi_force_bus_reset(void);

// ============================================================================
// ⚙️ High-Level Atomic Register Convenience Functions
// ============================================================================

/**
 * @brief Performs a complete atomic register write transaction.
 * Frame: [START] -> [SLA+W] -> [REG_ADDR] -> [DATA] -> [STOP]
 * @param data 7-bit peripheral address.
 * @param reg_addr Target register address (e.g. 0x00 for MODE1).
 * @param data Byte value to write to the register.
 * @return true if entire sequence completed with ACKs, false on bus failure.
 */
bool twi_write_register(uint8_t slave_addr, uint8_t reg_addr, uint8_t data);

/**
 * @brief Reads a single byte from a target peripheral register.
 * Frame: [START] -> [SLA+W] -> [REG_ADDR] -> [REP_START] -> [SLA+R] -> [DATA] -> [STOP]
 * @param data 7-bit peripheral address.
 * @param reg_addr Target register address.
 * @param out_data Pointer to output byte destination.
 * @return true if register read succeeded.
 */
bool twi_read_register(uint8_t slave_addr, uint8_t reg_addr, uint8_t* out_data);//  ============================================================================
// Host Laptop Unit Test Inspection Interface (Non-AVR Target Only)
// ============================================================================
#ifndef __AVR_ATmega328P__

/**
 * @brief Reads a byte directly from the laptop's virtual mock I2C register memory array.
 * @param reg_addr Register array index (0..255).
 * @return Value stored in mock memory.
 */
uint8_t read_mock_register(uint8_t reg_addr);

/**
 * @brief Resets all 256 bytes of mock memory array and write counters to zero.
 */
void reset_mock_bus(void);

/**
 * @brief Gets the total number of byte write operations captured during mock test passes.
 * @return Cumulative write count.
 */
uint32_t get_mock_write_count(void);

#endif // !__AVR_ATmega328P__
#endif // TWI_DRIVER_H