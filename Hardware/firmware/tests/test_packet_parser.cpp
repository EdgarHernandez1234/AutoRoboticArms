#include "../include/packet_parser.h"
#include "../include/circular_buffer.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

/**
 * @brief Helper function to push an entire string into the CircularBuffer byte-by-byte.
 */
static void push_string_to_buffer(CircularBuffer* rb, const char* str) {
    size_t len = strlen(str);
    for (size_t i = 0; i < len; i++) {
        bool ok = circular_buffer_enqueue(rb, (uint8_t)str[i]);
        assert(ok == true); // Ensure circular buffer capacity is sufficient
    }
}

void run_packet_parser_tests(void) {
    printf("[STAGING]: Initializing Non-Blocking Packet Parser Test Suite...\n");

    CircularBuffer cb;
    PacketParser parser;
    ParsedCommand cmd;

    // ------------------------------------------------------------------------
    // TEST 1: Nominal Valid Command Parsing & In-Place Tokenization
    // ------------------------------------------------------------------------
    printf("  [TEST 1]: Verifying Nominal Valid Command Frame Parsing...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    // Frame: "@DRV,90,45,120*57\n"
    // Payload: "DRV,90,45,120"
    // XOR Checksum Calculation: 'D'^'R'^'V'^','^'9'^'0'^','^'4'^'5'^','^'1'^'2'^'0' = 0x3B
    const char* nominal_frame = "@DRV,90,45,120*57\n";
    push_string_to_buffer(&cb, nominal_frame);

    ParseResult result = packet_parser_process_buffer(&parser, &cb, &cmd);

    assert(result == PARSE_SUCCESS_FRAME);
    assert(cmd.valid == true);
    assert(strcmp(cmd.command, "DRV") == 0);
    assert(cmd.angle_count == 3);
    assert(cmd.angles[0] == 90);
    assert(cmd.angles[1] == 45);
    assert(cmd.angles[2] == 120);
    assert(parser.valid_packets == 1);
    assert(parser.corrupted_packets == 0);
    printf("    [PASS]: Nominal frame successfully parsed with correct joint angles {90, 45, 120}.\n");

    // ------------------------------------------------------------------------
    // TEST 2: Corrupted Checksum Rejection & Dropped Frame Counters
    // ------------------------------------------------------------------------
    printf("  [TEST 2]: Verifying Corrupted Checksum Rejection...\n");
    memset(&cmd, 0, sizeof(ParsedCommand));
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    // Frame with intentionally corrupted checksum (0xFF instead of 0x3B)
    const char* corrupted_frame = "@DRV,90,45,120*FF\n";
    push_string_to_buffer(&cb, corrupted_frame);

    result = packet_parser_process_buffer(&parser, &cb, &cmd);

    assert(result == PARSE_ERROR_CHECKSUM);
    assert(cmd.valid == false);
    assert(parser.valid_packets == 0);
    assert(parser.corrupted_packets == 1);
    printf("    [PASS]: Corrupted checksum caught, frame rejected, and corrupted_packets counter incremented.\n");

    // ------------------------------------------------------------------------
    // TEST 3: Payload Overflow Protection (> 24 Chars Before '*')
    // ------------------------------------------------------------------------
    printf("  [TEST 3]: Verifying Payload Overflow Guard (> 24 characters)...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    // Flooded payload (26 characters before '*'): "DRV,1234567890123456789012"
    const char* overflow_frame = "@DRV,1234567890123456789012*00\n";
    push_string_to_buffer(&cb, overflow_frame);

    result = packet_parser_process_buffer(&parser, &cb, &cmd);

    assert(result == PARSE_ERROR_OVERFLOW);
    assert(parser.overflow_packets == 1);
    assert(parser.state == STATE_WAIT_FOR_START); // FSM must reset cleanly
    printf("    [PASS]: Payload overflow caught before array boundary; FSM reset safely.\n");

    // ------------------------------------------------------------------------
    // TEST 4: Mid-Stream Frame Re-Synchronization (Unexpected '@')
    // ------------------------------------------------------------------------
    printf("  [TEST 4]: Verifying Mid-Stream Frame Re-Synchronization...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    // Partial garbled frame followed immediately by a fresh valid frame:
    // "@DRV,90,45" (no '*' or '\n') interrupted by "@DRV,180,90*70\n"
    const char* interrupted_stream = "@DRV,90,45@DRV,180,90*70\n";
    push_string_to_buffer(&cb, interrupted_stream);

    result = packet_parser_process_buffer(&parser, &cb, &cmd);

    assert(result == PARSE_SUCCESS_FRAME);
    assert(cmd.valid == true);
    assert(cmd.angle_count == 2);
    assert(cmd.angles[0] == 180);
    assert(cmd.angles[1] == 90);
    assert(parser.valid_packets == 1);
    printf("    [PASS]: Unexpected '@' re-synchronized parser instantly; valid second frame executed.\n");

    // ------------------------------------------------------------------------
    // TEST 5: Boundary Value Analysis (BVA) Angle Clamping (0 - 180 Deg)
    // ------------------------------------------------------------------------
    printf("  [TEST 5]: Verifying Boundary Value Analysis (BVA) Servo Angle Clamping...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    // Out-of-bounds angles string: -50 clamped to 0, 999 clamped to 180
    // Payload: "DRV,-50,999"
    // XOR Checksum: 'D'^'R'^'V'^','^'-'^'5'^'0'^','^'9'^'9'^'9' = 0x51
    const char* bva_frame = "@DRV,-50,999*51\n";
    push_string_to_buffer(&cb, bva_frame);

    result = packet_parser_process_buffer(&parser, &cb, &cmd);

    assert(result == PARSE_SUCCESS_FRAME);
    assert(cmd.valid == true);
    assert(cmd.angles[0] == 0);   // -50 clamped to 0
    assert(cmd.angles[1] == 180); // 999 clamped to 180
    printf("    [PASS]: Out-of-bounds angles {-50, 999} successfully clamped to safe bounds {0, 180}.\n");

    // ------------------------------------------------------------------------
    // TEST 6: Invalid ASCII Hex Characters in Checksum Tail
    // ------------------------------------------------------------------------
    printf("  [TEST 6]: Verifying Non-Hex Checksum Tail Rejection...\n");
    circular_buffer_init(&cb);
    packet_parser_init(&parser);

    // Frame with non-hex tail characters 'G' and 'Z'
    const char* bad_hex_frame = "@DRV,90,45*GZ\n";
    push_string_to_buffer(&cb, bad_hex_frame);

    result = packet_parser_process_buffer(&parser, &cb, &cmd);

    assert(result == PARSE_ERROR_FORMAT);
    assert(parser.corrupted_packets == 1);
    printf("    [PASS]: Non-hex checksum character intercepted and rejected cleanly.\n");

    printf("\n[SUCCESS]: All Non-Blocking Packet Parser tests passed with 100%% green assertions!\n\n");
}

int main(void) {
    run_packet_parser_tests();
    return 0;
}