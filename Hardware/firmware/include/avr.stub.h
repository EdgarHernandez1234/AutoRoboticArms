#ifndef AVR_STUB_H
#define AVR_STUB_H

#ifdef TESTING_ON_HOST
#include <stdint.h>

// Mocking bare-metal 8-bit register variables inside your MacBook's RAM space
extern volatile uint8_t UBRR0H;
extern volatile uint8_t UBRR0L;
extern volatile uint8_t UCSR0A;
extern volatile uint8_t UCSR0B;
extern volatile uint8_t UCSR0C;
extern volatile uint8_t UDR0;

#define U2X0   1
#define RXCIE0 2
#define RXEN0  3
#define TXEN0  4
#define UCSZ01 5
#define UCSZ00 6
#define UDRE0  7
#define RXC0   7

inline void cli() {}
inline void sei() {}

#else
#include <avr/io.h>
#include <avr/interrupt.h>
#endif

#endif // AVR_STUB_H