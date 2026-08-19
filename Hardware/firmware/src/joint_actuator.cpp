#include "../include/joint_actuator.h"
#include "../include/twi_driver.h"
#include <string.h>

#ifdef __AVR_ATmega328P__
    #include <util/delay.h>
#else
    #include <chrono>
    #include <thread>
    // Delay fallback for host simulation testing
    #define _delay_us(us) std::this_thread::sleep_for(std::chrono::microseconds(us))
    #define _delay_ms(ms) std::this_thread::sleep_for(std::chrono::milliseconds(ms))
#endif

// ============================================================================
// 📌 Option C: Flash-Pinned Calibration Array (0 Bytes Dynamic SRAM)
// Maps Channels 0, 1, and 2 to specific servo tick bounds (0° -> 180°).
// ============================================================================
const JointConfig JOINT_CALIBRATION_MATRIX[MAX_ROBOTIC_JOINTS] PROGMEM = {
    { 0, 102, 512 }, // Joint 0: Base Yaw (Channel 0, ~1ms to ~2ms pulse)
    { 1, 102, 512 }, // Joint 1: Shoulder Pitch (Channel 1, ~1ms to ~2ms pulse)
    { 2, 102, 512 }  // Joint 2: Elbow Pitch (Channel 2, ~1ms to ~2ms pulse)
};

// Internal SRAM cache for active target angles (used during brownout re-arming)
static int16_t g_cached_angles[MAX_ROBOTIC_JOINTS] = { 90, 90, 90 };

// ============================================================================
// 🧮 Integer-Only Linear Scaling Math
// ============================================================================
uint16_t joint_actuator_degree_to_ticks(uint8_t joint_id, int16_t angle_degrees) {
    if (joint_id >= MAX_ROBOTIC_JOINTS) {
        return 307; // Safe default midpoint tick (~90 degrees) on invalid joint
    }

    // 🛡️ BVA Clamping Protection: Strict 0° <= θ <= 180°
    if (angle_degrees < 0)   angle_degrees = 0;
    if (angle_degrees > 180) angle_degrees = 180;

    // Read calibration parameters directly from Flash Memory (PROGMEM)
    uint16_t min_ticks = pgm_read_word(&(JOINT_CALIBRATION_MATRIX[joint_id].min_ticks));
    uint16_t max_ticks = pgm_read_word(&(JOINT_CALIBRATION_MATRIX[joint_id].max_ticks));

    // Pure 32-Bit Integer Linear Interpolation Equation:
    // N_ticks = min_ticks + (angle * (max_ticks - min_ticks) / 180)
    uint32_t delta_ticks = (uint32_t)(max_ticks - min_ticks);
    uint32_t scaled_ticks = min_ticks + ((uint32_t)angle_degrees * delta_ticks) / 180;

    return (uint16_t)scaled_ticks;
}

// ============================================================================
// 🔌 PCA9685 Hardware Initialization
// ============================================================================
bool joint_actuator_init(void) {
    twi_init(100000); // Ensure I2C bus is initialized at 100 kHz

    // Step 1: Put PCA9685 into SLEEP mode (MODE1 = 0x10) to unlock PRESCALE register
    if (!twi_write_register(PCA9685_I2C_ADDR, PCA9685_REG_MODE1, 0x10)) {
        return false;
    }

    // Step 2: Write 50 Hz Prescaler value (0x79)
    if (!twi_write_register(PCA9685_I2C_ADDR, PCA9685_REG_PRESCALE, PCA9685_PRESCALE_50HZ)) {
        return false;
    }

    // Step 3: Wake up controller and enable Auto-Increment mode (MODE1 = 0x20)
    if (!twi_write_register(PCA9685_I2C_ADDR, PCA9685_REG_MODE1, 0x20)) {
        return false;
    }

    // Step 4: Mandatory 500 us delay for internal oscillator stabilization
    _delay_us(500);

    // Step 5: Initialize all channels to default 90-degree midpoint positions
    return joint_actuator_write_all_cached();
}

