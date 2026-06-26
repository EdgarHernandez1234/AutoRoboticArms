#ifndef PACKET_PARSER_H
#define PACKET_PARSER_H

#include <stdint.h>
#include <stdbool.h>

#define MAX_PACKET_LENGTH 32

class PacketParser {
public:
    enum ParseState {
        WAIT_FOR_START,
        ACCUMULATE_PAYLOAD,
        WAIT_FOR_CHECKSUM
    };

private:
    char packet_buffer[MAX_PACKET_LENGTH];
    uint8_t write_index;
    ParseState current_state;

    // Fixed array outputs to pass parsed values up to main trajectory tracks safely
    uint8_t parsed_servo_id;
    int16_t parsed_angle;

public:
    // 1. STATE INITIALIZATION: Arms the monitoring perimeters
    void init() {
        write_index = 0;
        current_state = WAIT_FOR_START;
        parsed_servo_id = 0;
        parsed_angle = 0;
        packet_buffer[0] = '\0';
    }

    // 2. PARSE PERIMETER WATCHDOG: Ingests bytes sequentially from the memory ring buffer
    bool update(uint8_t data) {
        switch (current_state) {
            case WAIT_FOR_START:
                if (data == '@') { // Start character anchor found
                    write_index = 0;
                    current_state = ACCUMULATE_PAYLOAD;
                }
                break;

            case ACCUMULATE_PAYLOAD:
                if (data == '*') { // Payload string boundary limit encountered
                    packet_buffer[write_index] = '\0'; // Seal current C-string tracking window
                    current_state = WAIT_FOR_CHECKSUM;
                } else {
                    if (write_index < (MAX_PACKET_LENGTH - 3)) { // Defend array bounds against memory overflow
                        packet_buffer[write_index++] = (char)data;
                    } else {
                        init(); // Memory perimeter breached, force immediate state recovery reset
                    }
                }
                break;

            case WAIT_FOR_CHECKSUM:
                if (data == '\n') {
                    // Frame tracking closed. Return true to signal token processing execution check is primed
                    current_state = WAIT_FOR_START;
                    return true;
                }
                break;
        }
        return false;
    }

    // Accessor methods to fetch validated kinematic metrics cleanly
    uint8_t get_servo_id() const { return parsed_servo_id; }
    int16_t get_angle() const { return parsed_angle; }
};

#endif // PACKET_PARSER_H