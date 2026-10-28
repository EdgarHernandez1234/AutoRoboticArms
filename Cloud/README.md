# Distributed Cyber-Physical Telemetry & Cloud Data Lake (Cloud Layer)

An asynchronous, fault-tolerant edge-to-cloud telemetry ingestion pipeline designed for multi-axis robotic platforms. This system bridges high-frequency local mechatronic execution with remote cloud analytics under a perpetual **$0.00/month operational expense (OpEx)** profile.

---

## System Architecture

Cloud Layer operates as an out-of-band data fabric. It decouples real-time hardware actuation loops from cloud network latency by staging high-frequency joint states into an append-only local relational buffer before streaming delta-compressed binary archives to Amazon S3.


```

┌────────────────────────────────────────────────────────────────────────┐
│                      docker-compose.yml Host Boundary                  │
│                                                                        │
│  Host: ./storage  ────────[:rw]────────► /app/storage (SQLite WAL DB)  │
│  Host: ~/.aws     ────────[:ro]────────► /home/appuser/.aws (No Keys)  │
│                                                                        │
│   ┌───────────────────────────┐         ┌──────────────────────────┐   │
│   │       control-plane       │         │        cloud-sync        │   │
│   │  - Port 8050:8050         │         │  - Background sync daemon│   │
│   │  - REST /health           │         │  - Delta-GZIP (.pb.gz) S3│   │
│   │  - ws://host:8050/ws/tele │         │  - 3-strike breaker      │   │
│   │  - Healthcheck: urllib    │         │  - Cold-boot auto-schema │   │
│   └─────────────┬─────────────┘         └────────────┬─────────────┘   │
│                 │                                    │                 │
│                 └──────────────► telemetry-net ◄─────┘                 │
│                            (Isolated Bridge)                           │
└────────────────────────────────────────────────────────────────────────┘

```

---

## Technology Stack

* **Execution Runtime:** Python 3.12 (CPython), Docker (OCI Hardened Multi-Stage Build), Docker Compose
* **Asynchronous Web Engine:** FastAPI, Uvicorn, WebSockets (Port 8050)
* **Local Persistence Tier:** SQLite 3 with Write-Ahead Logging (WAL Mode), SQLModel, SQLAlchemy 2.0
* **Serialization & Wire Protocol:** Google Protocol Buffers v3 (Protobuf), in-memory GZIP stream compression
* **Cloud Infrastructure (AWS):** Amazon S3 (Server-Side Encryption AES-256, 7-Day Auto-Purge Lifecycle), AWS IAM (Write-Blind Principle of Least Privilege)
* **Quality Assurance:** Pytest, Pytest-Asyncio, HTTPX, Boto3 Mock Testing Harness

---

## Security & DevSecOps Architecture

* **Non-Root Runtime Sandbox:** Container runtime permanently drops root authority to `USER 10001` (`appuser:appgroup`), completely neutralizing container escape attack surfaces.
* **Zero-Secret Image Construction:** AWS credentials and API keys are strictly excluded from container images. Cloud authentication is handled via unprivileged read-only host volume bind mounts (`~/.aws:/home/appuser/.aws:ro`).
* **Write-Blind Cloud Perimeter:** Cloud synchronization operates under an IAM policy granting exclusively `s3:PutObject`. The edge node is mathematically barred from reading, listing, or deleting historical cloud archives (`s3:GetObject`, `s3:ListBucket` denied).
* **Air-Gapped Wheelhouse:** Production container layers install dependencies locally from an offline builder cache using `--no-index`, eliminating public network egress during container build time.
* **Rust / PyO3 ABI3 Shield:** Injects `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` during build time to ensure deterministic C-extension compilation across minor Python releases.

---

## Sprint Progression & Engineering Milestones

