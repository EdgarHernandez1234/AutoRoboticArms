#include "../include/circular_buffer.h"

// Hardware configuration macro flags for ATmega328P target platforms
#ifdef __AVR_ATmega328P__
#include <avr/io.h>
#include <avr/interrupt.h>
#endif

/**
 * Note: Since our class methods are fully optimized and implemented inline 
 * inside 'circular_buffer.h' to enable high-velocity TDD execution on both 
 * the local developer laptop and the headless target node, this translation 
 * unit handles lower-level hardware peripheral pre-flight optimizations.
 */

namespace HardwareBinding {
    
    void configure_serial_interrupt_links() {
        #ifdef __AVR_ATmega328P__
        // SECURITY INTERCEPT: Enable RX Complete Interrupt (RXCIE0) 
        // This ensures the hardware instantly populates our CircularBuffer 
        // on a byte-receive event without stalling the main processor clock.
        UCSR0B |= (1 << RXCIE0);
        
        // Globally unmask hardware interrupts
        sei();
        #endif
    }
}