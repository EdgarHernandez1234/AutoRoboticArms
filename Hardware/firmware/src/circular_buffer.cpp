#include "../include/circular_buffer.h"
#include <string.h>

/**
 * @brief Zeroes out the ring buffer memory and resets write/read pointers to zero.
 */
void circular_buffer_init(CircularBuffer* rb) {
    if (rb == NULL) return;
    rb->head = 0;
    rb->tail = 0;
    memset((void*)rb->buffer, 0, sizeof(rb->buffer));
}

/**
 * @brief Enqueues a byte into the buffer (Producer/ISR side).
 * @return true if successfully written, false if buffer is FULL (byte dropped safely).
 */
bool circular_buffer_enqueue(CircularBuffer* rb, uint8_t byte) {
    if (rb == NULL) return false;

    // Compute hypothetical next write index using single-cycle bitwise mask
    uint8_t next_head = (rb->head + 1) & CIRCULAR_BUFFER_MASK;

    // Full-Boundary Invariant: Never allow head to collide with tail from behind
    if (next_head == rb->tail) {
        return false; // Buffer full (31 usable bytes reached); drop byte to prevent corruption
    }

    rb->buffer[rb->head] = byte;
    rb->head = next_head; // Atomic 8-bit pointer write on AVR
    return true;
}

/**
 * @brief Dequeues a byte from the buffer (Consumer/Main Loop side).
 * @return true if byte was retrieved, false if buffer is EMPTY.
 */
bool circular_buffer_dequeue(CircularBuffer* rb, uint8_t* byte_ptr) {
    if (rb == NULL || byte_ptr == NULL) return false;

    // 🛡️ Empty-Boundary Check
    if (rb->head == rb->tail) {
        return false; // Buffer empty; nothing to read
    }

    *byte_ptr = rb->buffer[rb->tail];
    rb->tail = (rb->tail + 1) & CIRCULAR_BUFFER_MASK; // Atomic 8-bit pointer write on AVR
    return true;
}

/**
 * @brief Calculates unread bytes waiting in the buffer.
 * Uses branchless Two's Complement subtraction with 0x1F bitwise masking.
 */
uint8_t circular_buffer_available(const CircularBuffer* rb) {
    if (rb == NULL) return 0;
    return (rb->head - rb->tail) & CIRCULAR_BUFFER_MASK;
}

/**
 * @brief Returns true if buffer reached its 31-byte sentinel capacity limit.
 */
bool circular_buffer_is_full(const CircularBuffer* rb) {
    if (rb == NULL) return false;
    return ((rb->head + 1) & CIRCULAR_BUFFER_MASK) == rb->tail;
}

/**
 * @brief Returns true if head == tail.
 */
bool circular_buffer_is_empty(const CircularBuffer* rb) {
    if (rb == NULL) return true;
    return rb->head == rb->tail;
}