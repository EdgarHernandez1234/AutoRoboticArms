# AutoRoboticArms — Software Layer: Hardened Edge Control Plane & Embodied AI Node

**Software Layer** is the containerized local edge control plane, perimeter security gateway, and Reinforcement Learning (RL) sim-to-real execution stack for the **AutoRoboticArms** 3-DoF robotic manipulator.

It bridges high-level autonomous policies and browser operators on a workstation with deterministic, real-time serial actuation on an Ubuntu edge server connected to an ATmega328P / PCA9685 servo controller.

---

## Architecture Overview

```text
┌─────────────────────────────────────┐         LAN (HTTP / WS :80)         ┌───────────────────────────────────────────────────────────┐
│   MacBook Workstation (Client)      │ ──────────────────────────────────► │             Ubuntu Server (Edge Control Node)             │
│                                     │                                     │                                                           │
│  • Gymnasium + PPO Policy Training  │  POST /api/v1/trajectory (X-API-Key)│  ┌─────────────────────────────────────────────────────┐  │
│  • deploy_sim2real.py Rollout CLI   │ ──────────────────────────────────► │  │ auto-robotic-perimeter (nginx:1.27-alpine :80)      │  │
│  • Live Browser Telemetry Dashboard │ ◄────────────────────────────────── │  │  • Rate Limiting (15r/s REST, 5r/s WS)              │  │
│                                     │      WS /ws/telemetry (20 Hz)       │  │  • Security Headers & Static Dashboard Hosting      │  │
└─────────────────────────────────────┘                                     │  └──────────────────────────┬──────────────────────────┘  │
                                                                            │                             │ internal_isolated_bridge    │
                                                                            │                             ▼                             │
                                                                            │  ┌─────────────────────────────────────────────────────┐  │
                                                                            │  │ auto-robotic-orchestrator (FastAPI + Uvicorn :8000) │  │
                                                                            │  │  • X-API-Key Auth Gate & Pydantic Bounds Validation │  │
                                                                            │  │  • 3-DoF Analytical IK / FK & Trajectory Planner    │  │
                                                                            │  │  • 20 Hz Slew-Limited Serial Loop (/dev/ttyACM0)    │  │
                                                                            │  │  • Async SQLite WAL Telemetry Persistence           │  │
                                                                            │  └──────────────────────────┬──────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┼─────────────────────────────┼─────────────────────────────┘
                                                                                                          │ USB Serial (115200 Baud)
                                                                                                          ▼
                                                                                       ATmega328P + PCA9685 (3-DoF Arm)

```

### Key Engineering Features

* **Network-Airlocked Perimeter Security:** NGINX (`auto-robotic-perimeter`) binds exclusively to Port `80`, rate-limiting traffic and proxying requests across a private Docker bridge (`internal_isolated_bridge`) to an unexposed FastAPI backend (`auto-robotic-orchestrator`).
* **Constant-Time API Key Gate:** All actuation and state-mutating endpoints (`POST /api/v1/trajectory`, `POST /api/v1/cartesian`, `POST /api/v1/estop`) require a valid `X-API-Key` header verified via `secrets.compare_digest`, while read-only health and WebSocket telemetry remain accessible for real-time monitoring.
* **Dual-Thread Real-Time Determinism:** Isolates the 20 Hz serial UART loop (`Thread 1`, enforcing a $2^\circ/\text{tick}$ slew-rate limiter, `@DRV` XOR checksum framing, and 3000 ms watchdog heartbeats) from the asynchronous FastAPI/WebSocket server (`Thread 2`) using a bounded thread-safe `collections.deque` FIFO queue.
* **Analytical 3-DoF Kinematics & Safety Envelope:** Validates all waypoints against physical link invariants ($L_1 = 12.0\,\text{cm}$, $L_2 = 10.0\,\text{cm}$) and spherical workspace boundaries ($2.5\,\text{cm} \le r \le 21.5\,\text{cm}$) before committing trajectories, rejecting out-of-bounds targets atomically with `HTTP 422`.
* **Gymnasium RL Sandbox & Sim-to-Real Bridge:** Includes a custom Farama Gymnasium environment (`AutoRoboticArmEnv`) and a Stable-Baselines3 PPO policy trained to **98.0% reach accuracy** ($0.30\,\text{cm}$ mean error) that deploys trajectories directly over HTTP to the physical arm.
* **Zero-Dependency Operator Dashboard:** Real-time browser UI displaying live joint angles, 3D forward-kinematics end-effector coordinates, queue backlog, hardware `ACK` status, authenticated target dispatch, and a hardware `E-STOP` trigger.

---

## Repository Structure

