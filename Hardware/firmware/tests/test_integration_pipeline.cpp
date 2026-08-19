#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

#include "../include/circular_buffer.h"
#include "../include/packet_parser.h"
#include "../include/joint_actuator.h"
#include "../include/watchdog_interlock.h"
#include "../include/twi_driver.h"

// ============================================================================
// 🕰️ VIRTUAL HARDWARE MOCKS & CLOCK INJECTION
// ============================================================================
uint32_t g_mock_system_millis = 0;
char g_mock_uart_tx_log[256];
int g_mock_uart_tx_index = 0;

// Hook for millis() override
uint32_t get_simulated_millis(void) {
    return g_mock_system_millis;
}

// Hook for UART TX override
void mock_uart_transmit_byte(uint8_t byte) {
    if (g_mock_uart_tx_index < 255) {
        g_mock_uart_tx_log[g_mock_uart_tx_index++] = (char)byte;
        g_mock_uart_tx_log[g_mock_uart_tx_index] = '\0'; // Keep null-terminated
    }
}

// ============================================================================
// 📦 GLOBAL STATE (Mirroring main.cpp)
// ============================================================================
CircularBuffer g_rx_buffer;
PacketParser   g_parser;

uint8_t g_target_angles[3]  = {90, 90, 90};
uint8_t g_current_angles[3] = {90, 90, 90};

uint8_t g_consecutive_valid_frames = 0;
uint32_t g_last_actuator_ms = 0;

// ============================================================================
// ⚙️ THE SUPER-LOOP REPLICA (Executes 1 Tick of main.cpp's while(1) loop)
// ============================================================================

// Latch flag to track state transitions
bool g_is_in_safety_halt = false;
void execute_super_loop_step(void) {
    uint32_t current_ms = get_simulated_millis();

    // --------------------------------------------------------------------
    // [Task A] Prognostic Watchdog Interlock
    // --------------------------------------------------------------------
    bool is_safe = watchdog_check();
    
    if (!is_safe) {
        if (!g_is_in_safety_halt) {
            // First tick detecting communication loss: trip the halt and wipe trust
            g_is_in_safety_halt = true;
            g_consecutive_valid_frames = 0;
        }
        joint_actuator_write_all_cached(); // Lock holding torque!
    }

    // --------------------------------------------------------------------
    // [Task B] Greedy 1-Byte Parser Drain
    // --------------------------------------------------------------------
    uint8_t byte_in;
    if (circular_buffer_read(&g_rx_buffer, &byte_in)) {
        ParseStatus status = packet_parser_process_byte(&g_parser, byte_in);

        if (status == PARSE_SUCCESS) {
            if (g_is_in_safety_halt) {
                // In safety halt: require 3 consecutive valid frames to re-arm
                g_consecutive_valid_frames++;
                
                if (g_consecutive_valid_frames >= 3) {
                    g_is_in_safety_halt = false;
                    g_consecutive_valid_frames = 0;
                    watchdog_reset();
                    mock_uart_transmit_byte('K'); // Re-armed and moving
                    
                    g_target_angles[0] = g_parser.parsed_angles[0];
                    g_target_angles[1] = g_parser.parsed_angles[1];
                    g_target_angles[2] = g_parser.parsed_angles[2];
                } else {
                    mock_uart_transmit_byte('H'); // Still halted, building trust
                }
            } else {
                // Normal nominal execution
                watchdog_reset();
                mock_uart_transmit_byte('K');
                
                g_target_angles[0] = g_parser.parsed_angles[0];
                g_target_angles[1] = g_parser.parsed_angles[1];
                g_target_angles[2] = g_parser.parsed_angles[2];
            }
        } else if (status == PARSE_ERROR_CHECKSUM || status == PARSE_ERROR_FORMAT) {
            mock_uart_transmit_byte('E');
            g_consecutive_valid_frames = 0; // Corrupt packet resets trust
        }
    }

    // --------------------------------------------------------------------
    // [Task C] Cadenced Actuator Dispatch (20ms / 50 Hz Filter)
    // --------------------------------------------------------------------
    if (current_ms - g_last_actuator_ms >= 20) {
        g_last_actuator_ms = current_ms;
        
        if (!g_is_in_safety_halt) {
            bool physical_motion_required = false;
            for (int i = 0; i < 3; i++) {
                if (g_current_angles[i] < g_target_angles[i]) {
                    g_current_angles[i] += (g_target_angles[i] - g_current_angles[i] >= 2) ? 2 : 1;
                    physical_motion_required = true;
                } else if (g_current_angles[i] > g_target_angles[i]) {
                    g_current_angles[i] -= (g_current_angles[i] - g_target_angles[i] >= 2) ? 2 : 1;
                    physical_motion_required = true;
                }
            }
            if (physical_motion_required) {
                joint_actuator_write_all(g_current_angles, 3);
            }
        }
    }
}
// ============================================================================
// 🛠️ TEST HELPERS
// ============================================================================
void feed_serial_string(const char* str) {
    while (*str) {
        circular_buffer_write(&g_rx_buffer, (uint8_t)*str);
        str++;
    }
}

