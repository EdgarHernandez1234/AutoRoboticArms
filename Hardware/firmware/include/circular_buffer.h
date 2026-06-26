#ifndef CIRCULAR_BUFFER_H
#define CIRCULAR_BUFFER_H

#include <stdint.h>
#include <stdbool.h>

// CAPACITY ANCHOR: Must be a power of 2 (16, 32, 64, 128) for bitwise masking
#define BUFFER_SIZE 64
#define BUFFER_MASK (BUFFER_SIZE - 1)

class CircularBuffer {
private:
    uint8_t buffer[BUFFER_SIZE];
    
    // VOLATILE: Explicitly tells the compiler these will be changed by hardware interrupts
    volatile uint8_t head;
    volatile uint8_t tail;
    volatile uint8_t count;

public:
    // 1. HARDWARE INIT: Resets the tracking pointers to zero torque
    void init() {
        head = 0;
        tail = 0;
        count = 0;
    }

    // 2. INGRESS PIPELINE: Pushes new bytes from the USB Serial ISR into the ring
    bool enqueue(uint8_t data) {
        if (count >= BUFFER_SIZE) {
            return false; // INTERLOCK: Fails safely to prevent buffer overflow/SRAM corruption
        }
        buffer[head] = data;
        
        // BITWISE WRAP: Extremely fast cycle calculation replacing the heavy modulo (%) operator
        head = (head + 1) & BUFFER_MASK; 
        count++;
        
        return true;
    }

    // 3. EGRESS PIPELINE: Extracts bytes for the parser loop
    bool dequeue(uint8_t &data) {
        if (count == 0) {
            return false; // INTERLOCK: Fails safely if the buffer is empty
        }
        data = buffer[tail];
        
        // BITWISE WRAP
        tail = (tail + 1) & BUFFER_MASK; 
        count--;
        
        return true;
    }

    // 4. FAST STATE GUARD: Used by the interrupt gates to check capacity
    bool is_full() const {
        return (count >= BUFFER_SIZE);
    }

    // 5. DIAGNOSTICS: Exposes current payload volume to the watchdog logic
    uint8_t get_count() const {
        return count;
    }
};

#endif // CIRCULAR_BUFFER_H