#define __AVR_ATmega328P__
#include <avr/io.h>
#include <avr/interrupt.h>
#include "../include/ring_buffer.h"

SystemState currentSystemState = SYSTEM_INIT;
unsigned long lastValidPacketTime = 0;
const unsigned long WATCHDOG_TIMEOUT_MS = 300;

// Primitive software millis tracking register for standard AVR chips
volatile unsigned long timer_millis = 0;

// Timer0 Overflow Interrupt Service Routine (Fires approx every 1ms)
ISR(TIMER0_OVF_vect) {
    timer_millis++;
}

// Hardware UART Receive Complete Interrupt Service Routine
ISR(USART_RX_vect) {
    uint8_t incomingByte = UDR0; // Read directly from the hardware serial data register
    push_serial_byte(incomingByte);
}

void init_avr_registers() {
    // --- 1. CONFIGURE NATIVE HARDWARE UART (115200 Baud @ 16MHz Clock) ---
    uint16_t ubrr_value = 16; // Calculated via data-sheet rules for 115200 double-speed
    UBRR0H = (uint8_t)(ubrr_value >> 8);
    UBRR0L = (uint8_t)ubrr_value;
    
    UCSR0A |= (1 << U2X0); // Enable double-speed transmission mode
    UCSR0B |= (1 << RXCIE0) | (1 << RXEN0) | (1 << TXEN0); // Enable RX Interrupt, RX, and TX lines
    UCSR0C |= (1 << UCSZ01) | (1 << UCSZ00); // Set frame format: 8 Data Bits, 1 Stop Bit (8N1)

    // --- 2. DETERMINISTIC HARDWARE BOOT-FLUSH ---
    // Natively drain the ATmega328P's internal hardware internal FIFO pipeline
    // to destroy any stray electrical noise or leftovers from a previous host run
    uint8_t dummy_flush = 0;
    while (UCSR0A & (1 << RXC0)) {
        dummy_flush = UDR0; // Repetitively read the data register to empty the silicon queue
        (void)dummy_flush;  // Prevent compiler from optimization-stripping this out
    }

    // Force our software Static Ring Buffer pointers back to absolute zero baseline
    head = 0;
    tail = 0;
    for (uint8_t i = 0; i < BUFFER_SIZE; i++) {
        ringBuffer[i] = 0; // Completely sanitize memory array space
    }

    // --- 3. CONFIGURE TIMER0 FOR MILLIS TRACKING ---
    TCCR0B |= (1 << CS01) | (1 << CS00); // Set clock prescaler to 64
    TIMSK0 |= (1 << TOIE0);              // Enable Timer0 Overflow Interrupt
    
    sei(); // Enable global interrupts safely now that memory is sanitized
}

void verify_watchdog_interlock() {
    // Protected snapshot read of volatile clock register
    cli();
    unsigned long current_time = timer_millis;
    sei();
    
    if ((current_time - lastValidPacketTime) > WATCHDOG_TIMEOUT_MS) {
        if (currentSystemState == SYSTEM_NOMINAL) {
            handle_system_fault(SYSTEM_FAULT_TIMEOUT);
        }
    }
}

void handle_system_fault(SystemState faultType) {
    currentSystemState = faultType;
    
    if (faultType == SYSTEM_FAULT_TIMEOUT) {
        // Watched timeline expiration logic
        execute_safe_home_postures();
    } 
    else if (faultType == SYSTEM_FAULT_CHECKSUM) {
        transmit_uart_string("[SECURITY ALERT] CRC8 MISMATCH. Actuators frozen. Awaiting Secure Recovery Key...");
        
        // 🔒 HARD PROTOCOL STATE ISOLATION ENGINE
        // Completely hijack the main loop runner. Standard parsing is disabled.
        while (currentSystemState == SYSTEM_FAULT_CHECKSUM) {
            
            // Step 1: Keep pushing background incoming bytes over the UART lines into the buffer
            // Our direct hardware interrupt ISR(USART_RX_vect) continues handling this in isolation.
            
            // Step 2: Run our hyper-focused, zero-allocation handshake matching sweep
            verify_isolated_recovery_handshake();
            
            // Step 3: Maintain timeline watchdog health checks so the chip doesn't experience physical resets
            verify_watchdog_interlock(); 
        }
        
        transmit_uart_string("[SYSTEM HEALED] Authenticated Handshake Verified. State registers reset to NOMINAL.");
    }
}

void verify_isolated_recovery_handshake() {
    // Our secure 6-byte Out-of-Band Recovery Signature
    const uint8_t secure_key[6] = {0xAA, 0x55, 0xDE, 0xAD, 0xBE, 0xEF};
    
    // Evaluate if the ring buffer contains enough data to check for the key window
    while (((head - tail + BUFFER_SIZE) % BUFFER_SIZE) >= 6) {
        bool key_matched = true;
        
        // Inspect the ring buffer space sequentially to match against the signature token
        for (uint8_t i = 0; i < 6; i++) {
            uint8_t buffer_index = (tail + i) % BUFFER_SIZE;
            if (ringBuffer[buffer_index] != secure_key[i]) {
                key_matched = false;
                break; // Break loop instantly on first character index failure
            }
        }
        
        if (key_matched) {
            // MATCH FOUND: Clear the lockdown state programmatically!
            currentSystemState = SYSTEM_NOMINAL;
            
            // Flush out the 6 key bytes from our tracking counters
            tail = (tail + 6) % BUFFER_SIZE;
            
            // Reset our security metrics register logs
            cli();
            lastValidPacketTime = timer_millis; // Latch fresh time baseline
            sei();
            return;
        } else {
            // MISMATCH OR FUZZING FLOOD: Discard a single byte to slide the validation matrix down
            // This zero-allocation flush ensures bytes never pool or overflow the stack perimeters.
            tail = (tail + 1) % BUFFER_SIZE;
        }
    }
}

void transmit_uart_string(const char* str) {
    while (*str) {
        while (!(UCSR0A & (1 << UDRE0))); // Wait for empty transmit buffer register flag
        UDR0 = *str++;                     // Drop character byte onto the copper transmit line
    }
}

int main(void) {
    init_avr_registers();
    currentSystemState = SYSTEM_NOMINAL;
    
    // Infinite real-time deterministic execution processing loop
    while (1) {
        // 1. Process and evaluate incoming frames in ring buffer
        process_buffered_frames();
        
        // 2. Run asynchronous tracking health gate checks
        verify_watchdog_interlock();
    }
    
    return 0; // Standard compiler mapping (Never reached on bare metal)
}