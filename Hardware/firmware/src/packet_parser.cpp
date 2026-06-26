#include "../include/packet_parser.h"
#include <string.h>
#include <stdlib.h>

/**
 * COMPUTE PARITY CHECKSUM
 * Computes sequential bitwise XOR over the raw ASCII payload characters,
 * confirming data integrity before any servo mechanical shifts occur.
 */
bool validate_packet_integrity(const char* payload, const char* expected_checksum_hex) {
    uint8_t calculated_xor = 0;
    size_t length = strlen(payload);

    // Loop through the payload and apply sequential bitwise XOR masks
    for (size_t i = 0; i < length; ++i) {
        calculated_xor ^= (uint8_t)payload[i];
    }

    // Convert the computed uint8_t byte into 2 uppercase ASCII hex characters
    char calculated_hex[3];
    char const hex_conversion_table[] = "0123456789ABCDEF";
    calculated_hex[0] = hex_conversion_table[(calculated_xor >> 4) & 0x0F];
    calculated_hex[1] = hex_conversion_table[calculated_xor & 0x0F];
    calculated_hex[2] = '\0';

    // Verify string parity against the trailing host tracking token
    return (strcmp(calculated_hex, expected_checksum_hex) == 0);
}

/**
 * STRTOK ZERO-COPY PARSING ROUTINE
 * Safely slices strings using standard delimiters without allocating heap space.
 * Target packet format: "DRV,servo_id,angle"
 */
bool extract_kinematic_payload(char* payload, uint8_t &out_servo_id, int16_t &out_angle) {
    // Token 1: Identify prefix identifier flag
    char* token = strtok(payload, ",");
    if (token == NULL || strcmp(token, "DRV") != 0) {
        return false; // Error: Corrupted or mismatched instruction prefix
    }

    // Token 2: Extract Target Servo Identifier Channel
    token = strtok(NULL, ",");
    if (token == NULL) return false;
    out_servo_id = (uint8_t)atoi(token);

    // Token 3: Extract Target Actuator Degree Parameter
    token = strtok(NULL, ",");
    if (token == NULL) return false;
    out_angle = (int16_t)atoi(token);

    return true; // Execution parameter validated successfully
}