### Sprint 1: Relational Persistence Tier & Dynamic Engine Factory
* Engineered single-file SQLite database (`production_node.db`) separating persistent configuration data (`node_configurations`) from high-frequency volatile telemetry (`telemetry_ingress_queue`).
* Implemented lazy-evaluated factory pattern (`get_engine()`) with connection event listeners forcing Write-Ahead Logging (`PRAGMA journal_mode=WAL;`), a 64MB memory-mapped page cache, and a 60,000ms busy timeout to prevent write-lock collisions.

### Sprint 2: Asynchronous Multi-Threaded Concurrency Core
* Decoupled 20 Hz kinematic coordinate generation from filesystem I/O using a dual-threaded conductor (`src/conductor_host.py`).
* Implemented bounded memory airlock using `queue.Queue(maxsize=100)` with non-blocking `put_nowait()` drop-on-overflow backpressure protection.

### Sprint 3: Protocol Buffers (Protobuf v3) Binary Serialization
* Authored `proto/telemetry_schema.proto` defining `ArmKinematics` and `TelemetrySnapshot` envelopes with IEEE 754 32-bit float precision.
* Locked field tags with `reserved 7, 8;` to guarantee wire-level backward and forward compatibility.

### Sprint 4: Asynchronous ASGI Web Control Plane
* Deployed FastAPI/Uvicorn ASGI server on Port 8050 providing `/health` diagnostic endpoints and full-duplex WebSockets (`/ws/telemetry`) streaming deserialized JSON at 20 Hz.

### Sprint 5: Hardened Multi-Stage Containerization Baseline
* Architected a two-stage Dockerfile separating compiler tools (`gcc`, `make`) in Stage 1 from the minimal runtime image in Stage 2.
* Configured POSIX permission segmentation: immutable code directory (`chmod 555 /app/src`) and isolated persistent database volume (`chmod 770 /app/storage`).

### Sprint 9: AWS S3 Cloud Landing Zone & Resilient Egress Daemon
* Provisioned private AWS S3 bucket with 7-day auto-purge expiration rules ensuring $0.00 OpEx.
* Implemented out-of-band `CloudSyncWorker` (`src/cloud_sync.py`) featuring a hybrid flush trigger ($N \ge 50$ rows or $\Delta t \ge 30.0$ seconds).
* Engineered 4-byte big-endian framing length headers for in-memory delta-GZIP compaction (`.pb.gz`).
* Built a three-phase transactional state machine (`PENDING` $\to$ `PROCESSING` $\to$ `SYNCED`), automated crash-in-flight orphan recovery, and a 3-strike circuit breaker.

### Sprint 10: Multi-Container Orchestration & System Packaging
* Orchestrated multi-service composition (`docker-compose.yml`) linking `control-plane` and `cloud-sync` across an isolated software bridge network (`telemetry-net`).
* Implemented dependency supervision (`condition: service_healthy`) and self-healing schema creation to eliminate cold-boot database race conditions.

---

## Quickstart & Verification

### 1. Prerequisites
* Docker Engine 24.0+ and Docker Compose v2+
* Python 3.12+ (for local development)
* AWS CLI configured on host with an unprivileged S3 writer profile

### 2. Environment Configuration
Create a `.env` file in the project root:
```bash
cp .env.example .env
# Set your target bucket name and AWS region

```

### 3. Build & Deploy Multi-Container Stack

```bash
docker compose up -d

```

### 4. Health & Pipeline Verification

```bash
# Check container status and supervisor health
docker compose ps

# Audit local ASGI health probe
curl -i http://localhost:8050/health

# Inspect background cloud synchronization logs
docker compose logs cloud-sync --tail 25

```


---

### Step 4: Create `.env.example`

In `~/AutoRoboticArms/Cloud/`, create a sanitized environment template so external users know what configuration variables are required without seeing your real cloud identifiers:

```bash
cat <<EOF > ~/AutoRoboticArms/Cloud/.env.example
# AWS S3 Telemetry Lake Configuration
BUCKET_NAME=your-s3-telemetry-bucket-name
AWS_DEFAULT_REGION=us-east-1
TELEMETRY_STORAGE_DIR=/app/storage
EOF

```