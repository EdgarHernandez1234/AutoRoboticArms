#ifndef PACKET_PARSER_H
#define PACKET_PARSER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_PACKET_LENGTH   32
#define MAX_ROBOTIC_JOINTS  3

typedef enum {
    PARSE_IN_PROGRESS,
    PARSE_SUCCESS,
    PARSE_ERROR_FORMAT,
    PARSE_ERROR_CHECKSUM
} ParseStatus;

typedef enum {
    STATE_WAIT_FOR_START,       // Waiting for '@' marker
    STATE_ACCUMULATE_PAYLOAD,   // Reading payload bytes until '*'
    STATE_WAIT_FOR_CHECKSUM,    // Reading 2 hex checksum characters
    STATE_WAIT_FOR_NEWLINE      // Waiting for '\n' terminator
} ParserFSMState;

typedef struct {
    char           payload_buffer[MAX_PACKET_LENGTH];
    uint8_t        payload_index;
    char           checksum_buffer[3];
    uint8_t        checksum_index;
    ParserFSMState state;
    uint8_t        parsed_angles[MAX_ROBOTIC_JOINTS];
} PacketParser;

/**
 * @brief Initializes or resets the parser state machine.
 */
void packet_parser_init(PacketParser* parser);

/**
 * @brief Ingests exactly 1 raw ASCII byte into the parser FSM.
 * @param parser Pointer to the PacketParser instance.
 * @param byte Incoming character from RingBuffer / UART.
 * @return ParseStatus reflecting the outcome of processing this byte.
 */
ParseStatus packet_parser_process_byte(PacketParser* parser, uint8_t byte);

#ifdef __cplusplus
}
#endif

#endif // PACKET_PARSER_H