#include "../include/packet_parser.h"
#include <string.h>
#include <stdlib.h>

/**
 * @brief Converts a single ASCII character to a 4-bit nibble value (0-15).
 * @return 0x0 to 0x0F on success, 0xFF if character is invalid ASCII hex.
 */
static uint8_t hex_char_to_nibble(char c) {
    if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
    if (c >= 'A' && c <= 'F') return (uint8_t)(c - 'A' + 10);
    if (c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
    return 0xFF; // Invalid Hex Character Guard
}

/**
 * @brief Decodes two ASCII hex characters into a 1-byte integer.
 */
static bool decode_hex_pair(char high_char, char low_char, uint8_t* result_ptr) {
    if (result_ptr == NULL) return false;

    uint8_t high_nibble = hex_char_to_nibble(high_char);
    uint8_t low_nibble  = hex_char_to_nibble(low_char);

    if (high_nibble == 0xFF || low_nibble == 0xFF) {
        return false; // Non-hex character detected
    }

    *result_ptr = (high_nibble << 4) | low_nibble;
    return true;
}

/**
 * @brief Initializes parser state variables and resets diagnostic counters.
 */
void packet_parser_init(PacketParser* parser) {
    if (parser == NULL) return;
    parser->valid_packets = 0;
    parser->corrupted_packets = 0;
    parser->overflow_packets = 0;
    packet_parser_reset(parser);
}

/**
 * @brief Resets inner state machine variables without wiping cumulative stats.
 */
void packet_parser_reset(PacketParser* parser) {
    if (parser == NULL) return;
    parser->state = STATE_WAIT_FOR_START;
    parser->payload_idx = 0;
    parser->calculated_checksum = 0;
    parser->checksum_idx = 0;
    memset(parser->payload_buf, 0, sizeof(parser->payload_buf));
    memset(parser->checksum_hex, 0, sizeof(parser->checksum_hex));
}

/**
 * @brief Evaluates a single byte through the Protocol State Machine.
 */
ParseResult packet_parser_process_byte(PacketParser* parser, uint8_t byte, ParsedCommand* out_cmd) {
    if (parser == NULL) return PARSE_ERROR_FORMAT;

    char ch = (char)byte;

    // Edge Case 1 Guard: Mid-Stream Frame Re-Synchronization
    // If an unexpected '@' arrives while in the middle of a frame, reset and restart immediately
    if (ch == '@' && parser->state != STATE_WAIT_FOR_START) {
        packet_parser_reset(parser);
        parser->state = STATE_ACCUMULATE_PAYLOAD;
        return PARSE_BUSY;
    }

    switch (parser->state) {
        case STATE_WAIT_FOR_START:
            if (ch == '@') {
                packet_parser_reset(parser);
                parser->state = STATE_ACCUMULATE_PAYLOAD;
            }
            return PARSE_BUSY;

        case STATE_ACCUMULATE_PAYLOAD:
            if (ch == '*') {
                // Delimiter reached; null-terminate payload buffer
                parser->payload_buf[parser->payload_idx] = '\0';
                parser->state = STATE_READ_CHECKSUM;
                return PARSE_BUSY;
            }

            // Edge Case 2 Guard: Payload Buffer Overflow
            if (parser->payload_idx >= MAX_PAYLOAD_LEN) {
                parser->overflow_packets++;
                packet_parser_reset(parser);
                return PARSE_ERROR_OVERFLOW;
            }

            // Stash byte and update rolling XOR checksum
            parser->payload_buf[parser->payload_idx++] = ch;
            parser->calculated_checksum ^= (uint8_t)ch;
            return PARSE_BUSY;

        case STATE_READ_CHECKSUM:
            if (ch == '\n' || ch == '\r') {
                if (parser->checksum_idx < 2) {
                    // Truncated checksum tail
                    parser->corrupted_packets++;
                    packet_parser_reset(parser);
                    return PARSE_ERROR_FORMAT;
                }
                
                parser->state = STATE_VALIDATE_EXECUTE;
                break; // Fall through to validation block
            }

            if (parser->checksum_idx < 2) {
                parser->checksum_hex[parser->checksum_idx++] = ch;
                return PARSE_BUSY;
            }
            return PARSE_BUSY;

        default:
            packet_parser_reset(parser);
            return PARSE_ERROR_FORMAT;
    }

    // ------------------------------------------------------------------------
    // STATE_VALIDATE_EXECUTE Logic
    // ------------------------------------------------------------------------
    if (parser->state == STATE_VALIDATE_EXECUTE) {
        // Safety Initialization: Zero out output container so valid is false by default
        if (out_cmd != NULL) {
            memset(out_cmd, 0, sizeof(ParsedCommand));
        }
        
        uint8_t received_checksum = 0;

        // Edge Case 3 Guard: Invalid ASCII Hex Characters
        if (!decode_hex_pair(parser->checksum_hex[0], parser->checksum_hex[1], &received_checksum)) {
            parser->corrupted_packets++;
            packet_parser_reset(parser);
            return PARSE_ERROR_FORMAT;
        }

        // Parity Verification
        if (parser->calculated_checksum != received_checksum) {
            parser->corrupted_packets++;
            packet_parser_reset(parser);
            return PARSE_ERROR_CHECKSUM;
        }

        // ⚡ Checksum Verified! Execute In-Place Zero-Copy Tokenization
        if (out_cmd != NULL) {
            memset(out_cmd, 0, sizeof(ParsedCommand));

            // Token 1: Command Opcode (e.g., "DRV")
            char* token = strtok(parser->payload_buf, ",");
            if (token != NULL) {
                strncpy(out_cmd->command, token, sizeof(out_cmd->command) - 1);

                // Tokens 2+: Servo Joint Angles
                while ((token = strtok(NULL, ",")) != NULL && out_cmd->angle_count < MAX_JOINTS) {
                    int val = atoi(token);
                    // Angle Clamping Guard: Enforce 0 <= angle <= 180
                    if (val < 0) val = 0;
                    if (val > 180) val = 180;
                    out_cmd->angles[out_cmd->angle_count++] = (uint8_t)val;
                }
                out_cmd->valid = true;
            }
        }

        parser->valid_packets++;
        packet_parser_reset(parser);
        return PARSE_SUCCESS_FRAME;
    }

    packet_parser_reset(parser);
    return PARSE_ERROR_FORMAT;
}

/**
 * @brief Helper function: Drains waiting bytes from RingBuffer through the state machine.
 * @return PARSE_SUCCESS_FRAME if a full packet was parsed during this loop pass,
 * otherwise returns status of last processed byte or PARSE_BUSY.
 */
ParseResult packet_parser_process_buffer(PacketParser* parser, CircularBuffer* cb, ParsedCommand* out_cmd) {
    if (parser == NULL || cb == NULL) return PARSE_ERROR_FORMAT;

    uint8_t byte = 0;
    ParseResult last_result = PARSE_BUSY;

    while (circular_buffer_dequeue(cb, &byte)) {
        ParseResult res = packet_parser_process_byte(parser, byte, out_cmd);
        if (res == PARSE_SUCCESS_FRAME) {
            return PARSE_SUCCESS_FRAME; // Packet fully validated! Hand off to kinematic driver
        }
        if (res != PARSE_BUSY) {
            last_result = res; // Save error state (PARSE_ERROR_CHECKSUM, OVERFLOW, FORMAT)
        }
    }
    return last_result;
}