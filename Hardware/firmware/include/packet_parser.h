#ifndef PACKET_PARSER_H
#define PACKET_PARSER_H

#include <stdint.h>
#include <stdbool.h>
#include "./circular_buffer.h"

// ⚡ Protocol ICD Constraints
#define MAX_PAYLOAD_LEN 24 // Max ASCII characters between '@' and '*'
#define MAX_JOINTS      4  // Supported kinematic servo channels per command

// 🎛️ FSM States
typedef enum {
    STATE_WAIT_FOR_START = 0, // Idling, scanning for '@' header token
    STATE_ACCUMULATE_PAYLOAD, // Stash payload chars & calculate rolling XOR checksum
    STATE_READ_CHECKSUM,      // Read 2 ASCII Hex checksum characters following '*'
    STATE_VALIDATE_EXECUTE    // Checksum parity match and in-place tokenization
} ParseState;

// 🚦 Process Status Return Codes
typedef enum {
    PARSE_BUSY = 0,          // Frame in progress, waiting for more bytes
    PARSE_SUCCESS_FRAME,     // Valid frame decoded and checksum verified
    PARSE_ERROR_CHECKSUM,    // Frame complete, but XOR checksum mismatched
    PARSE_ERROR_OVERFLOW,    // Payload exceeded MAX_PAYLOAD_LEN before '*'
    PARSE_ERROR_FORMAT       // Invalid ASCII hex character in checksum tail
} ParseResult;

// Decoded Command Data Transfer Container
typedef struct {
    char command[8];             // e.g., "DRV"
    uint8_t angles[MAX_JOINTS];  // Parsed servo angles (0 - 180 deg)
    uint8_t angle_count;         // Number of valid joint angles parsed
    bool valid;                  // True if checksum and formatting passed
} ParsedCommand;

// Stateful Parser Memory Layout
typedef struct {
    ParseState state;                  // Current FSM state
    char payload_buf[MAX_PAYLOAD_LEN + 1]; // Local static payload buffer
    uint8_t payload_idx;               // Write pointer for payload buffer
    uint8_t calculated_checksum;       // Rolling bitwise XOR parity accumulator
    char checksum_hex[3];              // Storage for 2 ASCII Hex characters + null
    uint8_t checksum_idx;              // Index tracker for hex tail read
    
    // Diagnostic Metrics
    uint16_t valid_packets;            // Successfully parsed frames counter
    uint16_t corrupted_packets;        // Dropped frames counter (checksum fail)
    uint16_t overflow_packets;         // Dropped frames counter (length overrun)
} PacketParser;

// Public API Surface
void packet_parser_init(PacketParser* parser);
void packet_parser_reset(PacketParser* parser);
ParseResult packet_parser_process_byte(PacketParser* parser, uint8_t byte, ParsedCommand* out_cmd);
ParseResult packet_parser_process_buffer(PacketParser* parser, CircularBuffer* cb, ParsedCommand* out_cmd);

#endif // PACKET_PARSER_H