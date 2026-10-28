# AutoRoboticArms

An interdisciplinary cyber-physical robotics platform integrating bare-metal silicon control, containerized edge microservices, and out-of-band cloud telemetry ingestion. The platform orchestrates a 3-DoF articulated robotic manipulator using a rate-monotonic ATmega328P microcontroller core, an asynchronous edge control plane hosted on a private homelab server, and a zero-cost ($0.00 OpEx) telemetry lake.

---

## System Architecture

```
                                  +---------------------------------------------+
                                  |    Cloud Layer: Distributed Cloud Data Lake |
                                  |   (AWS S3 Write-Blind Chunks, GZIP .pb.gz)  |
                                  +----------------------+----------------------+
                                                         ^
                                                         | (Asynchronous Batch Ingestion)
+--------------------------------------------------------+------------------------------------+
| Software Layer: Local Edge Control Plane (Docker / Ubuntu Server Homelab)                   |
|                                                                                             |
|   +-----------------------+     +------------------------+     +------------------------+   |
|   |  FastAPI ASGI Gateway | --> | Bounded Ingress Queue  | --> | pyserial Driver Thread |   |
|   |  (REST / WebSocket)   |     | (Backpressure Control) |     | (115,200 Baud)         |   |
|   +-----------------------+     +------------------------+     +-----------+------------+   |
|                                                                            |                |
+----------------------------------------------------------------------------+----------------+
                                                                             |
                                     +---------------------------------------+ (Full-Duplex UART)
                                     | Ingress: @DRV,j0,j1,j2*CS\n
                                     | Egress:  1-Byte Handshake ('K'/'E'/'H')
                                     v
+---------------------------------------------------------------------------------------------+
| Hardware Layer: Deterministic Silicon Sentinel (ATmega328P @ 16 MHz)                        |
|                                                                                             |
|   +-----------------------+     +------------------------+     +------------------------+   |
|   | 32-Byte Ring Buffer   | --> | 4-State FSM Parser     | --> | 300 ms Watchdog        |   |
|   | (ISR / Bitwise Mask)  |     | (Zero-Copy Slicing)    |     | (Active Holding Torque)|   |
|   +-----------------------+     +------------------------+     +-----------+------------+   |
|                                                                            |                |
|                                    +---------------------------------------+                |
|                                    | Bare-Metal Register TWI (100 kHz)                      |
|                                    v                                                        |
|                    +--------------------------------+                                       |
|                    | PCA9685 12-Bit PWM Controller  |                                       |
|                    +---------------+----------------+                                       |
+------------------------------------+--------------------------------------------------------+
                                     | (Split-Rail +5V / Common Ground / 1000uF Bulk Reservoir)
                                     v
+---------------------------------------------------------------------------------------------+
| Mechatronic Manipulator (Double-Tower Dead-Shaft Yoke)                                      |
|   - Base Yaw: MG996R + 2-Inch Lazy Susan Thrust Bearing                                     |
|   - Shoulder Pitch: MG996R + Dual MF84ZZ Flanged Bearings (12.0 cm Link)                    |
|   - Elbow Pitch: MG90S + Parallelogram Trailing Gripper Linkage (10.0 cm Link)              |
+---------------------------------------------------------------------------------------------+

```



---

## Systems Architecture & Engineering Trade-Offs

### Hardware Layer: Deterministic Silicon Sentinel & Actuator Firmware

*Completed Milestones: Sprints 1, 2, 2.5, 3.0, and 8 (Phase D SIL Integration)*

* **Bare-Metal Microcode vs. High-Level Runtime Libraries:** Replaced standard Arduino framework abstraction layers (`Wire.h`, `HardwareSerial`) with register-level drivers targeting the ATmega328P at 16 MHz. Built a custom Two-Wire Interface driver (`twi_driver.cpp`) controlling `TWBR`, `TWSR`, `TWCR`, and `TWDR` directly at 100 kHz (`TWBR=72`), bounding bus-polling states to a 20,000-cycle ceiling (`I2C_TIMEOUT_LIMIT`) to eliminate infinite CPU lockups during hardware clock line failures.


* **Zero-Copy Memory Pipelines Under 2 KB SRAM Constraints:** Ingestion is handled via a 32-byte circular ring buffer driven by UART receive interrupts (`ISR(USART_RX_vect)`). Multi-byte tearing and memory fragmentation are mitigated using single-byte atomic indices (`uint8_t`) and single-cycle power-of-two bitwise masking (`& 0x1F`). Ingress payloads are parsed through a 4-state Finite State Machine (FSM) utilizing in-place tokenization (`strtok`) on fixed stack buffers.


