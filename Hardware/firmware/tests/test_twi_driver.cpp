#include "../include/twi_driver.h"
#include <assert.h>
#include <stdio.h>

void run_armored_twi_tests(void) {
    printf("[STAGING]: Initializing Armored TWI Driver Test Suite...\n");

    // 0. Baseline Initialization
    twi_init();
    assert(twi_get_state() == TWI_IDLE);

    // TEST CASE A: The Chaining Sequence Violation Trap
    printf("  [TEST A]: Executing Out-of-Order Sequence Violation...\n");
    // Attempting to write a data byte without claiming the bus via twi_start() first
    bool bad_write = twi_write(0x20); 
    assert(bad_write == false); // The internal guard must reject the operation
    assert(twi_get_state() == TWI_IDLE); // The state must remain unchanged
    printf("    [PASS]: Driver successfully rejected uninitialized twi_write().\n");

    // TEST CASE B: Virtual Out-of-Bounds Memory Invalidation
    printf("  [TEST B]: Executing Memory Boundary Overrun...\n");
    twi_start();
    twi_write(0x80); // Step 1: Device Address (Write Mode)
    twi_write(255);  // Step 2: Set the internal memory pointer to the absolute edge of the array (Index 255)
    
    // Step 3: Write a valid byte to the edge index. The pointer will auto-increment to 256 internally.
    bool good_write = twi_write(0xAA); 
    assert(good_write == true);
    assert(mock_twi_bus[255] == 0xAA);

    // Step 4: Attempt a sequential write that pushes the pointer to index 256 (Out of Bounds!)
    bool overflow_write = twi_write(0xBB);
    assert(overflow_write == false); // The array boundary guard must intercept and reject this
    assert(twi_get_state() == TWI_FAULT_STATE); // Driver must lock down
    printf("    [PASS]: Emulation layer successfully blocked memory pointer overflow and triggered FAULT_STATE.\n");

    // TEST CASE C & D: Fault State Lockout and Manual Bus Recovery
    printf("  [TEST C/D]: Verifying Lockout Integrity and Hardware Reset Hook...\n");
    // Prove that once in a fault state, standard commands are ignored
    bool locked_start = twi_start(); 
    assert(locked_start == false); 

    // Execute the programmatic recovery hook
    twi_force_bus_reset();
    assert(twi_get_state() == TWI_IDLE); // State should snap back to nominal

    // Verify the bus is open for business again
    bool recovered_start = twi_start();
    assert(recovered_start == true);
    assert(twi_get_state() == TWI_BUS_SECURED);
    twi_stop();
    printf("    [PASS]: Driver successfully recovered from terminal fault state via twi_force_bus_reset().\n");

    printf("\n[SUCCESS]: All Armored TWI Core defenses verified! Host runtime is secure.\n\n");
}

int main(void) {
    run_armored_twi_tests();
    return 0;
}