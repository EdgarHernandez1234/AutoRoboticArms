#ifndef CIRCULAR_BUFFER_H
#define CIRCULAR_BUFFER_H

#include <stdint.h>
#include <stdbool.h>

// ⚡ Hardware Capacity Constants
#define CIRCULAR_BUFFER_CAPACITY 32
#define CIRCULAR_BUFFER_MASK     (CIRCULAR_BUFFER_CAPACITY - 1) // 0x1F (31 in decimal)

// Lock-Free Single-Producer Single-Consumer (SPSC) Ring Buffer Struct
typedef struct {
    uint8_t buffer[CIRCULAR_BUFFER_CAPACITY]; // 32-byte static memory array
    volatile uint8_t head;               // Write pointer (Updated by ISR/Producer)
    volatile uint8_t tail;               // Read pointer (Updated by Main Loop/Consumer)
} CircularBuffer;

// Public API Surface
void circular_buffer_init(CircularBuffer* rb);
bool circular_buffer_enqueue(CircularBuffer* rb, uint8_t byte);
bool circular_buffer_dequeue(CircularBuffer* rb, uint8_t* byte_ptr);
uint8_t circular_buffer_available(const CircularBuffer* rb);
bool circular_buffer_is_full(const CircularBuffer* rb);
bool circular_buffer_is_empty(const CircularBuffer* rb);

#endif // CIRCULAR_BUFFER_H