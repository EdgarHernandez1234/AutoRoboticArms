#include "ring_buffer.h"

// Initialize state-space registers
volatile uint8_t ringBuffer[BUFFER_SIZE];
volatile uint8_t head = 0;
volatile uint8_t tail = 0;

// Pre-computed CRC8 CCITT Industrial Lookup Table (LUT)
static const uint8_t crc8_table[256] = {
    0x00, 0x07, 0x0E, 0x09, 0x1C, 0x1B, 0x12, 0x15, 0x38, 0x3F, 0x36, 0x31, 0x24, 0x23, 0x2A, 0x2D,
    0x70, 0x77, 0x7E, 0x79, 0x6C, 0x6B, 0x62, 0x65, 0x48, 0x4F, 0x46, 0x41, 0x54, 0x53, 0x5A, 0x5D,
    0xE0, 0xE7, 0xEE, 0xE9, 0xFC, 0xFB, 0xF2, 0xF5, 0xD8, 0xDF, 0xD6, 0xD1, 0xC4, 0xC3, 0xCA, 0xCD,
    0x90, 0x97, 0x9E, 0x99, 0x8C, 0x8B, 0x82, 0x85, 0xA8, 0xAF, 0xA6, 0xA1, 0xB4, 0xB3, 0xBA, 0xBD,
    0xC7, 0xC0, 0xC9, 0xCE, 0xDB, 0xDC, 0xD5, 0xD2, 0xFF, 0xF8, 0xF1, 0xF6, 0xE3, 0xE4, 0xED, 0xEA,
    0xB7, 0xB0, 0xB9, 0xBE, 0xAB, 0xAC, 0xA5, 0xA2, 0x8F, 0x88, 0x81, 0x86, 0x93, 0x94, 0x9D, 0x9A,
    0x27, 0x20, 0x29, 0x2E, 0x3B, 0x3C, 0x35, 0x32, 0x1F, 0x18, 0x11, 0x16, 0x03, 0x04, 0x0D, 0x0A,
    0x57, 0x50, 0x59, 0x5E, 0x4B, 0x4C, 0x45, 0x42, 0x6F, 0x68, 0x61, 0x66, 0x73, 0x74, 0x7D, 0x7A,
    0x89, 0x8E, 0x87, 0x80, 0x95, 0x92, 0x9B, 0x9C, 0xB1, 0xB6, 0xBF, 0xB8, 0xAD, 0xAA, 0xA3, 0xA4,
    0xF9, 0xFE, 0xF7, 0xF0, 0xE5, 0xE2, 0xEB, 0xEC, 0xC1, 0xC6, 0xCF, 0xC8, 0xDD, 0xDA, 0xD3, 0xD4,
    0x69, 0x6E, 0x67, 0x60, 0x75, 0x72, 0x7B, 0x7C, 0x51, 0x56, 0x5F, 0x58, 0x4D, 0x4A, 0x43, 0x44,
    0x19, 0x1E, 0x17, 0x10, 0x05, 0x02, 0x0B, 0x0C, 0x21, 0x26, 0x2F, 0x28, 0x3D, 0x3A, 0x33, 0x34,
    0x4E, 0x49, 0x40, 0x47, 0x52, 0x55, 0x5C, 0x5B, 0x76, 0x71, 0x78, 0x7F, 0x6A, 0x6D, 0x64, 0x63,
    0x3E, 0x39, 0x30, 0x37, 0x22, 0x25, 0x2C, 0x2B, 0x06, 0x01, 0x08, 0x0F, 0x1A, 0x1D, 0x14, 0x13,
    0xAE, 0xA9, 0xA0, 0xA7, 0xB2, 0xB5, 0xBC, 0xBB, 0x96, 0x91, 0x98, 0x9F, 0x8A, 0x8D, 0x84, 0x83,
    0xDE, 0xD9, 0xD0, 0xD7, 0xC2, 0xC5, 0xCC, 0xCB, 0xE6, 0xE1, 0xE8, 0xEF, 0xFA, 0xFD, 0xF4, 0xF3
};
void push_serial_byte(uint8_t incomingByte) {
    uint8_t nextHead = (head + 1) % BUFFER_SIZE;
    
    // Defensive Boundary Gate: Prevent buffer overflow if tail gets blocked
    if (nextHead != tail) {
        ringBuffer[head] = incomingByte;
        head = nextHead;
    } else {
        handle_system_fault(SYSTEM_FAULT_TIMEOUT);
    }
}

