#include <iostream>
#include <cassert>
#include "../include/circular_buffer.h"

// Terminal output escape configurations for clear visual pass matrices
#define LOG_PASS(msg) std::cout << "\033[32m[PASS] " << msg << "\033[0m\n"
#define LOG_ALERT(msg) std::cout << "\033[33m[STAGING] " << msg << "\033[0m\n"

void test_initial_state() {
    CircularBuffer ring;
    ring.init();
    
    // Assert correct structural properties on fresh instantiation
    assert(ring.get_count() == 0);
    assert(!ring.is_full());
    LOG_PASS("Initial baseline state limits verified.");
}

void test_overflow_backpressure_interlock() {
    CircularBuffer ring;
    ring.init();
    
    // Pump entries up to the explicit maximum limit boundary size (64 bytes)
    for (uint8_t i = 0; i < BUFFER_SIZE; ++i) {
        bool enqueued = ring.enqueue(i);
        assert(enqueued == true);
    }
    
    // Assert capacity guard is actively blocking further ingress modifications
    assert(ring.get_count() == BUFFER_SIZE);
    assert(ring.is_full() == true);
    
    // Attack the full buffer with an overflow byte to verify defensive protection
    bool overflow_breach_status = ring.enqueue(0xFF);
    assert(overflow_breach_status == false); // Enqueue must fail safely
    assert(ring.get_count() == BUFFER_SIZE);  // Storage size must remain untouched
    
    LOG_PASS("Overflow backpressure interlock defended array bounds successfully.");
}

void test_sliding_window_bitwise_wrap() {
    CircularBuffer ring;
    ring.init();
    
    // Fill buffer completely
    for (uint8_t i = 0; i < BUFFER_SIZE; ++i) {
        ring.enqueue(i);
    }
    
    // Dequeue a block of 10 entries to slide the trailing pointer forward
    uint8_t target_byte = 0;
    for (uint8_t i = 0; i < 10; ++i) {
        assert(ring.dequeue(target_byte));
        assert(target_byte == i); // Assert FIFO ordering contract matches
    }
    assert(ring.get_count() == (BUFFER_SIZE - 10)); // 54 remaining
    
    // Enqueue 5 new tracking entries to force the head pointer to wrap past 64 
    // using the bitwise & BUFFER_MASK operator
    for (uint8_t i = 0; i < 5; ++i) {
        assert(ring.enqueue(i + 200));
    }
    assert(ring.get_count() == 59);
    
    LOG_PASS("Sliding window bitwise wrapping calculations validated.");
}

int main() {
    std::cout << "==================================================\n";
    std::cout << "[QA LAB] Executing Isolated Circular Buffer Tests...\n";
    std::cout << "==================================================\n";
    
    test_initial_state();
    test_overflow_backpressure_interlock();
    test_sliding_window_bitwise_wrap();
    
    std::cout << "\n\033[32m[SUCCESS] Component Gate Closed. Memory ring is airtight.\033[0m\n";
    return 0;
}