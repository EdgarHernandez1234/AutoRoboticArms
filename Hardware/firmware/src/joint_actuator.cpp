#include <avr/pgmspace.h>
#include "ring_buffer.h"

// 1. Structural blueprint tracking separate physical constraints per joint segment
struct JointCalibration {
    const uint16_t minTicks; // 12-bit value matching 0 degrees pulse orientation
    const uint16_t maxTicks; // 12-bit value matching 180 degrees pulse orientation
};

// 2. 🚀 THE FLASH-PINNED INTERACTIVE CALIBRATION MATRIX
// PROGMEM bakes this structural data configuration straight inside the 32KB Flash pool
// 0 bytes of precious SRAM volatile data stack are consumed!
const JointCalibration calibrationMatrix[] PROGMEM = {
    {130, 490}, // Index 0: Base Joint   (Calibrated wide for a high-flex micro MG90S)
    {205, 410}, // Index 1: Shoulder Yoke (Calibrated narrow for a standard full-size MG996R)
    {180, 440}  // Index 2: Elbow Link    (Calibrated individually based on desk loading)
};

// Direct register address mapping offsets for PCA9685 peripheral channels
#define PCA9685_ADDRESS   0x40  // Default factory un-jumpered I2C address profile
#define PCA9685_MODE1     0x00  // Control register 1
#define PCA9685_PRESCALE  0xFE  // Clock scaling register
#define LED0_OFF_L        0x08  // Base start pointer address for channel 0 register configurations

bool pca9685_write_register(uint8_t reg_addr, uint8_t data_val) {
    if (!twi_assert_start_condition()) return false;
    
    // 0x18 = Slave Address + Write Bit (0x40 << 1 = 0x80) successfully acknowledged
    if (!twi_transmit_byte_payload((PCA9685_ADDRESS << 1), 0x18)) return false;
    
    // 0x28 = Data byte successfully acknowledged by slave
    if (!twi_transmit_byte_payload(reg_addr, 0x28)) return false;
    if (!twi_transmit_byte_payload(data_val, 0x28)) return false;
    
    twi_assert_stop_condition();
    return true;
}

void update_joint_actuator_register(uint8_t jointIndex, uint8_t rawAngle) {
    // Guard parameter bounds checking natively at the edge
    if (rawAngle > 180) rawAngle = 180;
    
    // Extract constants directly from program space flash lines
    uint16_t minPulse = pgm_read_word(&(calibrationMatrix[jointIndex].minTicks));
    uint16_t maxPulse = pgm_read_word(&(calibrationMatrix[jointIndex].maxTicks));
    
    // 🧠 LINEAR ARITHMETIC INTERPOLATION MATRIX STEP
    // Bypasses resource-heavy double/float emulation variables entirely.
    // Scales the operation over safe uint32_t registers before executing integer division.
    uint16_t targetTicks = minPulse + (((uint32_t)(rawAngle) * (maxPulse - minPulse)) / 180);
    
    // Calculate memory offset mapping slots for the PCA9685 register indices
    // Each distinct channel takes exactly 4 sequential register blocks
    uint8_t baseRegisterOffset = LED0_OFF_L + (jointIndex * 4);
    
    // Drop lower and upper split-bytes packages down the data link tracks
    pca9685_write_register(baseRegisterOffset,     (uint8_t)(targetTicks & 0xFF));        // Low 8 Bits
    pca9685_write_register(baseRegisterOffset + 1, (uint8_t)((targetTicks >> 8) & 0x0F)); // High 4 Bits
}