// ============================================================================
// ⚙️ Actuator Register Writing Methods
// ============================================================================
bool joint_actuator_set_angle(uint8_t joint_id, int16_t angle_degrees) {
    if (joint_id >= MAX_ROBOTIC_JOINTS) {
        return false;
    }

    // Update internal SRAM cache
    g_cached_angles[joint_id] = angle_degrees;

    // Calculate 12-bit tick target
    uint16_t ticks = joint_actuator_degree_to_ticks(joint_id, angle_degrees);

    // Read assigned channel index from Flash Memory
    uint8_t channel = pgm_read_byte(&(JOINT_CALIBRATION_MATRIX[joint_id].channel));

    // Calculate base PCA9685 register offset for targeted channel
    // Register mapping formula: REG = LED0_ON_L + (channel * 4)
    uint8_t reg_on_l  = PCA9685_REG_LED0_ON_L  + (channel * 4);
    uint8_t reg_off_l = PCA9685_REG_LED0_OFF_L + (channel * 4);
    uint8_t reg_off_h = PCA9685_REG_LED0_OFF_H + (channel * 4);

    // Always start pulse immediately at tick 0
    if (!twi_write_register(PCA9685_I2C_ADDR, reg_on_l, 0x00)) goto write_error;
    if (!twi_write_register(PCA9685_I2C_ADDR, reg_on_l + 1, 0x00)) goto write_error;

    // Split 12-bit tick value across Low Byte and High Byte
    // LEDn_OFF_L = ticks & 0xFF
    // LEDn_OFF_H = (ticks >> 8) & 0x0F
    if (!twi_write_register(PCA9685_I2C_ADDR, reg_off_l, (uint8_t)(ticks & 0xFF))) goto write_error;
    if (!twi_write_register(PCA9685_I2C_ADDR, reg_off_h, (uint8_t)((ticks >> 8) & 0x0F))) goto write_error;

    return true;

write_error:
    // 🛡️ Write failure detected (e.g. missing ACK or bus glitch). Execute Brownout Re-Arm!
    return joint_actuator_rearm();
}

bool joint_actuator_write_all(const uint8_t* angles, uint8_t count) {
    if (angles == NULL || count < MAX_ROBOTIC_JOINTS) {
        return false;
    }

    bool success = true;
    for (uint8_t i = 0; i < MAX_ROBOTIC_JOINTS; i++) {
        if (!joint_actuator_set_angle(i, (int16_t)angles[i])) {
            success = false;
        }
    }
    return success;
}

bool joint_actuator_write_all_cached(void) {
    bool success = true;
    for (uint8_t i = 0; i < MAX_ROBOTIC_JOINTS; i++) {
        uint16_t ticks = joint_actuator_degree_to_ticks(i, g_cached_angles[i]);
        uint8_t channel = pgm_read_byte(&(JOINT_CALIBRATION_MATRIX[i].channel));

        uint8_t reg_on_l  = PCA9685_REG_LED0_ON_L  + (channel * 4);
        uint8_t reg_off_l = PCA9685_REG_LED0_OFF_L + (channel * 4);
        uint8_t reg_off_h = PCA9685_REG_LED0_OFF_H + (channel * 4);

        twi_write_register(PCA9685_I2C_ADDR, reg_on_l, 0x00);
        twi_write_register(PCA9685_I2C_ADDR, reg_on_l + 1, 0x00);
        
        if (!twi_write_register(PCA9685_I2C_ADDR, reg_off_l, (uint8_t)(ticks & 0xFF)) ||
            !twi_write_register(PCA9685_I2C_ADDR, reg_off_h, (uint8_t)((ticks >> 8) & 0x0F))) {
            success = false;
        }
    }
    return success;
}

/**
 * @brief Recovers PCA9685 from a brownout reset or register corruption.
 * @param parser Pointer to active parser/actuator instance.
 * @return true if recovery and re-initialization succeeded, false on I2C failure.
 */

// ============================================================================
// 🚨 Jax's Brownout Recovery Re-Arming Pipeline
// ============================================================================
bool joint_actuator_rearm(void) {
    // Step 1: Force chip into SLEEP mode to enable PRESCALE modification
    if (!twi_write_register(PCA9685_I2C_ADDR, PCA9685_REG_MODE1, 0x10)) return false;

    // Step 2: Re-apply 50 Hz Prescaler (0x79)
    if (!twi_write_register(PCA9685_I2C_ADDR, PCA9685_REG_PRESCALE, PCA9685_PRESCALE_50HZ)) return false;

    // Step 3: Wake up chip and re-enable Auto-Increment (0x20)
    if (!twi_write_register(PCA9685_I2C_ADDR, PCA9685_REG_MODE1, 0x20)) return false;

    // Step 4: Stabilization delay for $25\text{ MHz}$ internal clock
    _delay_us(500);

    // Step 5: Restore cached joint target angles to prevent holding torque collapse
    return joint_actuator_write_all_cached();
}