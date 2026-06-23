#include <avr/io.h>
#include <avr/interrupt.h>

// Direct mapping to Arduino hardware PWM pin footprints
#define BASE_LED_PIN     9   // Timer1 Output Channel A (OC1A)
#define SHLDR_LED_PIN    10  // Timer1 Output Channel B (OC1B)
#define ELBOW_LED_PIN    11  // Timer2 Output Channel A (OC2A)

// Volatile variables mapped down from your Sprint 1 data parser loops
volatile uint8_t base_angle = 90;
volatile uint8_t shldr_angle = 90;
volatile uint8_t elbow_angle = 90;

void setup_starter_kit_io(void) {
    // Configure pins 9, 10, and 11 explicitly as digital outputs
    pinMode(BASE_LED_PIN, OUTPUT);
    pinMode(SHLDR_LED_PIN, OUTPUT);
    pinMode(ELBOW_LED_PIN, OUTPUT);
    
    // Natively baseline our initial state positions to standard 90-degree midpoints
    analogWrite(BASE_LED_PIN, 127);   // 50% duty cycle state
    analogWrite(SHLDR_LED_PIN, 127);  // 50% duty cycle state
    analogWrite(ELBOW_LED_PIN, 127);  // 50% duty cycle state
}

void execute_led_voltage_transformations(void) {
    // Translate incoming 8-bit angles (0 to 180) to standard 8-bit PWM values (0 to 255)
    // Formula: Duty Cycle Byte = (Target Angle * 255) / 180
    uint8_t base_pwm  = ((uint16_t)(base_angle) * 255) / 180;
    uint8_t shldr_pwm = ((uint16_t)(shldr_angle) * 255) / 180;
    uint8_t elbow_pwm = ((uint16_t)(elbow_angle) * 255) / 180;

    // Direct registration step driving current down the physical pin tracks
    analogWrite(BASE_LED_PIN, base_pwm);
    analogWrite(SHLDR_LED_PIN, shldr_pwm);
    analogWrite(ELBOW_LED_PIN, elbow_pwm);
}