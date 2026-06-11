cmake_minimum_required(VERSION 3.15)
project(ConductorReceiver CXX C)
# Enforce generation of compile_commands.json for VS Code IntelliSense tracking
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(CMAKE_CXX_STANDARD 17)

# ==============================================================================
# TARGET PRODUCTION CROSS-COMPILATION PROFILE (avr-gcc)
# ==============================================================================
if(NOT RUN_HOST_TESTS)
    set(MCU atmega328p)
    set(MCU_SPEED 16000000UL)
    set(AVRDUDE_PROGRAMMER arduino)
    set(AVRDUDE_PORT /dev/tty.usbmodem*)

    set(CMAKE_C_COMPILER avr-gcc)
    set(CMAKE_CXX_COMPILER avr-g++)

    set(CMAKE_CXX_FLAGS "-mmcu=${MCU} -DF_CPU=${MCU_SPEED} -Os -Wall -Wextra -ffunction-sections -fdata-sections")

    include_directories(include)
    file(GLOB_RECURSE SOURCES "src/main.cpp" "src/ring_buffer.cpp")

    add_executable(${PROJECT_NAME}.elf ${SOURCES})

    add_custom_command(TARGET ${PROJECT_NAME}.elf POST_BUILD
        COMMAND avr-objcopy -O ihex -R .eeprom ${PROJECT_NAME}.elf ${PROJECT_NAME}.hex
        COMMENT "Building flash-memory image: ${PROJECT_NAME}.hex"
    )

    add_custom_target(upload
        COMMAND avrdude -F -V -c ${AVRDUDE_PROGRAMMER} -p m328p -P ${AVRDUDE_PORT} -b 115200 -U flash:w:${PROJECT_NAME}.hex:i
        DEPENDS ${PROJECT_NAME}.elf
        COMMENT "Streaming binary image payload over hardware interface lines..."
    )

# ==============================================================================
# HOST-SIDE LOCAL VERIFICATION TESTING PROFILE (clang++)
# ==============================================================================
else()
    message(STATUS "Building Host-Side Local Validation Harness Suite...")
    include_directories(include)
    
    # Compile firmware logic paired with your mock test runner definitions
    add_executable(test_runner tests/test_firmware_core.cpp src/ring_buffer.cpp)
    target_compile_definitions(test_runner PRIVATE TESTING_ON_HOST)
endif()