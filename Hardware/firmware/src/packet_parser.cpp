#include "../include/packet_parser.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

void packet_parser_init(PacketParser* parser) {
    if (!parser) return;
    parser->payload_index = 0;
    parser->checksum_index = 0;
    parser->state = STATE_WAIT_FOR_START;
    parser->payload_buffer[0] = '\0';
    parser->checksum_buffer[0] = '\0';
    
    for (int i = 0; i < MAX_ROBOTIC_JOINTS; i++) {
        parser->parsed_angles[i] = 90; // Default midpoint
    }
}

static uint8_t hex_char_to_nibble(char c) {
    if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
    if (c >= 'A' && c <= 'F') return (uint8_t)(c - 'A' + 10);
    if (c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
    return 0xFF;
}

static bool extract_and_clamp_angles(PacketParser* parser) {
    // Expected format: DRV,<j0>,<j1>,<j2>
    char* token = strtok(parser->payload_buffer, ",");
    if (!token || strcmp(token, "DRV") != 0) {
        return false;
    }

    for (int i = 0; i < MAX_ROBOTIC_JOINTS; i++) {
        token = strtok(NULL, ",");
        if (!token) return false; // Missing joint argument

        int angle_val = atoi(token);
        
        // BVA Clamping Protection [0, 180]
        if (angle_val < 0) angle_val = 0;
        if (angle_val > 180) angle_val = 180;

        parser->parsed_angles[i] = (uint8_t)angle_val;
    }

    return true;
}

ParseStatus packet_parser_process_byte(PacketParser* parser, uint8_t byte) {
    if (!parser) return PARSE_ERROR_FORMAT;

    char c = (char)byte;

    switch (parser->state) {
        case STATE_WAIT_FOR_START:
            if (c == '@') {
                parser->payload_index = 0;
                parser->checksum_index = 0;
                parser->payload_buffer[0] = '\0';
                parser->checksum_buffer[0] = '\0';
                parser->state = STATE_ACCUMULATE_PAYLOAD;
            }
            return PARSE_IN_PROGRESS;

        case STATE_ACCUMULATE_PAYLOAD:
            if (c == '*') {
                parser->payload_buffer[parser->payload_index] = '\0';
                parser->checksum_index = 0;
                parser->state = STATE_WAIT_FOR_CHECKSUM;
                return PARSE_IN_PROGRESS;
            }
            if (c == '\n' || c == '@') {
                // Malformed packet reset
                parser->state = (c == '@') ? STATE_ACCUMULATE_PAYLOAD : STATE_WAIT_FOR_START;
                parser->payload_index = 0;
                return PARSE_ERROR_FORMAT;
            }
            if (parser->payload_index < (MAX_PACKET_LENGTH - 1)) {
                parser->payload_buffer[parser->payload_index++] = c;
                return PARSE_IN_PROGRESS;
            } else {
                // Buffer overflow protection
                parser->state = STATE_WAIT_FOR_START;
                return PARSE_ERROR_FORMAT;
            }

        case STATE_WAIT_FOR_CHECKSUM:
            parser->checksum_buffer[parser->checksum_index++] = c;
            if (parser->checksum_index >= 2) {
                parser->checksum_buffer[2] = '\0';
                parser->state = STATE_WAIT_FOR_NEWLINE;
            }
            return PARSE_IN_PROGRESS;

        case STATE_WAIT_FOR_NEWLINE:
            if (c == '\n') {
                parser->state = STATE_WAIT_FOR_START;

                // 1. Calculate running XOR checksum
                uint8_t calculated_cs = 0;
                for (uint8_t i = 0; i < parser->payload_index; i++) {
                    calculated_cs ^= (uint8_t)parser->payload_buffer[i];
                }

                // 2. Decode expected hex checksum
                uint8_t high_nibble = hex_char_to_nibble(parser->checksum_buffer[0]);
                uint8_t low_nibble  = hex_char_to_nibble(parser->checksum_buffer[1]);
                if (high_nibble == 0xFF || low_nibble == 0xFF) {
                    return PARSE_ERROR_CHECKSUM;
                }
                uint8_t expected_cs = (uint8_t)((high_nibble << 4) | low_nibble);

                // 3. Verify parity
                if (calculated_cs != expected_cs) {
                    return PARSE_ERROR_CHECKSUM;
                }

                // 4. Tokenize arguments into parsed_angles
                if (!extract_and_clamp_angles(parser)) {
                    return PARSE_ERROR_FORMAT;
                }

                return PARSE_SUCCESS;
            } else {
                parser->state = STATE_WAIT_FOR_START;
                return PARSE_ERROR_FORMAT;
            }

        default:
            parser->state = STATE_WAIT_FOR_START;
            return PARSE_ERROR_FORMAT;
    }
}