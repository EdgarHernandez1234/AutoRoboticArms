#ifndef CIRCULAR_BUFFER_H
#define CIRCULAR_BUFFER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BUFFER_SIZE 32
#define BUFFER_MASK (BUFFER_SIZE - 1) // 0x1F (31) for single-cycle bitwise wrapping

typedef struct {
    uint8_t buffer[BUFFER_SIZE];
    volatile uint8_t head;
    volatile uint8_t tail;
} CircularBuffer;

/**
 * @brief Initializes or clears the circular ring buffer.
 */
void circular_buffer_init(CircularBuffer* cb);

/**
 * @brief Pushes a single byte into the ring buffer (e.g. from UART ISR).
 * @param cb Pointer to CircularBuffer instance.
 * @param data Byte to write.
 * @return true if written successfully, false if buffer was full (overflow).
 */
bool circular_buffer_write(CircularBuffer* cb, uint8_t data);

/**
 * @brief Pops/reads a single byte from the ring buffer.
 * @param cb Pointer to CircularBuffer instance.
 * @param data Pointer to store the extracted byte.
 * @return true if a byte was read, false if the buffer was empty.
 */
bool circular_buffer_read(CircularBuffer* cb, uint8_t* data);

/**
 * @brief Returns true if the buffer has no readable data.
 */
bool circular_buffer_is_empty(const CircularBuffer* cb);

/**
 * @brief Returns true if the buffer cannot accept more data.
 */
bool circular_buffer_is_full(const CircularBuffer* cb);

/**
 * @brief Returns the number of unread bytes in the buffer.
 */
uint8_t circular_buffer_available(const CircularBuffer* cb);

#ifdef __cplusplus
}
#endif

#endif // CIRCULAR_BUFFER_H