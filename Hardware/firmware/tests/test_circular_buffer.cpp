#include "../include/circular_buffer.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

void run_circular_buffer_tests(void) {
    printf("[STAGING]: Initializing 32-Byte Ring Buffer Unit Test Suite...\n");

    CircularBuffer rb;

    // ------------------------------------------------------------------------
    // TEST 1: Initialization & Empty State Verification
    // ------------------------------------------------------------------------
    printf("  [TEST 1]: Verifying Initialization State...\n");
    circular_buffer_init(&rb);

    assert(rb.head == 0);
    assert(rb.tail == 0);
    assert(circular_buffer_is_empty(&rb) == true);
    assert(circular_buffer_is_full(&rb) == false);
    assert(circular_buffer_available(&rb) == 0);

    // Verify empty dequeue protection
    uint8_t dummy_byte = 0;
    bool empty_dequeue = circular_buffer_dequeue(&rb, &dummy_byte);
    assert(empty_dequeue == false);
    assert(rb.head == 0 && rb.tail == 0); // Pointers must remain untouched
    printf("    [PASS]: Buffer initializes to pure zero and rejects empty dequeue operations.\n");

    // ------------------------------------------------------------------------
    // TEST 2: Basic Enqueue / Dequeue FIFO Ordering
    // ------------------------------------------------------------------------
    printf("  [TEST 2]: Verifying Sequential FIFO Enqueue/Dequeue Ordering...\n");
    uint8_t test_payload[] = {'@', 'D', 'R', 'V', ',', '9', '0', '*'};
    uint8_t payload_len = sizeof(test_payload);

    for (uint8_t i = 0; i < payload_len; i++) {
        bool ok = circular_buffer_enqueue(&rb, test_payload[i]);
        assert(ok == true);
    }

    assert(circular_buffer_available(&rb) == payload_len);
    assert(circular_buffer_is_empty(&rb) == false);

    // Read back bytes and assert strict First-In, First-Out sequence parity
    for (uint8_t i = 0; i < payload_len; i++) {
        uint8_t read_byte = 0;
        bool ok = circular_buffer_dequeue(&rb, &read_byte);
        assert(ok == true);
        assert(read_byte == test_payload[i]);
    }

    assert(circular_buffer_available(&rb) == 0);
    assert(circular_buffer_is_empty(&rb) == true);
    printf("    [PASS]: First-In, First-Out (FIFO) byte integrity confirmed 100%% match.\n");

    // ------------------------------------------------------------------------
    // TEST 3: Capacity Boundary & Full Sentinel Enforcement (31 Usable Bytes)
    // ------------------------------------------------------------------------
    printf("  [TEST 3]: Verifying 31-Byte Capacity Boundary & Overflow Dropping...\n");
    circular_buffer_init(&rb);

    // Fill buffer to max capacity (31 bytes out of 32 slots)
    for (uint8_t i = 0; i < 31; i++) {
        bool ok = circular_buffer_enqueue(&rb, (uint8_t)(i + 1));
        assert(ok == true);
    }

    // Assert Full condition
    assert(circular_buffer_available(&rb) == 31);
    assert(circular_buffer_is_full(&rb) == true);

    // Attempt 32nd byte write (Must fail to preserve full vs empty sentinel boundary)
    bool overflow_enqueue = circular_buffer_enqueue(&rb, 0xFF);
    assert(overflow_enqueue == false); // Fail-safe drop
    assert(circular_buffer_available(&rb) == 31); // Size remains capped at 31
    printf("    [PASS]: Sentinel boundary correctly caps buffer at 31 bytes and drops overflow byte.\n");

    // ------------------------------------------------------------------------
    // TEST 4: Pointer Wrap-Around & Two's Complement Unread Math ((head - tail) & 0x1F)
    // ------------------------------------------------------------------------
    printf("  [TEST 4]: Verifying Pointer Index Wrap-Around & (head - tail) & 0x1F Math...\n");
    circular_buffer_init(&rb);

    // Advance pointers near end of array: tail = 28, head = 28
    rb.head = 28;
    rb.tail = 28;

    // Enqueue 7 bytes to force head past 31 (wraps to 0, 1, 2, 3)
    for (uint8_t i = 0; i < 7; i++) {
        bool ok = circular_buffer_enqueue(&rb, (uint8_t)('A' + i));
        assert(ok == true);
    }

    // Confirm wrapped index states: tail = 28, head = 3 ((28 + 7) & 0x1F = 3)
    assert(rb.tail == 28);
    assert(rb.head == 3);

    // Math Check: (3 - 28) & 0x1F = -25 & 0x1F = 231 & 31 = 7 unread bytes!
    assert(circular_buffer_available(&rb) == 7);

    // Dequeue all 7 bytes and check read accuracy across array wrap boundary
    for (uint8_t i = 0; i < 7; i++) {
        uint8_t val = 0;
        bool ok = circular_buffer_dequeue(&rb, &val);
        assert(ok == true);
        assert(val == (uint8_t)('A' + i));
    }

    assert(circular_buffer_is_empty(&rb) == true);
    assert(rb.tail == 3);
    assert(rb.head == 3);
    printf("    [PASS]: Index wrap-around arithmetic ((3 - 28) & 0x1F = 7) verified perfect.\n");

    // ------------------------------------------------------------------------
    // TEST 5: NULL Pointer Defensive Safety Guards
    // ------------------------------------------------------------------------
    printf("  [TEST 5]: Verifying NULL Pointer Defensive Intercepts...\n");
    assert(circular_buffer_enqueue(NULL, 0x10) == false);
    assert(circular_buffer_dequeue(NULL, &dummy_byte) == false);
    assert(circular_buffer_dequeue(&rb, NULL) == false);
    assert(circular_buffer_available(NULL) == 0);
    assert(circular_buffer_is_full(NULL) == false);
    assert(circular_buffer_is_empty(NULL) == true);
    printf("    [PASS]: NULL pointer defensive guards successfully neutralized invalid calls.\n");

    printf("\n[SUCCESS]: All 32-Byte Ring Buffer tests passed with 100%% green assertions!\n\n");
}

int main(void) {
    run_circular_buffer_tests();
    return 0;
}