#include "../include/twi_driver.h"
#include <assert.h>
#include <stdio.h>

void run_twi_driver_mvp_tests(void) {
    printf("[STAGING]: Initializing TWI Driver Testing Pass...\n");
    
    // 1. Verify initialization clears our virtual peripheral bus tracking map
    twi_init();
    
    // Assert that a sample register is initially zeroed out
    assert(mock_twi_bus[0x00] == 0);
    assert(mock_twi_bus[0xFE] == 0);
    printf("  [PASS]: TWI driver virtualization mapping initialization confirmed clear.\n");

    // 2. Simulate a single-byte register write transaction targeting the PCA9685
    // Device Address: 0x40 (PCA9685 Base)
    // Register Address: 0x00 (MODE1 Control Register)
    // Value Payload: 0x20 (Auto-Increment Enable Flag)
    uint8_t target_device = 0x40;
    uint8_t target_register = 0x00;
    uint8_t expected_payload = 0x20;

    bool transaction_status = twi_write_reg(target_device, target_register, expected_payload);
    
    // Assert both the nominal return signature and memory position accuracy
    assert(transaction_status == true);
    assert(mock_twi_bus[target_register] == expected_payload);
    printf("  [PASS]: Monolithic byte-write successfully intercept mapped to mock address [0x%02X].\n", target_register);

    // 3. Stress-test random register assignment locations to confirm alignment stability
    twi_write_reg(0x40, 0xFA, 0xAA); // LED0_ON_H
    twi_write_reg(0x40, 0xFB, 0x55); // LED0_OFF_L
    
    assert(mock_twi_bus[0xFA] == 0xAA);
    assert(mock_twi_bus[0xFB] == 0x55);
    printf("  [PASS]: Dynamic multi-address register validation sweeps complete.\n");

    printf("[SUCCESS]: Phase A MVP TWI Core verification test suite passed perfectly!\n\n");
}

int main(void) {
    run_twi_driver_mvp_tests();
    return 0;
}