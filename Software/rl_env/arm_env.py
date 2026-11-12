"""
arm_env.py
Custom Farama Gymnasium Environment for the 3-Axis AutoRoboticArms.
Simulates joint kinematics, workspace bounds, and target reaching dynamics.
"""

import sys
import os
import math
from typing import Optional, Tuple, Dict, Any

import numpy as np
import gymnasium as gym
from gymnasium import spaces

# Allow importing forward_kinematics from edge-orchestrator
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "edge-orchestrator"))
)
from forward_kinematics import compute_forward_kinematics, JOINT_LIMITS


class AutoRoboticArmEnv(gym.Env):
    """
    3-DoF Robotic Arm Reaching Environment.
    Goal: Move the end-effector from a starting pose to a randomized 3D target
    within the safe physical workspace envelope.
    """

    metadata = {"render_modes": ["human", "ansi"], "render_fps": 30}

    def __init__(
        self,
        render_mode: Optional[str] = None,
        max_steps: int = 150,
        max_delta_deg: float = 5.0,
        goal_tolerance_cm: float = 0.5,
    ):
        super().__init__()
        self.render_mode = render_mode
        self.max_steps = max_steps
        self.max_delta_deg = max_delta_deg
        self.goal_tolerance_cm = goal_tolerance_cm

        # Joint limits arrays
        self.joint_low = np.array(
            [
                JOINT_LIMITS["base"][0],
                JOINT_LIMITS["shoulder"][0],
                JOINT_LIMITS["elbow"][0],
            ],
            dtype=np.float32,
        )
        self.joint_high = np.array(
            [
                JOINT_LIMITS["base"][1],
                JOINT_LIMITS["shoulder"][1],
                JOINT_LIMITS["elbow"][1],
            ],
            dtype=np.float32,
        )

        # Action Space: Normalized angular velocity / step delta [-1.0, 1.0]^3
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(3,), dtype=np.float32
        )

        # Observation Space (9D):
        # [norm_j1, norm_j2, norm_j3, curr_x, curr_y, curr_z, err_x, err_y, err_z]
        obs_low = np.array(
            [-1.0, -1.0, -1.0, -25.0, -25.0, -5.0, -50.0, -50.0, -50.0],
            dtype=np.float32,
        )
        obs_high = np.array(
            [1.0, 1.0, 1.0, 25.0, 25.0, 25.0, 50.0, 50.0, 50.0],
            dtype=np.float32,
        )
        self.observation_space = spaces.Box(
            low=obs_low, high=obs_high, dtype=np.float32
        )

        # Internal state
        self.current_joints = np.array([90.0, 90.0, 90.0], dtype=np.float32)
        self.target_xyz = np.array([10.0, 0.0, 12.0], dtype=np.float32)
        self.current_xyz = np.array([10.0, 0.0, 12.0], dtype=np.float32)
        self.step_count = 0

    def _sample_valid_target(self) -> np.ndarray:
        """
        Samples a guaranteed reachable 3D target point inside the safe workspace
        by sampling valid random joint angles and computing FK.
        """
        while True:
            rand_base = self.np_random.uniform(30.0, 150.0)
            rand_shoulder = self.np_random.uniform(45.0, 135.0)
            rand_elbow = self.np_random.uniform(45.0, 135.0)
            x, y, z = compute_forward_kinematics(rand_base, rand_shoulder, rand_elbow)
            r_xy = math.hypot(x, y)
            # Enforce physical workspace safety envelope (above table surface, inside max reach)
            if 3.0 <= z <= 19.0 and 5.0 <= r_xy <= 19.5 and x >= 2.0:
                return np.array([x, y, z], dtype=np.float32)

    def _get_obs(self) -> np.ndarray:
        # Normalize joint angles to [-1, 1]
        norm_joints = (
            2.0
            * (self.current_joints - self.joint_low)
            / (self.joint_high - self.joint_low)
            - 1.0
        )
        error_xyz = self.target_xyz - self.current_xyz
        return np.concatenate([norm_joints, self.current_xyz, error_xyz]).astype(
            np.float32
        )

    def _get_info(self) -> Dict[str, Any]:
        dist = float(np.linalg.norm(self.target_xyz - self.current_xyz))
        return {
            "distance_cm": round(dist, 4),
            "current_joints": self.current_joints.tolist(),
            "current_xyz": self.current_xyz.tolist(),
            "target_xyz": self.target_xyz.tolist(),
            "is_success": bool(dist <= self.goal_tolerance_cm),
        }

    def reset(
        self, *, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        super().reset(seed=seed)
        self.step_count = 0

        # Reset arm to neutral L-pose (90, 90, 90)
        self.current_joints = np.array([90.0, 90.0, 90.0], dtype=np.float32)
        fk = compute_forward_kinematics(*self.current_joints)
        self.current_xyz = np.array(fk, dtype=np.float32)

        # Sample a reachable target coordinate
        if options and "target_xyz" in options:
            self.target_xyz = np.array(options["target_xyz"], dtype=np.float32)
        else:
            self.target_xyz = self._sample_valid_target()

        return self._get_obs(), self._get_info()

    def step(
        self, action: np.ndarray
    ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        self.step_count += 1
        action = np.clip(action, -1.0, 1.0)

        # Apply angular deltas and clamp to hardware joint limits
        delta_deg = action * self.max_delta_deg
        new_joints = np.clip(
            self.current_joints + delta_deg, self.joint_low, self.joint_high
        )

        # Check if joint limit was hit (penalize boundary slamming)
        hit_joint_limit = not np.allclose(self.current_joints + delta_deg, new_joints)
        self.current_joints = new_joints

        # Compute new end-effector position via Forward Kinematics
        fk = compute_forward_kinematics(*self.current_joints)
        self.current_xyz = np.array(fk, dtype=np.float32)

        # Euclidean distance to target
        dist_cm = float(np.linalg.norm(self.target_xyz - self.current_xyz))

        # --- REWARD COMPUTATION ---
        # 1. Dense distance penalty
        reward = -dist_cm
        # 2. Action smoothness penalty (discourages jitter)
        reward -= 0.05 * float(np.sum(np.square(action)))
        # 3. Joint limit boundary penalty
        if hit_joint_limit:
            reward -= 1.0

        terminated = False
        truncated = False

        # Check workspace floor collision (table surface safety guard z < 2.0 cm)
        if self.current_xyz[2] < 2.0:
            reward -= 50.0
            truncated = True

        # Check terminal goal reach success
        if dist_cm <= self.goal_tolerance_cm:
            reward += 100.0
            terminated = True

        # Check episode horizon timeout
        if self.step_count >= self.max_steps:
            truncated = True

        if self.render_mode == "ansi":
            print(self.render())

        return self._get_obs(), float(reward), terminated, truncated, self._get_info()

    def render(self) -> Optional[str]:
        if self.render_mode == "ansi":
            dist = float(np.linalg.norm(self.target_xyz - self.current_xyz))
            return (
                f"Step {self.step_count:03d} | "
                f"Joints: {np.round(self.current_joints, 1).tolist()} | "
                f"XYZ: {np.round(self.current_xyz, 2).tolist()} | "
                f"Dist: {dist:.2f} cm"
            )
        return None