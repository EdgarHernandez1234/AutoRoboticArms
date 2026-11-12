"""
train_ppo.py
Stable-Baselines3 PPO Training Pipeline for AutoRoboticArmEnv.
Trains a continuous reaching policy in simulation and saves best model weights.
"""

import os
import sys
import time
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from stable_baselines3.common.monitor import Monitor

# Ensure project root is on sys.path for rl_env imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)

from rl_env.arm_env import AutoRoboticArmEnv

# --- TRAINING CONFIGURATION ---
TOTAL_TIMESTEPS = 150_000
N_ENVS = 4
EVAL_FREQ = 10_000
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
TB_LOG_DIR = os.path.join(os.path.dirname(__file__), "tensorboard_logs")


def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(TB_LOG_DIR, exist_ok=True)

    print(f"[*] Initializing {N_ENVS} vectorized AutoRoboticArmEnv instances...")
    train_env = make_vec_env(AutoRoboticArmEnv, n_envs=N_ENVS, seed=42)
    eval_env = Monitor(AutoRoboticArmEnv())

    # Save best performing policy based on mean evaluation reward
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=MODELS_DIR,
        log_path=MODELS_DIR,
        eval_freq=max(EVAL_FREQ // N_ENVS, 1),
        n_eval_episodes=20,
        deterministic=True,
        render=False,
    )

    # Periodic safety checkpoints
    checkpoint_callback = CheckpointCallback(
        save_freq=max(50_000 // N_ENVS, 1),
        save_path=MODELS_DIR,
        name_prefix="ppo_arm_checkpoint",
    )

    # Initialize PPO Agent with a compact [64, 64] MLP ideal for 3-DoF CPU training
    model = PPO(
        policy="MlpPolicy",
        env=train_env,
        learning_rate=3e-4,
        n_steps=1024,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.005,
        policy_kwargs=dict(net_arch=[64, 64]),
        tensorboard_log=TB_LOG_DIR,
        device="cpu",
        verbose=1,
        seed=42,
    )

    print(f"[*] Starting PPO training for {TOTAL_TIMESTEPS:,} timesteps on CPU...")
    start_time = time.time()

    model.learn(
        total_timesteps=TOTAL_TIMESTEPS,
        callback=[eval_callback, checkpoint_callback],
        progress_bar=False,
    )

    elapsed = time.time() - start_time
    final_model_path = os.path.join(MODELS_DIR, "ppo_arm_final")
    model.save(final_model_path)

    print(f"\n[PASS] Training complete in {elapsed:.1f} seconds!")
    print(f"[*] Final model saved to: {final_model_path}.zip")
    print(f"[*] Best evaluation model saved to: {os.path.join(MODELS_DIR, 'best_model.zip')}")

    train_env.close()
    eval_env.close()


if __name__ == "__main__":
    main()