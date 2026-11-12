"""
evaluate_policy.py
Evaluates trained PPO weights on AutoRoboticArmEnv across randomized 3D targets.
"""

import os
import sys
import numpy as np
from stable_baselines3 import PPO

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)

from rl_env.arm_env import AutoRoboticArmEnv

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "best_model.zip")


def evaluate(num_episodes: int = 50):
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Trained model not found at {MODEL_PATH}. Run train_ppo.py first.")

    print(f"[*] Loading trained policy from: {MODEL_PATH}")
    model = PPO.load(MODEL_PATH, device="cpu")
    env = AutoRoboticArmEnv()

    successes = 0
    final_distances = []
    episode_lengths = []
    episode_rewards = []

    for ep in range(num_episodes):
        obs, info = env.reset(seed=1000 + ep)
        terminated = False
        truncated = False
        steps = 0
        total_reward = 0.0

        while not (terminated or truncated):
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            steps += 1

        if info["is_success"]:
            successes += 1
        final_distances.append(info["distance_cm"])
        episode_lengths.append(steps)
        episode_rewards.append(total_reward)

    success_rate = (successes / num_episodes) * 100.0
    mean_dist = float(np.mean(final_distances))
    mean_steps = float(np.mean(episode_lengths))
    mean_reward = float(np.mean(episode_rewards))

    print("\n--- PPO Policy Evaluation Summary ---")
    print(f"Episodes Evaluated   : {num_episodes}")
    print(f"Success Rate (<0.5cm): {success_rate:.1f}% ({successes}/{num_episodes})")
    print(f"Mean Final Error     : {mean_dist:.3f} cm")
    print(f"Mean Episode Steps   : {mean_steps:.1f} steps")
    print(f"Mean Episode Reward  : {mean_reward:.2f}")

if __name__ == "__main__":
    evaluate(num_episodes=50)