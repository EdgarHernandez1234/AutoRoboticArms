#include "../include/packet_parser.h"
#include "../include/circular_buffer.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

/**
 * @brief Helper function to push an entire string into the CircularBuffer.
 */
static void push_string_to_buffer(CircularBuffer* cb, const char* str) {
    size_t len = strlen(str);
    for (size_t i = 0; i < len; i++) {
        bool ok = circular_buffer_write(cb, (uint8_t)str[i]);
        assert(ok == true);
    }
}

/**
 * @brief Helper function to drain the circular buffer through the byte-by-byte parser.
 * @return Final ParseStatus of the last processed byte.
 */
static ParseStatus feed_buffer_to_parser(PacketParser* parser, CircularBuffer* cb) {
    uint8_t byte_in;
    ParseStatus last_status = PARSE_IN_PROGRESS;
    while (circular_buffer_read(cb, &byte_in)) {
        last_status = packet_parser_process_byte(parser, byte_in);
    }
    return last_status;
}

void run_packet_parser_tests(void) {
    printf("[STAGING]: Initializing Non-Blocking Packet Parser Unit Test Suite...\n");

    CircularBuffer cb;
    PacketParser parser;

    // ------------------------------------------------------------------------
    // TEST 1: Nominal Valid Command Parsing & In-Place Tokenization
    // ------------------------------------------------------------------------
    printf("  [TEST 1]: Verifying Nominal Valid Command Frame Parsing...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    // Frame: "@DRV,90,45,120*57\n"
    // Payload: "DRV,90,45,120" -> XOR Checksum: 0x57
    const char* valid_frame = "@DRV,90,45,120*57\n";
    push_string_to_buffer(&cb, valid_frame);

    ParseStatus result = feed_buffer_to_parser(&parser, &cb);

    assert(result == PARSE_SUCCESS);
    assert(parser.parsed_angles[0] == 90);
    assert(parser.parsed_angles[1] == 45);
    assert(parser.parsed_angles[2] == 120);
    printf("    [PASS]: Nominal frame successfully parsed into joint targets {90, 45, 120}.\n");

    // ------------------------------------------------------------------------
    // TEST 2: Checksum Failure Rejection
    // ------------------------------------------------------------------------
    printf("  [TEST 2]: Verifying Checksum Mismatch Anomaly Rejection...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    // Frame with intentionally corrupted checksum (0x99 instead of 0x57)
    const char* corrupted_checksum_frame = "@DRV,90,45,120*99\n";
    push_string_to_buffer(&cb, corrupted_checksum_frame);

    result = feed_buffer_to_parser(&parser, &cb);

    assert(result == PARSE_ERROR_CHECKSUM);
    printf("    [PASS]: Corrupted checksum rejected with PARSE_ERROR_CHECKSUM.\n");

    // ------------------------------------------------------------------------
    // TEST 3: Mid-Frame Reset and Incomplete Frame Resumption
    // ------------------------------------------------------------------------
    printf("  [TEST 3]: Verifying Malformed Stream Reset on Unexpected Start Byte...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    // Fragment: "@DRV,90,4" interrupted by a fresh "@DRV,0,180,90*62\n"
    // Payload "DRV,0,180,90" -> XOR: 0x6C
    const char* interrupted_stream = "@DRV,90,4@DRV,0,180,90*6C\n";
    push_string_to_buffer(&cb, interrupted_stream);

    result = feed_buffer_to_parser(&parser, &cb);

    assert(result == PARSE_SUCCESS);
    assert(parser.parsed_angles[0] == 0);
    assert(parser.parsed_angles[1] == 180);
    assert(parser.parsed_angles[2] == 90);
    printf("    [PASS]: Parser recovered cleanly after unexpected start delimiter.\n");

    // ------------------------------------------------------------------------
    // TEST 4: Non-Blocking Fragmented Ingestion
    // ------------------------------------------------------------------------
    printf("  [TEST 4]: Verifying Multi-Packet Stream Interleaving...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    const char* part1 = "@DRV,30,";
    const char* part2 = "60,90*60\n";

    push_string_to_buffer(&cb, part1);
    result = feed_buffer_to_parser(&parser, &cb);
    assert(result == PARSE_IN_PROGRESS);

    push_string_to_buffer(&cb, part2);
    result = feed_buffer_to_parser(&parser, &cb);
    assert(result == PARSE_SUCCESS);
    assert(parser.parsed_angles[0] == 30);
    assert(parser.parsed_angles[1] == 60);
    assert(parser.parsed_angles[2] == 90);
    printf("    [PASS]: Fragmented packet across multiple loop cycles assembled perfectly.\n");

    // ------------------------------------------------------------------------
    // TEST 5: Boundary Value Analysis (BVA) Clamping
    // ------------------------------------------------------------------------
    printf("  [TEST 5]: Verifying BVA Clamp on Out-Of-Bounds Target Angles...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    // Payload: "DRV,-50,999,45"
    // XOR Checksum: 0x7C
    // Bounds check: -50 clamped to 0, 999 clamped to 180, 45 preserved
    const char* bva_frame = "@DRV,-50,999,45*7C\n";
    push_string_to_buffer(&cb, bva_frame);

    result = feed_buffer_to_parser(&parser, &cb);

    assert(result == PARSE_SUCCESS);
    assert(parser.parsed_angles[0] == 0);   // Clamped lower limit
    assert(parser.parsed_angles[1] == 180); // Clamped upper limit
    assert(parser.parsed_angles[2] == 45);  // Nominal
    printf("    [PASS]: Out-of-bounds inputs {-50, 999, 45} clamped to safe limits {0, 180, 45}.\n");

    // ------------------------------------------------------------------------
    // TEST 6: Invalid ASCII Hex Characters in Checksum Tail
    // ------------------------------------------------------------------------
    printf("  [TEST 6]: Verifying Non-Hex Checksum Tail Rejection...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    const char* bad_hex_frame = "@DRV,90,45,0*GZ\n";
    push_string_to_buffer(&cb, bad_hex_frame);

    result = feed_buffer_to_parser(&parser, &cb);

    assert(result == PARSE_ERROR_CHECKSUM);
    printf("    [PASS]: Non-hexadecimal characters in checksum correctly trapped.\n");

    printf("[SUCCESS]: All Packet Parser Unit Tests Passed 100%%!\n");
}

int main(void) {
    run_packet_parser_tests();
    return 0;
}