* **300 ms Watchdog & Active-Hold Failsafe:** Implemented a non-blocking hardware/software hybrid watchdog tracking monotonic clock deltas. If communication halts for $\ge 300\text{ ms}$, the system trips into an active safe-hold latch: instead of cutting PWM signals to zero duty cycles—which causes mechanical linkage collapse under gravitational torque—the firmware locks the PCA9685 PWM registers to the last known valid joint angles (`g_cached_angles`), maintaining continuous electromagnetic holding torque.


* **Tri-Phase Recovery Barrier:** Recovery from a 300 ms safety halt requires a 3-consecutive-frame trust burst (`@DRV,j0,j1,j2*CS\n`) with verified 8-bit XOR checksums, responding with `H` (Safe Hold) flags until the third frame before re-arming the motion planner and returning `K` (ACK).



### Software Layer: Local Hardened Edge Microservices & Ingress Gateway

*Completed Milestones: Sprints 1 through 7 (Sprint 8 Assembly/Integration Actively Underway)*

* **Tri-Threaded Concurrency Separation:** Designed `orchestrator_node.py` to decouple high-frequency physical serial transmission (20 Hz worker thread) from asynchronous network ingress (FastAPI/Uvicorn on port 8000) and disk I/O.


* **Bounded Backpressure Regulation:** Implemented a thread-safe bounded double-ended queue (`collections.deque(maxlen=10000)`) enforcing drop-on-full policies to prevent memory leaks and container OOM faults under sustained trajectory command bursts.


* **Container Security Isolation:** Encapsulated the application layer within an OCI-compliant Debian runtime (`python:3.12-slim`) running as an unprivileged POSIX user (`UID 10001:10001`). Configured hardware pass-through explicitly via Linux group attachment (`--group-add 20`) to grant serial access (`/dev/ttyACM0`) without giving the container privileged root capabilities.


* **Local Transactional Persistence:** Staged high-frequency joint states locally in SQLite utilizing Write-Ahead Logging (`PRAGMA journal_mode=WAL;`), providing concurrent, lock-free reads for diagnostics while isolating the write path.



### Cloud Layer: Distributed Cloud Data Fabric & Vendor Migration

*Completed Milestones: Sprints 1 through 10 (Pipeline Finalized)*

* **Cloud Migration Case Study (GCP to AWS):** The cloud landing zone was originally planned for Google Cloud Platform (GCS, Cloud Functions, and Eventarc). During Sprint 9, the telemetry destination pivoted to Amazon Web Services (AWS S3). Because edge persistence (`database_manager.py`), serialization schemas (`telemetry_schema.proto`), and worker routines were designed around vendor-neutral POSIX standards, the entire application runtime was migrated to AWS with zero modifications to core business logic—requiring only changes to the egress transport client (`boto3`) and cloud identity policies.


* **Zero-Trust Write-Blind IAM Architecture:** Edge credentials (`edge-telemetry-writer`) are restricted strictly to `s3:PutObject` on the designated bucket prefix. The identity is explicitly denied `s3:GetObject`, `s3:ListBucket`, and `s3:DeleteObject`, ensuring that even an arbitrary compromise of the local homelab machine cannot lead to exfiltration, tampering, or deletion of historical cloud telemetry.


* **Sliding-Window Compaction & $0.00 OpEx Defense:** To prevent S3 Class A request exhaustion under 20 Hz generation rates, `cloud_sync.py` enforces a dual-boundary batching engine ($N \ge 50\text{ records}$ or $\Delta t \ge 30.0\text{ s}$). Payloads are packaged using binary Protocol Buffers v3 and compressed in-memory via GZIP (`compresslevel=9`), reducing monthly network transactions by over 95%. An automated 7-day S3 lifecycle expiration policy purges aging archives, locking total cloud operational expense at $0.00/month.



---

## Physical Mechatronics & Power Distribution

* **Split-Rail Power Isolation:** Microcontroller logic gates run exclusively on clean +5V USB power from the host machine. Actuator power is isolated on an independent +5V (3A–4A) external DC bench supply. Both rails share a common ground reference point at the Arduino GND terminal to eliminate floating I2C logic lines without creating inter-rail ground loops.


