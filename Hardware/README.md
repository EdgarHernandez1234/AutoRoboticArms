# Hardware Layer

Here will be focusing on the embedded systems aspects of my Project

## Tech Stack

### Hardware:
- Arduino Uno R3
- Raspberry Pi 4 Model B
- Ubuntu Server LTS serial ports

### Software:
- Pytest
- Python venv
- Cmake

## Sprints

### Sprint 1: Writing the conductor_host.py file 
- Implementing inverse kinematics on conductor host
- Implementing a CRC8 checksum instead of a simple XOR checksum
- Implementing a 2 byte binary framing for a 3-axis robotic arm for now (The second arm will come later)
- Updating my project architecture to reflect this on my first sprint for this hardware Layer 

### Sprint 2: Shifting Left and writing my Unit tests early
- Using pytest to write a test harness in a isolated python environment. Requirements.txt have the versions of python libraries I am currently using for this sprint
- pytest.ini is responsible for Manifest Calibration which makes a filepath that leads to the unit tests while keeping other files unaffected
- Added conductor.serial_connection= reset_mock() which makes sure each unit test goes through a clean run
-  Added Safety operating bounds min and max on arm to not arm
- Working on Boundary Value Analysis which now has Epsilon-Flanking Fuzzing unit tests which include very small numbers that barely go over or under the robotic arm safety limits
- Added a clamped edge frame when the robotic arm is in manual mode. It handles the arm from going over or under its safety limits. Updated the previous manual mode exception unit test to calculate clamped ticks
- Added Telementary Log Throttling which defends against Denial of Service exploits but keeps precise vector forsenics for seeing what the bad ai/person wanted to do. Also a unit test that reflects this
- Added an custom exception which the AI on the software layer is able to reorginize its planned path. Will be expanded in the Software Layer

### Sprint 3: Bare Metal C++:
- Using CMake to make a dual-target project architecture
-  Made main and ring buffer C++ files to keep memory separate from execution states. 
- Implemented automated path configs (compile_commands.json) to include custom directories to VSCode to avoid red squiggly lines
- Made a Pre-Processor Sheild Blueprint which isolates physical hardware dependencies from host simulation code
- Main control system loop and testing frame work run independently. So testing code can be removed from main code to keep microcontroller have its minimal resources
- Implemented fixed 32-byte memory ring buffer with a CRC8 CCCITT Table to prevent memory overflow exploits. So no rogue commands for the arm 
- Using an old laptop that's running a headless Ubuntu Server LTS with Docker. Also will use Docker Bulid-Time Secret Injection to not leak hardware key in github repo but keep no overhead in binary trasfers to microchip tracking lines
- Using a Bi-Directional Handshake Protocol which means no more data crowding and Queue Starvation. So the Python app won't go over what the physical servo can handle and the arduino microcontroller will write a byte token to show it is completely lined up.
- Made a test register stub for the register emulator
- Made Unit tests which are in tests

### Sprint 4: Robotic Arm assembly
- Researching possible materials to make robotic arm without a 3D printer for first prototype