void reset_test_state(void) {
    g_mock_system_millis = 0;
    g_mock_uart_tx_index = 0;
    g_mock_uart_tx_log[0] = '\0';
    g_consecutive_valid_frames = 0;
    g_is_in_safety_halt = false;
    g_last_actuator_ms = 0;
    
    g_target_angles[0] = 90; g_target_angles[1] = 90; g_target_angles[2] = 90;
    g_current_angles[0] = 90; g_current_angles[1] = 90; g_current_angles[2] = 90;

    circular_buffer_init(&g_rx_buffer);
    packet_parser_init(&g_parser);
    joint_actuator_init();
    watchdog_init(3000);
    reset_mock_bus();
}

std::string generate_valid_frame(int j0, int j1, int j2) {
    char payload[32];
    snprintf(payload, sizeof(payload), "DRV,%d,%d,%d", j0, j1, j2);
    uint8_t checksum = 0;
    for (int i = 0; payload[i] != '\0'; i++) checksum ^= payload[i];
    char frame[64];
    snprintf(frame, sizeof(frame), "@%s*%02X\n", payload, checksum);
    return std::string(frame);
}

// Reconstitute 12-bit PCA9685 tick value from mock I2C array
uint16_t read_mock_pca9685_ticks(uint8_t channel) {
    uint8_t off_l_reg = 0x08 + (channel * 4);
    uint8_t off_h_reg = 0x09 + (channel * 4);
    uint8_t low = read_mock_register(off_l_reg);
    uint8_t high = read_mock_register(off_h_reg);
    return (uint16_t)(low | ((high & 0x0F) << 8));
}

// ============================================================================
// 🧪 UNIT TEST CASES
// ============================================================================

void test_fragmented_ingestion_and_nominal_execution(void) {
    printf("  [TEST 1]: Fragmented String Ingestion & Slew-Rate Dispatch...\n");
    reset_test_state();

    std::string frame = generate_valid_frame(100, 110, 120);
    
    // Fragment 1: Inject first 5 bytes ("@DRV,")
    for (int i = 0; i < 5; i++) {
        circular_buffer_write(&g_rx_buffer, frame[i]);
        execute_super_loop_step(); // Crank loop 5 times
    }
    assert(g_mock_uart_tx_index == 0); // No ACK yet

    // Fragment 2: Inject the rest of the frame
    for (size_t i = 5; i < frame.length(); i++) {
        circular_buffer_write(&g_rx_buffer, frame[i]);
        execute_super_loop_step();
    }
    
    // Assert 1: System acknowledged the valid frame with 'K'
    assert(g_mock_uart_tx_log[0] == 'K');

    // Fast-forward time to allow Slew-Rate interpolation to reach targets
    for (int i = 0; i < 100; i++) {
        g_mock_system_millis += 20; // Skip forward in 20ms steps
        execute_super_loop_step();
    }

    // Assert 2: Joint Actuator processed final degrees into 12-bit ticks
    assert(read_mock_pca9685_ticks(0) == 329); // 100 deg -> 329 ticks
    assert(read_mock_pca9685_ticks(1) == 352); // 110 deg -> 352 ticks
    assert(read_mock_pca9685_ticks(2) == 375); // 120 deg -> 375 ticks

    printf("  [TEST 1]: PASSED! ✅\n");
}

