#include "../include/circular_buffer.h"

void circular_buffer_init(CircularBuffer* cb) {
    if (!cb) return;
    cb->head = 0;
    cb->tail = 0;
}

bool circular_buffer_write(CircularBuffer* cb, uint8_t data) {
    if (!cb) return false;

    uint8_t next_head = (cb->head + 1) & BUFFER_MASK;

    // If next_head hits tail, the buffer is full (reserves 1 slot to distinguish empty vs full)
    if (next_head == cb->tail) {
        return false; // Buffer overflow dropped
    }

    cb->buffer[cb->head] = data;
    cb->head = next_head;
    return true;
}

bool circular_buffer_read(CircularBuffer* cb, uint8_t* data) {
    if (!cb || !data) return false;

    // If head == tail, buffer is empty
    if (cb->head == cb->tail) {
        return false;
    }

    *data = cb->buffer[cb->tail];
    cb->tail = (cb->tail + 1) & BUFFER_MASK;
    return true;
}

bool circular_buffer_is_empty(const CircularBuffer* cb) {
    if (!cb) return true;
    return (cb->head == cb->tail);
}

bool circular_buffer_is_full(const CircularBuffer* cb) {
    if (!cb) return false;
    return (((cb->head + 1) & BUFFER_MASK) == cb->tail);
}

uint8_t circular_buffer_available(const CircularBuffer* cb) {
    if (!cb) return 0;
    return (cb->head - cb->tail) & BUFFER_MASK;
}