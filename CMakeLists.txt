cmake_minimum_required(VERSION 3.10)

# Define the project name and version
project(AutoRoboticArms_Firmware VERSION 1.0.0)

# Enforce C++11 standard and strict compiler warnings
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED True)
add_compile_options(-Wall -Wextra -Wpedantic -O2)

# Tell the compiler where to find the header files (.h)
include_directories(firmware/include)

# Group all of the core Phase C & Phase D Flat C-API source files
set(FIRMWARE_CORE_SOURCES
    firmware/tests/circular_buffer.cpp
    firmware/tests/packet_parser.cpp
    firmware/tests/joint_actuator.cpp
    firmware/tests/watchdog_interlock.cpp
    firmware/tests/twi_driver.cpp
    firmware/tests/test_integration_pipeline.cpp
)

# -----------------------------------------------------------------------------
#  PHASE D: Software-in-the-Loop (SIL) Integration Pipeline Target
# -----------------------------------------------------------------------------
add_executable(test_integration_pipeline
    firmware/tests/test_integration_pipeline.cpp
    ${FIRMWARE_CORE_SOURCES}
)

# Note: main.cpp is the AVR Silicon entry point. 
# It is compiled separately via AVR-GCC/Makefiles or PlatformIO, 
# not the host-side CI test toolchain.