void test_cyber_physical_watchdog_trip(void) {
    printf("  [TEST 2]: Watchdog 3000ms Timeout Trip & Safe Holding Torque...\n");
    reset_test_state();

    // 1. Send a command to move joints to 100 degrees (100 deg = 329 ticks)
    std::string init_frame = generate_valid_frame(100, 100, 100);
    feed_serial_string(init_frame.c_str());
    for (size_t i = 0; i < init_frame.length(); i++) {
        execute_super_loop_step();
    }

    // Step virtual time through the slew-rate ramp until joints reach 100 deg
    for (int i = 0; i < 20; i++) {
        g_mock_system_millis += 20;
        execute_super_loop_step();
    }

    // Verify initial bus state is active at 100 deg (329 ticks)
    assert(read_mock_pca9685_ticks(0) == 329);

    // 2. Advance mock time past the 3000ms threshold (Communication Loss)
    g_mock_system_millis += 3500;
    execute_super_loop_step(); 

    // Assert 1: Watchdog flagged the system as unsafe
    assert(watchdog_check() == false);

    // Assert 2: Safe holding torque remains active at 100 deg (329 ticks)
    assert(read_mock_pca9685_ticks(0) == 329);

    // 3. Feed a movement command while halted
    std::string rejected_frame = generate_valid_frame(180, 180, 180);
    feed_serial_string(rejected_frame.c_str());
    for (size_t i = 0; i < rejected_frame.length(); i++) {
        execute_super_loop_step();
    }

    // Assert 3: System rejects execution and replies with 'H' (Halt Notice)
    assert(g_mock_uart_tx_log[g_mock_uart_tx_index - 1] == 'H');

    // Assert 4: Registers were NOT changed to 180 deg (512 ticks); holding torque stayed at 329
    assert(read_mock_pca9685_ticks(0) == 329);

    printf("  [TEST 2]: PASSED! ✅\n");
}

void test_3_frame_trust_rearming_gate(void) {
    printf("  [TEST 3]: 3-Frame Trust Barrier Re-Arming Sequence...\n");
    reset_test_state();

    watchdog_reset(); // Bootstrap the watchdog
    // Force safety trip
    g_mock_system_millis += 3500;
    execute_super_loop_step();
    assert(watchdog_check() == false);

    std::string valid_frame = generate_valid_frame(90, 90, 90);
    std::string bad_frame = "@DRV,90,90,90*FF\n"; // Bad checksum

    // Frame 1 (Valid) -> Should stay Halted
    feed_serial_string(valid_frame.c_str());
    for(size_t i=0; i<valid_frame.length(); i++) execute_super_loop_step();
    assert(g_mock_uart_tx_log[0] == 'H'); 
    
    // Frame 2 (Corrupt) -> Resets Trust to 0, emits 'E'
    feed_serial_string(bad_frame.c_str());
    for(size_t i=0; i<bad_frame.length(); i++) execute_super_loop_step();
    assert(g_mock_uart_tx_log[1] == 'E');

    // Frame 3, 4, 5 (Valid Sequence) -> Builds trust and Re-Arms
    for (int j = 0; j < 3; j++) {
        feed_serial_string(valid_frame.c_str());
        for(size_t i=0; i<valid_frame.length(); i++) execute_super_loop_step();
    }
    
    // Assert: Last telemetry byte emitted should now be 'K' (Re-Armed & Executing)
    assert(g_mock_uart_tx_log[g_mock_uart_tx_index - 1] == 'K');
    assert(watchdog_check() == true); // System is live again!

    printf("  [TEST 3]: PASSED! ✅\n");
}

// ============================================================================
// 🚀 Test Harness Main Entry Point
// ============================================================================
int main(void) {
    printf("\n=========================================================\n");
    printf("🧪 RUNNING PHASE D: END-TO-END SIL INTEGRATION PIPELINE\n");
    printf("=========================================================\n");

    test_fragmented_ingestion_and_nominal_execution();
    test_cyber_physical_watchdog_trip();
    test_3_frame_trust_rearming_gate();

    printf("\n=========================================================\n");
    printf("🎉 PHASE D INTEGRATION PIPELINE VERIFIED 100%% SECURE!\n");
    printf("=========================================================\n\n");

    return 0;
}