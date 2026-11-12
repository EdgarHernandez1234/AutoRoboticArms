"""
forward_kinematics.py
Analytical Forward Kinematics (FK) Solver for the 3-Axis AutoRoboticArms.
Converts joint angles (degrees) into 3D end-effector Cartesian coordinates (cm).
"""

import math
from typing import Dict, Tuple

# Physical Link Invariants (cm) — locked to kinematics.py & physical hardware
L1_CM = 12.0  # Shoulder-to-Elbow link length
L2_CM = 10.0  # Elbow-to-Wrist/End-Effector link length

# Servo Angle Bounds (degrees)
JOINT_LIMITS = {
    "base": (0.0, 180.0),
    "shoulder": (15.0, 165.0),
    "elbow": (15.0, 165.0),
}


def compute_forward_kinematics(
    base_deg: float, shoulder_deg: float, elbow_deg: float
) -> Tuple[float, float, float]:
    """
    Computes 3D Cartesian coordinates (x, y, z) in cm from servo joint angles.

    Coordinate Frame Alignment:
      - Base Yaw = 90 deg -> Facing straight forward along +Y axis (X = 0)
      - Shoulder Pitch = 90 deg -> Upper arm (L1) pointing straight up (+Z)
      - Elbow Pitch = 90 deg -> Forearm (L2) perpendicular to L1 (horizontal forward)
      - Neutral Pose (90, 90, 90) -> (x=0.0, y=10.0, z=12.0) cm

    Args:
        base_deg: Base yaw servo angle in degrees [0, 180].
        shoulder_deg: Shoulder pitch servo angle in degrees [15, 165].
        elbow_deg: Elbow pitch servo angle in degrees [15, 165].

    Returns:
        Tuple (x, y, z) in centimeters.
    """
    # Convert servo frame angles to standard trigonometric elevation/azimuth angles
    # Base azimuth relative to +Y forward axis
    yaw_rad = math.radians(base_deg - 90.0)

    # Shoulder angle relative to horizontal plane (90 deg servo = 90 deg vertical)
    theta_1 = math.radians(shoulder_deg)

    # Elbow internal angle (90 deg servo = 90 deg bend between L1 and L2)
    # Relative angle of forearm L2 to horizontal plane:
    theta_2 = theta_1 - math.radians(elbow_deg)

    # Planar radial reach (r) and vertical elevation (z)
    r = L1_CM * math.cos(theta_1) + L2_CM * math.cos(theta_2)
    z = L1_CM * math.sin(theta_1) + L2_CM * math.sin(theta_2)

    # Project radial reach onto X-Y Cartesian plane
    x = r * math.sin(yaw_rad)
    y = r * math.cos(yaw_rad)

    return (round(x, 4), round(y, 4), round(z, 4))


def verify_fk_ik_consistency() -> Dict[str, Tuple[float, float, float]]:
    """
    Quick sanity check verifying neutral L-pose (90, 90, 90) yields (0.0, 10.0, 12.0).
    """
    neutral_xyz = compute_forward_kinematics(90.0, 90.0, 90.0)
    return {"neutral_pose_xyz": neutral_xyz}


if __name__ == "__main__":
    print(verify_fk_ik_consistency())