#ifndef JOINT_ACTUATOR_H
#define JOINT_ACTUATOR_H

#include <stdint.h>
#include <stdbool.h>

// Handle PROGMEM cross-compilation compatibility between AVR hardware and host laptop
#ifdef __AVR_ATmega328P__
    #include <avr/pgmspace.h>
#else
    #ifndef PROGMEM
        #define PROGMEM
    #endif
    #ifndef pgm_read_word
        #define pgm_read_word(addr) (*(const uint16_t*)(addr))
    #endif
    #ifndef pgm_read_byte
        #define pgm_read_byte(addr) (*(const uint8_t*)(addr))
    #endif
#endif

// ============================================================================
// 📡 PCA9685 I2C Hardware Register & Protocol Definitions
// ============================================================================
#define PCA9685_I2C_ADDR      0x40  // Default 7-bit I2C Slave Address

#define PCA9685_REG_MODE1     0x00  // Mode Register 1 (Sleep, Auto-Increment)
#define PCA9685_REG_PRESCALE  0xFE  // Prescaler for PWM output frequency

#define PCA9685_REG_LED0_ON_L 0x06  // Channel 0 ON Count Low Byte
#define PCA9685_REG_LED0_ON_H 0x07  // Channel 0 ON Count High Byte
#define PCA9685_REG_LED0_OFF_L 0x08 // Channel 0 OFF Count Low Byte
#define PCA9685_REG_LED0_OFF_H 0x09 // Channel 0 OFF Count High Byte

// 50 Hz Carrier Frequency Prescaler Value for 25 MHz Internal Oscillator
// Prescaler = round(25MHz / (4096 * 50Hz)) - 1 = 121 (0x79)
#define PCA9685_PRESCALE_50HZ 0x79  

#define MAX_ROBOTIC_JOINTS    3     // Single 3-DoF Robotic Arm (Base, Shoulder, Elbow)

// ============================================================================
// 🧱 Option C: Interactive Calibration Structure Layout
// ============================================================================
typedef struct {
    uint8_t  channel;     // PCA9685 PWM Output Channel (0-15)
    uint16_t min_ticks;   // 12-Bit Tick count corresponding to 0 Degrees
    uint16_t max_ticks;   // 12-Bit Tick count corresponding to 180 Degrees
} JointConfig;

// ============================================================================
// 🔌 Public API Function Declarations
// ============================================================================

/**
 * @brief Initializes the PCA9685 PWM Controller over I2C.
 * Configures 50 Hz PWM frequency, enables Auto-Increment, and wakes the chip.
 * @return true if I2C setup succeeded, false on bus error.
 */
bool joint_actuator_init(void);

/**
 * @brief Clamps degree input (0..180) and calculates 12-bit PWM tick count.
 * @param joint_id Joint index (0 = Base, 1 = Shoulder, 2 = Elbow).
 * @param angle_degrees Angular command input.
 * @return 12-bit register tick duration (e.g. 102..512).
 */
uint16_t joint_actuator_degree_to_ticks(uint8_t joint_id, int16_t angle_degrees);

/**
 * @brief Sets a single joint to a specific target angle in degrees.
 * @param joint_id Joint index (0, 1, or 2).
 * @param angle_degrees Target angle (0..180).
 * @return true if register write succeeded, false if re-arm was triggered.
 */
bool joint_actuator_set_angle(uint8_t joint_id, int16_t angle_degrees);

/**
 * @brief Updates all 3 joint channels simultaneously from an array of angles.
 * @param angles Array containing joint angles.
 * @param count Number of joints in array (must match MAX_ROBOTIC_JOINTS).
 * @return true if all writes succeeded.
 */
bool joint_actuator_write_all(const uint8_t* angles, uint8_t count);

/**
 * @brief Re-applies the cached joint positions from SRAM back to registers.
 * Used during brownout recovery to restore physical holding torque.
 * @return true if all writes succeeded.
 */
bool joint_actuator_write_all_cached(void);

/**
 * @brief Executes a 5-step recovery sequence if PCA9685 experiences a brownout reset.
 * @return true if re-initialization and torque restoration succeeded.
 */
bool joint_actuator_rearm(void);

#endif // JOINT_ACTUATOR_H