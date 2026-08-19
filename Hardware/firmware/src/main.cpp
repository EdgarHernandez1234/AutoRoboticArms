#include <stdint.h>
#include <stdbool.h>
#include "../include/circular_buffer.h"
#include "../include/packet_parser.h"
#include "../include/twi_driver.h"
#include "../include/joint_actuator.h"
#include "../include/watchdog_interlock.h"

// ============================================================================
// Platform-Specific Hardware Hooks (AVR Silicon vs. Host Simulation)
// ============================================================================
#ifdef __AVR_ATmega328P__
  #include <avr/io.h>
  #include <avr/interrupt.h>
  // Externally linked Arduino Core millis() function
    extern "C" uint32_t millis(void)
#else
    #include <stdio.h>
    // Virtual mock clock injection for 0ms CI test execution
    extern uint32_t get_simulated_millis(void);
    #define millis() get_simulated_millis()
    
    // Virtual UART telemetry hook for host-side assertions
    extern void mock_uart_transmit_byte(uint8_t byte);
#endif

// ============================================================================
// 📦 Global State Instances
// ============================================================================
CircularBuffer g_rx_buffer;
PacketParser   g_parser;

bool g_is_in_safety_halt = false;
// Slew-Rate Interpolation Caches
uint8_t g_target_angles[MAX_ROBOTIC_JOINTS]  = {90, 90, 90};
uint8_t g_current_angles[MAX_ROBOTIC_JOINTS] = {90, 90, 90};

// Re-Arming Security Gate
uint8_t g_consecutive_valid_frames = 0;
uint32_t g_last_actuator_ms = 0;

// ============================================================================
// Initialization & Telemetry Helpers
// ============================================================================
void hardware_setup(void) {
    // 1. Initialize Subsystems
    circular_buffer_init(&g_rx_buffer);
    packet_parser_init(&g_parser);
    joint_actuator_init();
    watchdog_init(3000); // Set 3000 ms Dead-Man's threshold

#ifdef __AVR_ATmega328P__
    // 2. Initialize Hardware UART @ 115200 Baud (16 MHz CPU Clock)
    // Formula: UBRR = (16,000,000 / (16 * 115200)) - 1 = 7.68 (~8)
    UBRR0H = 0;
    UBRR0L = 8;
    
    // Enable RX, TX, and RX-Complete Interrupts
    UCSR0B = (1 << RXEN0) | (1 << TXEN0) | (1 << RXCIE0);
    // 8-bit Data, 1 Stop Bit, No Parity
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00);
    
    // 3. Enable Global Interrupts (Booting the ISR priority)
    sei();
#endif
}

void send_telemetry_ack(char status_byte) {
#ifdef __AVR_ATmega328P__
    // Wait for empty transmit buffer, then fire the byte down the USB TX wire
    while (!(UCSR0A & (1 << UDRE0))); 
    UDR0 = status_byte;
#else
    mock_uart_transmit_byte((uint8_t)status_byte);
#endif
}

// ============================================================================
// Hardware Interrupt Service Routine (Priority 1: Zero-Latency Ingestion)
// ============================================================================
#ifdef __AVR_ATmega328P__
ISR(USART_RX_vect) {
    // Instantly capture byte from hardware register and push to CircularBuffer
    uint8_t incoming_byte = UDR0;
    if (!circular_buffer_write(&g_rx_buffer, incoming_byte)) {
        // Drop byte silently on overflow; Watchdog handles stalls if frames corrupt
    }
}
#endif

// ============================================================================
// Master Cooperative Super-Loop
// ============================================================================
int main(void) {
    hardware_setup();

    // The Deterministic Execution Engine
    while (1) {
        uint32_t current_ms = millis();

        // --------------------------------------------------------------------
        // [Task A] The Prognostic Watchdog Interlock (Continuous Check)
        // --------------------------------------------------------------------
        bool is_safe = watchdog_check();
        
        if (!is_safe) {
            if (!g_is_in_safety_halt) {
            g_is_in_safety_halt = true;
            g_consecutive_valid_frames = 0;
            }
            // [Jax's Defense] Communication lost! Lock motors at cached positions
            // Do NOT cut PWM to 0. Hold torque to prevent physical collapse.
            joint_actuator_write_all_cached();
        }

        // --------------------------------------------------------------------
        // [Task B] Greedy 1-Byte Parser Drain (Priority 2)
        // --------------------------------------------------------------------
        uint8_t byte_in;
        if (circular_buffer_read(&g_rx_buffer, &byte_in)) {
            // Feed exactly 1 byte into the FSM to avoid starving the 20ms clock
            ParseStatus status = packet_parser_process_byte(&g_parser, byte_in);

        if (status == PARSE_SUCCESS) {
                if (g_is_in_safety_halt) {
                    g_consecutive_valid_frames++;
                    if (g_consecutive_valid_frames >= 3) {
                        g_is_in_safety_halt = false;
                        g_consecutive_valid_frames = 0;
                        watchdog_reset();
                        send_telemetry_ack('K');

                        g_target_angles[0] = g_parser.parsed_angles[0];
                        g_target_angles[1] = g_parser.parsed_angles[1];
                        g_target_angles[2] = g_parser.parsed_angles[2];
                    } else {
                        send_telemetry_ack('H');
                    }
                } else {
                    watchdog_reset();
                    send_telemetry_ack('K');

                    g_target_angles[0] = g_parser.parsed_angles[0];
                    g_target_angles[1] = g_parser.parsed_angles[1];
                    g_target_angles[2] = g_parser.parsed_angles[2];
                }
            } else if (status == PARSE_ERROR_CHECKSUM || status == PARSE_ERROR_FORMAT) {
                send_telemetry_ack('E');
                g_consecutive_valid_frames = 0;
            }
        }
        // --------------------------------------------------------------------
        // [Task C] Cadenced Actuator Dispatch & Slew-Rate (Priority 3)
        // --------------------------------------------------------------------
        // Limit high-latency I2C writes to 50 Hz (20ms periods)
        if (current_ms - g_last_actuator_ms >= 20) {
            g_last_actuator_ms = current_ms;

            if (is_safe) {
                bool physical_motion_required = false;

                // [Jax's Defense] Slew-Rate Interpolation (Max 2 degrees per 20ms tick)
                // Prevents gears from stripping when recovering from a halt offset
                for (int i = 0; i < MAX_ROBOTIC_JOINTS; i++) {
                    if (g_current_angles[i] < g_target_angles[i]) {
                        g_current_angles[i] += (g_target_angles[i] - g_current_angles[i] >= 2) ? 2 : 1;
                        physical_motion_required = true;
                    } else if (g_current_angles[i] > g_target_angles[i]) {
                        g_current_angles[i] -= (g_current_angles[i] - g_target_angles[i] >= 2) ? 2 : 1;
                        physical_motion_required = true;
                    }
                }

                if (physical_motion_required) {
                    // Write interpolated setpoint via I2C transport layer
                    joint_actuator_write_all(g_current_angles, MAX_ROBOTIC_JOINTS);
                }
            }
        }
    }

    return 0; // Never reached in embedded systems
}
