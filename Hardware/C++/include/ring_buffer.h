#ifndef RING_BUFFER_H
#define RING_BUFFER_H

#include <stdint.h>
#include <avr/io.h>

#define BUFFER_SIZE 32
#define SYNC_1 0x55
#define SYNC_2 0xAA

// System States Lifecycle Enumeration
enum SystemState {
    SYSTEM_INIT,
    SYSTEM_NOMINAL,
    SYSTEM_FAULT_TIMEOUT,
    SYSTEM_FAULT_CHECKSUM
};

// Explicitly expose global registers to compilation units
extern volatile uint8_t ringBuffer[BUFFER_SIZE];
extern volatile uint8_t head;
extern volatile uint8_t tail;
extern SystemState currentSystemState;
extern unsigned long lastValidPacketTime;

// Core Function Prototypes
void push_serial_byte(uint8_t incomingByte);
void process_buffered_frames();
void parse_incoming_frame_window();
void handle_system_fault(SystemState faultType);

#endif // RING_BUFFER_H