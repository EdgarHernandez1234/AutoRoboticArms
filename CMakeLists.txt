cmake_minimum_required(VERSION 3.10)

# Define project name and version
project(AutoRoboticArms_Firmware VERSION 1.0.0)

# Enforce C++11 standard and strict compiler warnings
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED True)
add_compile_options(-Wall -Wextra -Wpedantic -O2)

# Point to header directory inside Hardware/firmware/include
include_directories(Hardware/firmware/include)

# Group core Phase C & D Flat C-API source implementations
set(FIRMWARE_CORE_SOURCES
    Hardware/firmware/src/ring_buffer.cpp
    Hardware/firmware/src/packet_parser.cpp
    Hardware/firmware/src/joint_actuator.cpp
    Hardware/firmware/src/watchdog_interlock.cpp
    Hardware/firmware/src/twi_driver.cpp
)

# -----------------------------------------------------------------------------
# 🧪 PHASE D: Software-in-the-Loop (SIL) Integration Pipeline Target
# -----------------------------------------------------------------------------
add_executable(test_integration_pipeline
    Hardware/firmware/tests/test_integration_pipeline.cpp
    ${FIRMWARE_CORE_SOURCES}
)