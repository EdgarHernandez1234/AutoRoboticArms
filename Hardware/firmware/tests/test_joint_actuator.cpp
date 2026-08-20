#include <cassert>
#include <cstdio>
#include <cstring>
#include <stdint.h>

#include "../include/joint_actuator.h"
#include "../include/twi_driver.h"

// ============================================================================
// 🛠️ Test Helper: Reconstitute Split 8-Bit Registers into 12-Bit Integer Ticks
// ============================================================================
static uint16_t read_mock_pca9685_ticks(uint8_t channel) {
    // PCA9685 Register Offsets:
    // Channel n LEDn_OFF_L starts at 0x08 + (channel * 4)
    // Channel n LEDn_OFF_H starts at 0x09 + (channel * 4)
    uint8_t off_l_reg = PCA9685_REG_LED0_OFF_L + (channel * 4);
    uint8_t off_h_reg = PCA9685_REG_LED0_OFF_H + (channel * 4);

    uint8_t low_byte  = read_mock_register(off_l_reg);
    uint8_t high_byte = read_mock_register(off_h_reg);

    // Reconstruct 12-bit integer: Low Byte | (High Byte lower nibble << 8)
    return (uint16_t)(low_byte | ((high_byte & 0x0F) << 8));
}

// ============================================================================
// 🧪 Individual Unit Test Suite Declarations
// ============================================================================

void test_pca9685_initialization(void) {
    printf("  [TEST 1]: Verifying PCA9685 Initialization & 50 Hz Register Setup...\n");
    reset_mock_bus();

    bool init_success = joint_actuator_init();
    assert(init_success == true);

    // Verify MODE1 register (0x00) was set to 0x20 (Auto-Increment enabled, Awake)
    assert(read_mock_register(PCA9685_REG_MODE1) == 0x20);

    // Verify PRESCALE register (0xFE) was set to 0x79 (50 Hz Prescaler)
    assert(read_mock_register(PCA9685_REG_PRESCALE) == PCA9685_PRESCALE_50HZ);

    // Verify default initial joint positions (90 degrees -> 307 ticks) across Channels 0, 1, 2
    assert(read_mock_pca9685_ticks(0) == 307);
    assert(read_mock_pca9685_ticks(1) == 307);
    assert(read_mock_pca9685_ticks(2) == 307);

    printf("  [TEST 1]: PASSED! ✅\n");
}

void test_angle_to_tick_transformation_math(void) {
    printf("  [TEST 2]: Verifying Integer Angle-to-Tick Scaling Math...\n");
    reset_mock_bus();
    joint_actuator_init();

    // Test 0 Degrees -> Min pulse tick boundary (102 ticks / 0x0066)
    joint_actuator_set_angle(0, 0);
    assert(read_mock_pca9685_ticks(0) == 102);

    // Test 90 Degrees -> Midpoint tick boundary (307 ticks / 0x0133)
    joint_actuator_set_angle(0, 90);
    assert(read_mock_pca9685_ticks(0) == 307);

    // Test 180 Degrees -> Max pulse tick boundary (512 ticks / 0x0200)
    joint_actuator_set_angle(0, 180);
    assert(read_mock_pca9685_ticks(0) == 512);

    printf("  [TEST 2]: PASSED! ✅\n");
}

void test_multi_axis_channel_isolation(void) {
    printf("  [TEST 3]: Verifying Multi-Axis Channel Address Register Isolation...\n");
    reset_mock_bus();
    joint_actuator_init();

    // Command distinct target angles across all 3 joints simultaneously
    joint_actuator_set_angle(0, 45);   // Joint 0 (Base Yaw)     -> Channel 0 -> 204 ticks
    joint_actuator_set_angle(1, 135);  // Joint 1 (Shoulder)     -> Channel 1 -> 409 ticks
    joint_actuator_set_angle(2, 90);   // Joint 2 (Elbow Pitch)  -> Channel 2 -> 307 ticks

    // Assert that each channel register in mock_bus_memory received its exact value
    assert(read_mock_pca9685_ticks(0) == 204);
    assert(read_mock_pca9685_ticks(1) == 409);
    assert(read_mock_pca9685_ticks(2) == 307);

    printf("  [TEST 3]: PASSED! ✅\n");
}

void test_bva_angle_clamping_protection(void) {
    printf("  [TEST 4]: Verifying Out-of-Bounds BVA Input Clamping Protection...\n");
    reset_mock_bus();
    joint_actuator_init();

    // Under-range angle (-50 degrees) must clamp to 0 degrees (102 ticks)
    joint_actuator_set_angle(0, -50);
    assert(read_mock_pca9685_ticks(0) == 102);

    // Over-range angle (999 degrees) must clamp to 180 degrees (512 ticks)
    joint_actuator_set_angle(0, 999);
    assert(read_mock_pca9685_ticks(0) == 512);

    // Multi-joint write array with mixed invalid bounds
    uint8_t out_of_bounds_angles[3] = { 0, 255, 90 }; // 255 exceeds 180
    joint_actuator_write_all(out_of_bounds_angles, 3);

    assert(read_mock_pca9685_ticks(0) == 102); // 0 deg
    assert(read_mock_pca9685_ticks(1) == 512); // Clamped from 255 to 180 deg
    assert(read_mock_pca9685_ticks(2) == 307); // 90 deg

    printf("  [TEST 4]: PASSED! ✅\n");
}

void test_brownout_rearm_pipeline(void) {
    printf("  [TEST 5]: Verifying Jax's PCA9685 Brownout Recovery Re-Arming Pipeline...\n");
    reset_mock_bus();

    // Set known active joint positions
    uint8_t active_angles[3] = { 45, 90, 135 };
    joint_actuator_write_all(active_angles, 3);

    // Simulate a PCA9685 power brownout: clear mock memory to factory defaults (MODE1 = 0x11)
    reset_mock_bus();
    twi_write_register(PCA9685_I2C_ADDR, PCA9685_REG_MODE1, 0x11);

    // Trigger brownout recovery re-arm
    bool rearm_success = joint_actuator_rearm();
    assert(rearm_success == true);

    // Assert that MODE1 was woken up back to 0x20 and prescaler was rewritten to 0x79
    assert(read_mock_register(PCA9685_REG_MODE1) == 0x20);
    assert(read_mock_register(PCA9685_REG_PRESCALE) == PCA9685_PRESCALE_50HZ);

    // Assert that cached joint positions (45°, 90°, 135°) were restored to registers
    assert(read_mock_pca9685_ticks(0) == 204); // 45 deg
    assert(read_mock_pca9685_ticks(1) == 307); // 90 deg
    assert(read_mock_pca9685_ticks(2) == 409); // 135 deg

    printf("  [TEST 5]: PASSED! ✅\n");
}

// ============================================================================
// 🚀 Test Harness Main Entry Point
// ============================================================================
int main(void) {
    printf("\n=========================================================\n");
    printf("🧪 RUNNING PHASE C: JOINT ACTUATOR UNIT TEST HARNESS\n");
    printf("=========================================================\n");

    test_pca9685_initialization();
    test_angle_to_tick_transformation_math();
    test_multi_axis_channel_isolation();
    test_bva_angle_clamping_protection();
    test_brownout_rearm_pipeline();

    printf("\n=========================================================\n");
    printf("🎉 ALL PHASE C UNIT TESTS PASSED 100%% GREEN!\n");
    printf("=========================================================\n\n");

    return 0;
}