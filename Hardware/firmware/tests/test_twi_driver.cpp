#ifndef __AVR_ATmega328P__
#include "twi_driver.h"
#include <cassert>
#include <iostream>

void test_twi_mock_bus_transactions() {
    HardwareBinding::TWIDriver mock_twi;
    
    // Step 1: Initialize and check that the mock bus starts completely blank
    mock_twi.init(100000);
    assert(mock_twi.get_mock_write_count() == 0);
    
    // Step 2: Simulate an I2C transaction sequence
    bool start_status = mock_twi.start();
    assert(start_status == true);
    
    // Write a slave address (e.g., PCA9685 address 0x40, write bit 0)
    bool addr_status = mock_twi.write_address(0x40, false);
    assert(addr_status == true);
    
    // Write a mock data register byte and data value byte
    bool reg_status = mock_twi.write_byte(0x00); // Mode 1 Register
    bool val_status = mock_twi.write_byte(0x20); // Auto-Increment Enable bit value
    
    assert(reg_status == true);
    assert(val_status == true);
    
    // Step 3: Assert against our virtual silicon array to verify value delivery
    assert(mock_twi.get_mock_write_count() == 2);
    assert(mock_twi.read_mock_register(0) == 0x00); // First byte written
    assert(mock_twi.read_mock_register(1) == 0x20); // Second byte written
    
    std::cout << "[PHASE A TEST]: TWIDriver Mock isolated test pass successfully!" << std::endl;
}
#endif