* **Transient Voltage Suppression & BOD Protection:** When the dual MG996R actuators initiate acceleration from rest, motor inrush currents spike to $\approx 1.5\text{ A} \dots 2.5\text{ A}$ per unit. A low-ESR $1000\,\mu\text{F}$ electrolytic capacitor placed across the PCA9685 power terminal acts as a local reservoir, absorbing inductive back-EMF ($V_L = L \frac{di}{dt}$) and preventing voltage dips below the ATmega328P's 4.3V Brown-Out Detection (BOD) threshold. High-frequency switching noise is shunted to ground via 100 nF ceramic capacitors adjacent to logic pins.


* **Mechanical Load Decoupling:** Manipulator links are cut from 3 mm rigid Sintra Expanded PVC with fixed pivot invariants ($L_1 = 12.0\text{ cm}$, $L_2 = 10.0\text{ cm}$). Base axial and radial loads are decoupled from the base servo horn via a 2-inch Lazy Susan ball bearing turntable, isolating the motor gear train from cantilever bending moments. The shoulder joint utilizes a double-tower yoke supported by dual MF84ZZ flanged ball bearings riding on a steel dead-shaft pin, transferring linkage mass into the chassis frame.



---

## Interface Control Document (ICD)

### Serial Wire Link (Software $\leftrightarrow$ Hardware)

* **Physical Medium:** Full-Duplex UART over USB (`/dev/ttyACM0`) at 115,200 Baud, 8-N-1.


* **Frame Structure:** `@DRV,<joint0>,<joint1>,<joint2>*<XOR_HEX>\n` (Payload $\le 24$ bytes).


* **Parity Computation:** 8-bit uppercase hexadecimal representation of rolling XOR across all characters between `@` and `*`.


* **Handshake Acknowledgements:**
* `'K'` (0x4B): Command validated, checksum verified, target registered.


* `'E'` (0x45): Formatting error, framing violation, or XOR checksum mismatch (Frame discarded).


* `'H'` (0x48): Communication timeout tripped ($\ge 300\text{ ms}$); arm locked in safe holding torque.





### Wire Format & Cloud Schemas (Software Layer $\leftrightarrow$ Cloud Layer)

* **Local Staging Schema (`telemetry_ingress_queue`):** `record_id` (INTEGER PK AUTOINCREMENT), `timestamp` (DATETIME), `sync_status` (VARCHAR: `PENDING`, `PROCESSING`, `SYNCED`), `left_arm_protobuf_blob` (BLOB).


* **Wire Protocol (Protobuf v3):** Serialized byte structures using IEEE 754 32-bit floats for joint coordinates (`base_yaw`, `shoulder_pitch`, `elbow_pitch`), mapped with a 4-byte big-endian framing length header.


* **S3 Bucket Object Key Layout:** `telemetry/year={YYYY}/chunk_{YYYYMMDD_HHMMSS_ffffff}.pb.gz`.



---

## Repository Structure

```
AutoRoboticArms/
├── Hardware/                         # Hardware Layer: Deterministic Silicon Sentinel
│   ├── firmware/
│   │   ├── include/                  # Ring buffer, FSM parser, TWI register driver, watchdog
│   │   └── src/                      # main.cpp (50 Hz rate-monotonic superloop), unit drivers
│   ├── firmware_host/                # Python SIL testing harness, mock serial interfaces
│   └── tests/                        # Software-in-the-Loop native test runners
├── Software/                         # Software Layer: Edge Compute & Orchestration Plane
│   ├── src/
│   │   ├── orchestrator_node.py      # Tri-threaded serial dispatch, bounded queue core
│   │   └── api/                      # FastAPI ASGI routes, Pydantic validation models
│   ├── tests/                        # Pytest suites, mock serial loopback tests
│   └── Dockerfile                    # Multi-stage unprivileged OCI deployment image
└── Cloud/                            # Cloud Layer: Distributed Data Fabric & Cloud Landing Zone
    ├── proto/                        # telemetry_schema.proto definitions
    ├── src/
    │   ├── cloud_sync.py             # Asynchronous out-of-band batching daemon
    │   └── control_plane.py          # Port 8050 diagnostics gateway & WebSocket engine
    ├── aws/                          # iam_write_blind_policy.json, s3_lifecycle_rule.json
    └── docker-compose.yml            # Multi-container boundary composition

```