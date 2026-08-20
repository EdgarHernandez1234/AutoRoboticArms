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

    // Verify empty read protection
    uint8_t dummy_byte = 0;
    bool empty_dequeue = circular_buffer_read(&rb, &dummy_byte);
    assert(empty_dequeue == false);
    assert(rb.head == 0 && rb.tail == 0); // Pointers must remain untouched
    printf("    [PASS]: Buffer initializes to pure zero and rejects empty read operations.\n");

    // ------------------------------------------------------------------------
    // TEST 2: Basic Write / Read FIFO Ordering
    // ------------------------------------------------------------------------
    printf("  [TEST 2]: Verifying Sequential FIFO Write/Read Ordering...\n");
    const char* test_payload = "@DRV,90,45,180*2E\n";
    size_t payload_len = strlen(test_payload);

    for (size_t i = 0; i < payload_len; i++) {
        bool ok = circular_buffer_write(&rb, (uint8_t)test_payload[i]);
        assert(ok == true);
    }

    assert(circular_buffer_available(&rb) == (uint8_t)payload_len);
    assert(circular_buffer_is_empty(&rb) == false);

    // Read back and assert 1:1 character parity
    for (size_t i = 0; i < payload_len; i++) {
        uint8_t extracted = 0;
        bool ok = circular_buffer_read(&rb, &extracted);
        assert(ok == true);
        assert(extracted == (uint8_t)test_payload[i]);
    }

    assert(circular_buffer_is_empty(&rb) == true);
    assert(circular_buffer_available(&rb) == 0);
    printf("    [PASS]: Exact FIFO sequence validated across full command frame.\n");

    // ------------------------------------------------------------------------
    // TEST 3: Usable Boundary Limit (31 Bytes) & Overflow Rejection
    // ------------------------------------------------------------------------
    printf("  [TEST 3]: Verifying 31-Byte Usable Boundary & Overflow Intercept...\n");
    circular_buffer_init(&rb);

    // Fill up to 31 bytes (usable capacity for 32-byte circular buffer)
    for (uint8_t i = 0; i < 31; i++) {
        bool ok = circular_buffer_write(&rb, i);
        assert(ok == true);
    }

    assert(circular_buffer_available(&rb) == 31);
    assert(circular_buffer_is_full(&rb) == true);

    // 32nd byte write MUST fail to prevent head from colliding with tail
    bool overflow_attempt = circular_buffer_write(&rb, 0xFF);
    assert(overflow_attempt == false);
    assert(circular_buffer_available(&rb) == 31); // Count remains 31
    printf("    [PASS]: 31-byte usable capacity respected; 32nd byte correctly rejected.\n");

    // ------------------------------------------------------------------------
    // TEST 4: Power-of-Two Index Wrap-Around Bitwise Arithmetic (& 0x1F)
    // ------------------------------------------------------------------------
    printf("  [TEST 4]: Verifying Single-Cycle Pointer Wrap-Around (& 0x1F)...\n");
    // Clear 28 bytes out of the 31 currently in the buffer
    for (uint8_t i = 0; i < 28; i++) {
        uint8_t val = 0;
        assert(circular_buffer_read(&rb, &val) == true);
        assert(val == i);
    }

    // Now tail is at 28, head is at 31 -> 3 unread bytes remain
    assert(rb.tail == 28);
    assert(rb.head == 31);
    assert(circular_buffer_available(&rb) == 3);

    // Write 4 more bytes: (31 + 1) & 0x1F = 0, wrapping head around to 0, 1, 2, 3
    for (uint8_t i = 0; i < 4; i++) {
        assert(circular_buffer_write(&rb, (uint8_t)('A' + i)) == true);
    }
    assert(rb.head == 3);

    // Total available: (3 - 28) & 0x1F = 7 unread bytes
    assert(circular_buffer_available(&rb) == 7);

    // Read remaining 3 original bytes (28, 29, 30)
    for (uint8_t i = 28; i < 31; i++) {
        uint8_t val = 0;
        assert(circular_buffer_read(&rb, &val) == true);
        assert(val == i);
    }

    // Read the 4 wrapped bytes ('A', 'B', 'C', 'D')
    for (uint8_t i = 0; i < 4; i++) {
        uint8_t val = 0;
        assert(circular_buffer_read(&rb, &val) == true);
        assert(val == (uint8_t)('A' + i));
    }

    assert(circular_buffer_is_empty(&rb) == true);
    assert(rb.head == 3 && rb.tail == 3);
    printf("    [PASS]: Bitwise wrap-around arithmetic ((3 - 28) & 0x1F = 7) verified perfect.\n");

    // ------------------------------------------------------------------------
    // TEST 5: Defensive NULL Pointer Intercepts
    // ------------------------------------------------------------------------
    printf("  [TEST 5]: Verifying NULL Pointer Defensive Intercepts...\n");
    assert(circular_buffer_write(NULL, 0x10) == false);
    assert(circular_buffer_read(NULL, &dummy_byte) == false);
    assert(circular_buffer_read(&rb, NULL) == false);
    assert(circular_buffer_available(NULL) == 0);
    assert(circular_buffer_is_full(NULL) == false);
    assert(circular_buffer_is_empty(NULL) == true);
    printf("    [PASS]: All NULL pointer defensive gates return safe fallback states.\n");

    printf("[SUCCESS]: All 32-Byte Ring Buffer Unit Tests Passed 100%%!\n");
}

int main(void) {
    run_circular_buffer_tests();
    return 0;
}