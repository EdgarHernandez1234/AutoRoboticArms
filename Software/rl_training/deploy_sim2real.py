"""
deploy_sim2real.py
Sim-to-Real Bridge: Rolls out trained PPO policy weights in simulation,
extracts the generated 3D Cartesian trajectory, and dispatches it atomically to
the hardened Option B edge orchestrator over HTTP.
"""

import os
import sys
import time
import argparse
import urllib.request
import urllib.error
import json
from typing import List, Tuple

import numpy as np
from stable_baselines3 import PPO

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)

from rl_env.arm_env import AutoRoboticArmEnv

DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "best_model.zip")


def http_get_json(url: str, timeout: float = 3.0) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url: str, payload: dict, api_key: str, timeout: float = 5.0) -> Tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="ignore")
        try:
            return err.code, json.loads(body)
        except json.JSONDecodeError:
            return err.code, {"detail": body}


def verify_orchestrator_health(base_url: str) -> dict:
    health_url = f"{base_url}/api/v1/health"
    print(f"[*] Checking edge orchestrator health at {health_url}...")
    health = http_get_json(health_url)
    if health.get("status") != "NOMINAL" or health.get("safe_hold_tripped", True):
        raise RuntimeError(f"Hardware gate rejected deployment! Health state: {health}")
    print(f"[PASS] Orchestrator NOMINAL | Current Pose: {health.get('current_pose')}")
    return health


def generate_policy_trajectory(
    model_path: str, target_xyz: Tuple[float, float, float]
) -> Tuple[List[dict], dict]:
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model weights not found at {model_path}")

    model = PPO.load(model_path, device="cpu")
    env = AutoRoboticArmEnv()

    obs, info = env.reset(options={"target_xyz": list(target_xyz)})
    waypoints = []

    # Record initial starting pose
    start_x, start_y, start_z = info["current_xyz"]
    waypoints.append({"x": round(start_x, 3), "y": round(start_y, 3), "z": round(start_z, 3)})

    terminated = False
    truncated = False

    while not (terminated or truncated):
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        cx, cy, cz = info["current_xyz"]
        waypoints.append({"x": round(cx, 3), "y": round(cy, 3), "z": round(cz, 3)})

    if not info["is_success"]:
        raise RuntimeError(
            f"Policy failed to reach target {target_xyz} in simulation "
            f"(final error: {info['distance_cm']:.3f} cm). Aborting hardware dispatch."
        )

    return waypoints, info


def wait_for_queue_drain(base_url: str, timeout_sec: float = 15.0) -> None:
    health_url = f"{base_url}/api/v1/health"
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        health = http_get_json(health_url)
        backlog = health.get("queue_backlog", 0)
        if health.get("safe_hold_tripped"):
            raise RuntimeError("Hardware safe-hold tripped mid-trajectory!")
        if backlog == 0:
            return
        time.sleep(0.25)
    raise TimeoutError("Timed out waiting for orchestrator queue to drain.")


def main():
    parser = argparse.ArgumentParser(description="Deploy trained PPO trajectory to Option B hardware")
    parser.add_argument("--host", type=str, default="localhost", help="Ubuntu Server IP or hostname")
    parser.add_argument("--port", type=int, default=8000, help="FastAPI orchestrator port")
    parser.add_argument("--x", type=float, default=5.0, help="Target X coordinate (cm)")
    parser.add_argument("--y", type=float, default=12.0, help="Target Y coordinate (cm)")
    parser.add_argument("--z", type=float, default=8.0, help="Target Z coordinate (cm)")
    parser.add_argument("--return-home", action="store_true", help="Return to neutral L-pose (10, 0, 12) after reaching target")
    parser.add_argument("--dry-run", action="store_true", help="Simulate policy trajectory without sending HTTP commands")
    parser.add_argument("--api-key",type=str,default=os.getenv("CONTROL_PLANE_API_KEY", "dev-local-perimeter-key"), help="X-API-Key token for edge orchestrator authentication",
)
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    target = (args.x, args.y, args.z)

    print(f"[*] Rolling out PPO policy toward target {target} cm...")
    waypoints, sim_info = generate_policy_trajectory(DEFAULT_MODEL_PATH, target)
    print(
        f"[PASS] Policy converged in {len(waypoints) - 1} steps | "
        f"Final Sim Error: {sim_info['distance_cm']:.3f} cm"
    )

    if args.return_home:
        waypoints.append({"x": 10.0, "y": 0.0, "z": 12.0})

    if args.dry_run:
        print("[DRY-RUN] Generated Cartesian Waypoints:")
        for idx, wp in enumerate(waypoints):
            print(f"  Step {idx:02d}: {wp}")
        return

    # 1. Check live hardware health gate
    verify_orchestrator_health(base_url)

    # 2. Dispatch trajectory batch to POST /api/v1/trajectory
    traj_url = f"{base_url}/api/v1/trajectory"
    payload = {"waypoints": waypoints, "step_size_cm": 0.5}
    print(f"[*] Dispatching {len(waypoints)} RL waypoints to {traj_url}...")
    status_code, resp_body = http_post_json(traj_url, payload, args.api_key)

    if status_code != 200:
        raise RuntimeError(f"Trajectory rejected (HTTP {status_code}): {resp_body}")

    print(f"[PASS] Enqueued {resp_body.get('total_steps')} interpolated steps on hardware.")

    # 3. Monitor execution until queue drains
    print("[*] Waiting for physical servo execution to complete...")
    time.sleep(0.5)
    wait_for_queue_drain(base_url)
    print("[PASS] Trajectory execution complete! Queue drained with NOMINAL status.")


if __name__ == "__main__":
    main()