void process_buffered_frames() {
    // A valid packed binary movement command contract is exactly 6 bytes long
    while (((head - tail + BUFFER_SIZE) % BUFFER_SIZE) >= 6) {
        
        // Peek at the first byte in the queue without advancing the tail index yet
        uint8_t potentialSync1 = ringBuffer[tail];
        
        if (potentialSync1 == SYNC_1) {
            // Peek at the adjacent step position index via modular arithmetic
            uint8_t potentialSync2 = ringBuffer[(tail + 1) % BUFFER_SIZE];
            
            if (potentialSync2 == SYNC_2) {
                // SUCCESS: Back-to-back sync header verified! Safe to parse full window.
                parse_incoming_frame_window();
                return;
            } else {
                // CORRUPTION TRIGGERED: SYNC_1 was a false positive byte mismatch.
                // Advance tail pointer by 1 to flush the bad 0x55 byte.
                // Shift parsing evaluation window down to realign seamlessly.
                tail = (tail + 1) % BUFFER_SIZE;
                handle_system_fault(SYSTEM_FAULT_CHECKSUM);
            }
        } else {
            // Not a sync character. Discard byte and advance window index pointer.
            tail = (tail + 1) % BUFFER_SIZE;
        }
    }
}

void parse_incoming_frame_window() {
    uint8_t running_crc = 0;
    for (uint8_t i = 0; i < 5; i++) {
        running_crc = crc8_table[running_crc ^ ringBuffer[(tail + i) % BUFFER_SIZE]];
    }
    
    uint8_t packet_checksum = ringBuffer[(tail + 5) % BUFFER_SIZE];
    
    if (running_crc == packet_checksum) {
        // 1. Natively extract verified motor parameter primitives
        uint8_t base_target  = ringBuffer[(tail + 2) % BUFFER_SIZE];
        uint8_t shldr_target = ringBuffer[(tail + 3) % BUFFER_SIZE];
        uint8_t elbow_target = ringBuffer[(tail + 4) % BUFFER_SIZE];
        
        // (In Sprint 8, these targets will map to physical PCA9685 I2C register duty cycles)
        (void)base_target; (void)shldr_target; (void)elbow_target; 

        // 2. Latch time-stamp ledger for the 300ms watchdog interlock loop
        cli();
        lastValidPacketTime = timer_millis;
        sei();
        
        // 3. Clear all 6 bytes of the processed frame from the queue bounds
        tail = (tail + 6) % BUFFER_SIZE;

        // 4. 🔄 BI-DIRECTIONAL ACKNOWLEDGEMENT TRIGGER
        // Forcefully drop the ASCII 'K' character byte onto the copper Tx track lines.
        // This signals to Option B that the buffer is clear and ready for the next frame.
#ifndef TESTING_ON_HOST
        while (!(UCSR0A & (1 << UDRE0))); // Wait for empty hardware transmit buffer flag
        UDR0 = 'K';                       // Spill token onto the physical wire
#endif
    } else {
        handle_system_fault(SYSTEM_FAULT_CHECKSUM);
        tail = (tail + 1) % BUFFER_SIZE;
    }
}

void verify_isolated_recovery_handshake() {
    // Our secure 6-byte Out-of-Band Recovery Signature
    const uint8_t secure_key[6] = {0xAA, 0x55, 0xDE, 0xAD, 0xBE, 0xEF};
    // Evaluate if the ring buffer contains enough data to check for the key window
    while (((head - tail + BUFFER_SIZE) % BUFFER_SIZE) >= 6) {
        bool key_matched = true;
        for (uint8_t i = 0; i < 6; i++) {
            if (ringBuffer[(tail + i) % BUFFER_SIZE] != secure_key[i]) {
                key_matched = false;
                break;
            }
        }
        if (key_matched) {
            currentSystemState = SYSTEM_NOMINAL;
            tail = (tail + 6) % BUFFER_SIZE;
            cli();
            lastValidPacketTime = timer_millis;
            sei();
            return;
        } else {
            tail = (tail + 1) % BUFFER_SIZE;
        }
    }
}