```text
Software/
├── docker-compose.yml              # Multi-container orchestration (NGINX perimeter + FastAPI node)
├── .env.example                    # Template for CONTROL_PLANE_API_KEY & serial configuration
├── nginx/
│   └── nginx.conf                  # Reverse proxy, rate-limiting zones, security headers & WS upgrade map
├── edge-orchestrator/
│   ├── Dockerfile                  # Multi-stage unprivileged runtime (UID 10001, dialout GID 20)
│   ├── requirements.txt            # Pinned FastAPI, Uvicorn, Pydantic, and PySerial dependencies
│   ├── orchestrator_node.py        # Dual-thread FastAPI server, serial worker, & WebSocket hub
│   ├── kinematics.py               # Analytical 3-DoF Inverse Kinematics & workspace envelope checks
│   ├── forward_kinematics.py       # 3-DoF Forward Kinematics projection (angles -> X, Y, Z)
│   ├── trajectory.py               # Linear Cartesian path discretization (0.5 cm step resolution)
│   └── database_manager.py         # Asynchronous SQLite WAL micro-batch telemetry writer
├── dashboard/
│   ├── index.html                  # Operator control & live telemetry dashboard markup
│   ├── styles.css                  # Responsive dark-mode grid & status indicator styling
│   └── app.js                      # Full-duplex WebSocket client & authenticated REST dispatcher
├── rl_env/
│   └── arm_env.py                  # Custom Farama Gymnasium environment (AutoRoboticArmEnv)
├── rl_training/
│   ├── train_ppo.py                # Multi-worker Stable-Baselines3 PPO training script
│   ├── evaluate_policy.py          # Deterministic policy benchmark & metrics evaluator
│   └── deploy_sim2real.py          # Sim-to-real rollout client targeting Port 80 REST ingress
├── scripts/
│   ├── servo_calibration.py        # CLI bench tool for homing and PWM limit verification
│   └── run_trajectory_demo.py      # Multi-waypoint physical load test script
├── tests/
│   ├── test_kinematics.py          # IK boundary value & singularity unit tests
│   ├── test_trajectory.py          # Path interpolation & envelope breach tests
│   ├── test_orchestrator_node.py   # Mock serial, queue backpressure, & API endpoint tests
│   └── test_arm_env.py             # Gymnasium API compliance & reward shaping tests
└── data/                           # Host bind-mount for persistent SQLite WAL database (telemetry.db)

```

---

## Hardware & Network Topology

| Node | Role | Interfaces & Services |
| --- | --- | --- |
| **Ubuntu Server** | Headless Edge Control Node | • USB Serial `/dev/ttyACM0` (`115200` baud) to ATmega328P<br>

<br>• `auto-robotic-perimeter` (`nginx:1.27-alpine` on Port `80`)<br>

<br>• `auto-robotic-orchestrator` (Uvicorn on isolated Port `8000`)<br>

<br>• Persistent SQLite WAL store (`./data/telemetry.db`) |
| **MacBook Workstation** | AI Training & Operator Client | • Isolated Python 3.11 `.venv` (PyTorch, Gymnasium, Stable-Baselines3)<br>

<br>• PPO training (`train_ppo.py`) & sim-to-real CLI (`deploy_sim2real.py`)<br>

<br>• Browser operator console (`http://<UBUNTU_IP>/`) |

---

## Quickstart & Deployment

### 1. Ubuntu Server (Edge Control Stack)

1. **Configure environment variables & host storage permissions:**
```bash
cd optionb
cp .env.example .env
# Edit .env and set a strong CONTROL_PLANE_API_KEY

mkdir -p data
sudo chown -R 10001:10001 data

```


2. **Build and launch the containerized stack:**
```bash
docker compose up -d --build
docker compose ps

```


3. **Verify health & perimeter airlock:**
```bash
# Should return HTTP 200 OK with status: NOMINAL
curl -i [http://127.0.0.1/api/v1/health](http://127.0.0.1/api/v1/health)

# Should fail with Connection Refused (internal bridge isolation)
curl -i [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

```



---

### 2. MacBook Workstation (Operator Dashboard & RL Rollout)

1. **Open the Live Telemetry Dashboard:**
Navigate to `http://<UBUNTU_LAN_IP>/` in your browser. The WebSocket telemetry stream (`WS: CONNECTED`) attaches automatically; enter your `CONTROL_PLANE_API_KEY` in the **Perimeter Command Gate** card to dispatch coordinates or trigger **E-STOP**.
2. **Run a Sim-to-Real PPO Policy Rollout:**
```bash
source .venv/bin/activate
python rl_training/deploy_sim2real.py \
  --host <UBUNTU_LAN_IP> \
  --port 80 \
  --api-key <YOUR_CONTROL_PLANE_API_KEY> \
  --x 12.0 --y 5.0 --z 8.0 \
  --return-home

```



---

## API Reference

| Method | Endpoint | Auth Required | Description |
| --- | --- | --- | --- |
| `GET` | `/api/v1/health` | No | Returns node health, serial bus status, watchdog state, and queue depth. |
| `WS` | `/ws/telemetry` | No | Streams 20 Hz JSON telemetry frames (`joints`, `cartesian`, `hardware_ack`, `queue_backlog`). |
| `POST` | `/api/v1/trajectory` | `X-API-Key` | Discretizes a list of 3D Cartesian waypoints (`0.5 cm` steps), validates IK bounds, and enqueues atomically. |
| `POST` | `/api/v1/cartesian` | `X-API-Key` | Moves the end-effector to a single validated `(x, y, z)` target coordinate. |
| `POST` | `/api/v1/estop` | `X-API-Key` | Immediately flushes the motion queue and latches the hardware `SAFE_HOLD` state. |

---

## Running the Automated Test Suite

```bash
pytest -v

```

Validates 3-DoF analytical kinematics, linear trajectory interpolation, queue backpressure guards, API authentication/error codes, and Gymnasium environment compliance.