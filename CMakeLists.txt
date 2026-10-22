cmake_minimum_required(VERSION 3.10)
project(AutoRoboticArms_Firmware VERSION 1.0.0)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED True)
add_compile_options(-Wall -Wextra -Wpedantic -O2)

# Point to headers using absolute source directory resolution
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/Hardware/firmware/include)

# Group core firmware C++ translation units
set(FIRMWARE_CORE_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/Hardware/firmware/src/circular_buffer.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/Hardware/firmware/src/packet_parser.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/Hardware/firmware/src/joint_actuator.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/Hardware/firmware/src/watchdog_interlock.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/Hardware/firmware/src/twi_driver.cpp
)

# -----------------------------------------------------------------------------
# 🧪 PHASE D: Software-in-the-Loop (SIL) Integration Pipeline Target
# -----------------------------------------------------------------------------
add_executable(test_integration_pipeline
    ${CMAKE_CURRENT_SOURCE_DIR}/Hardware/firmware/tests/test_integration_pipeline.cpp
    ${FIRMWARE_CORE_SOURCES}
)