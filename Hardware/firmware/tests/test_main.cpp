#include <iostream>
#include "../src/twi_driver.cpp" // Include the implementation file for testing purposes
// Forward declaration of your isolated test suite function from test_twi_driver.cpp
void run_twi_driver_tests();

int main() {
    std::cout << "\n========== RUNNING FIRMWARE UNIT TESTS ==========" << std::endl;
    
    // Execute the Phase A test group
    run_twi_driver_tests();
    
    std::cout << "================ ALL TESTS PASSED ================\n" << std::endl;
    return 0;
}