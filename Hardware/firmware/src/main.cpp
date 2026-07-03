#ifdef __AVR_ATmega328P__
  #include <Arduino.h>       // Provides the hardware millisecond timer (millis())
  #include <avr/io.h>
  #include <avr/interrupt.h>
#else
  // Fallbacks for local native testing on your MacBook
  #include <ctime>
  #include <chrono>
  #include <cstdint>

inline uint32_t millis() {
      // Relative 0ms alignment parameters
      static bool is_initialized = false;
      static auto baseline_epoch = std::chrono::steady_clock::now();
      
      // Latched cycle profiling state trackers
      static auto last_execution_call = std::chrono::steady_clock::now();
      static uint32_t virtual_accumulated_time_ms = 0;

      auto current_wall_clock = std::chrono::steady_clock::now();

      //  Establish Time-Zero on initial boot invocation
      if (!is_initialized) {
          baseline_epoch = current_wall_clock;
          last_execution_call = current_wall_clock;
          virtual_accumulated_time_ms = 0;
          is_initialized = true;
          return virtual_accumulated_time_ms;
      }

      // Compute raw difference between loop steps
      auto elapsed_since_last_tick = std::chrono::duration_cast<std::chrono::milliseconds>(
          current_wall_clock - last_execution_call
      ).count();

      // SPHERICAL FILTER PASS: Trap both thread scheduling stutters and deep sleep resume leaps
      // If a single cycle steps forward by more than 150ms, it is an environmental anomaly.
      if (elapsed_since_last_tick > 150) {
          // Clamp and saturate: pass forward a nominal step to stabilize the watchdog tracking
          virtual_accumulated_time_ms += 1; 
      } else {
          // Nominal path: step forward predictably in unison with actual elapsed time
          virtual_accumulated_time_ms += static_cast<uint32_t>(elapsed_since_last_tick);
      }

      // Snapshot the active timeline point to evaluate the next cycle block iteration
      last_execution_call = current_wall_clock;

      return virtual_accumulated_time_ms;
  }
#endif

#include "../include/circular_buffer.h"
#include "../include/watchdog_interlock.h"
#include "../include/packet_parser.h"

// ---------------------------------------------------------
// 1. GLOBAL COMPONENT INSTANTIATION
// ---------------------------------------------------------
CircularBuffer rx_buffer;
WatchdogInterlock watchdog;
PacketParser parser;

#define HARDWARE_SAFETY_PIN 10

// External hardware hooks mapped from our .cpp source files
namespace HardwareBinding { void configure_serial_interrupt_links(); }
extern void configure_hardware_interlock_pins(uint8_t safety_pin);
extern void cut_actuator_electrical_rails(uint8_t safety_pin);

// ---------------------------------------------------------
// 2. HARDWARE INTERRUPT SERVICE ROUTINE (ISR)
// ---------------------------------------------------------
#ifdef __AVR_ATmega328P__
// This hardware vector fires automatically the nanosecond a USB byte hits the chip
ISR(USART_RX_vect) {
    uint8_t incoming_byte = UDR0; // Read directly from the silicon UART register
    rx_buffer.enqueue(incoming_byte); // Zero-copy drop into the memory ring
}
#endif

// ---------------------------------------------------------
// 3. SYSTEM INITIALIZATION GATE
// ---------------------------------------------------------
void setup_firmware() {
    #ifdef __AVR_ATmega328P__
    Serial.begin(115200); // Set standard high-speed UART baud rate
    #endif

    // Initialize our modular components
    rx_buffer.init();
    parser.init();
    watchdog.init(HARDWARE_SAFETY_PIN);

    // Bind software logic to physical copper pins and interrupt masks
    configure_hardware_interlock_pins(HARDWARE_SAFETY_PIN);
    HardwareBinding::configure_serial_interrupt_links();
}

// ---------------------------------------------------------
// 4. INFINITE DETERMINISTIC SCHEDULER LOOP
// ---------------------------------------------------------
int main() {
    setup_firmware();

    while (true) {
  
        // Inside main.cpp loop block
        uint32_t current_time_ms;

        #ifdef __AVR_ATmega328P__
            current_time_ms = millis(); // The real Arduino hardware timer call
        #else
            // Standard platform-agnostic high-resolution clock simulation
            // Using std::chrono ensures perfect MacBook terminal compilation compatibility
            current_time_ms = static_cast<uint32_t>(
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now().time_since_epoch()
                ).count()
            );
        #endif

        // --- STAGE A: PROGNOSTIC SAFETY EVALUATION ---
        // Evaluate time-delta. If communication is dead, drop power instantly.
        if (!watchdog.evaluate_state(current_time_ms)) {
            cut_actuator_electrical_rails(HARDWARE_SAFETY_PIN);
        }

        // --- STAGE B: DATA INGESTION & PIPELINE DRAIN ---
        uint8_t extracted_byte;
        // Continuously pop bytes out of the buffer until it is empty
        while (rx_buffer.dequeue(extracted_byte)) {
            
            // --- STAGE C: TOKENIZATION & VALIDATION ---
            // Feed the extracted byte into the parser state machine
            bool frame_complete = parser.update(extracted_byte);
            
            if (frame_complete) {
                // A full "\n" terminated envelope was successfully captured!
                // (In Sprint 8, we will extract the payload, run the XOR checksum via 
                // validate_packet_integrity(), and command the motors here).
                
                // KICK THE DOG: The frame arrived safely. Reset the safety countdown!
                watchdog.reset_timer(current_time_ms);
            }
        }
    }
    return 0;
}