#include "../include/watchdog_interlock.h"

// Target compilation shielding for bare-metal register manipulation
#ifdef __AVR_ATmega328P__
#include <avr/io.h>
#include <avr/wdt.h>
#include <avr/interrupt.h>
#endif

/**
 * Low-level register implementation of our emergency shutdown procedures.
 * This binds our portable validation math to direct hardware pin controls.
 */
#ifdef __AVR_ATmega328P__
void configure_hardware_interlock_pins(uint8_t safety_pin) {
    // Set the designated safety relay control pin as an OUTPUT
    // Equivalent to pinMode(safety_pin, OUTPUT) but direct port manipulated
    if (safety_pin >= 8 && safety_pin <= 13) {
        DDRB |= (1 << (safety_pin - 8)); // Digital Pins 8-13 map onto Port B registers
    } else if (safety_pin >= 0 && safety_pin <= 7) {
        DDRD |= (1 << safety_pin);       // Digital Pins 0-7 map onto Port D registers
    }

    // INITIAL baseline STATE: Force pin HIGH to energize our safety connection tracks
    if (safety_pin >= 8 && safety_pin <= 13) {
        PORTB |= (1 << (safety_pin - 8));
    } else if (safety_pin >= 0 && safety_pin <= 7) {
        PORTD |= (1 << safety_pin);
    }
}

void cut_actuator_electrical_rails(uint8_t safety_pin) {
    // EMERGENCY ACTION: Instantly clear the bit to ground out the safety pin,
    // dropping power/signal lines to our PCA9685 servo driver array.
    if (safety_pin >= 8 && safety_pin <= 13) {
        PORTB &= ~(1 << (safety_pin - 8));
    } else if (safety_pin >= 0 && safety_pin <= 7) {
        PORTD &= ~(1 << safety_pin);
    }
}
#else
// Mock declarations for native testing compilation on developer laptops
void configure_hardware_interlock_pins(uint8_t safety_pin) {
    (void)safety_pin; // Explicitly mutes the unused-parameter compiler warning
}
void cut_actuator_electrical_rails(uint8_t safety_pin) {
    (void)safety_pin; // Clean, zero-overhead, zero-byte compilation footprint
}
#endif