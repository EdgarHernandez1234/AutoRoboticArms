"""
kinematics.py
Stateless analytical 3-DoF geometric Inverse Kinematics (IK) engine.
Maps Cartesian task-space coordinates (X, Y, Z) into bounded joint angles.
"""

import math

# -----------------------------------------------------------------------------
# PHYSICAL LINK CONSTANTS & OPERATIONAL REACH BOUNDS
# -----------------------------------------------------------------------------
# Pivot-to-pivot pitch measurements in centimeters
L1 = 12.0  # Main shoulder-to-elbow linkage
L2 = 10.0  # Forearm elbow-to-wrist linkage

# Cushioned spherical reach boundaries to prevent singular leverage & binding
SAFE_MIN_REACH = 2.5  # |L1 - L2| + 0.5 cm defensive buffer
SAFE_MAX_REACH = 21.5  # (L1 + L2) - 0.5 cm defensive buffer


class WorkspaceEnvelopeViolation(Exception):
    """
    Raised when requested Cartesian (X, Y, Z) coordinates breach the physical
    spherical reach envelope or approach mechanical singularity boundaries.
    """
    pass


def calculate_joint_angles(x: float, y: float, z: float) -> dict:
    """
    Converts 3D Cartesian coordinates into 3-axis servo angles (0 - 180 degrees).
    
    Returns:
        dict: {"base": int, "shoulder": int, "elbow": int}
        
    Raises:
        WorkspaceEnvelopeViolation: If target is out of the safe reach envelope.
    """
    # 1. Base Yaw Calculation (Horizontal X-Y Plane)
    # atan2 evaluates all 4 spatial quadrants safely and eliminates zero-division
    base_rad = math.atan2(y, x)
    xy_radius = math.sqrt(x**2 + y**2)

    # 2. 3D Euclidean Distance (Shoulder Pivot to End-Effector)
    distance_squared = xy_radius**2 + z**2
    distance = math.sqrt(distance_squared)

    # 3. Spatial Boundary Check (Boundary Value Analysis Pre-Filter)
    if distance > SAFE_MAX_REACH or distance < SAFE_MIN_REACH:
        raise WorkspaceEnvelopeViolation(
            f"Target coordinate ({x:.2f}, {y:.2f}, {z:.2f}) breaches physical envelope. "
            f"Spherical distance: {distance:.2f} cm (Allowed: {SAFE_MIN_REACH} cm - {SAFE_MAX_REACH} cm)"
        )

    # 4. Elbow Pitch Calculation (Law of Cosines)
    # distance^2 = L1^2 + L2^2 - 2*L1*L2*cos(elbow)
    cos_elbow_angle = (distance_squared - L1**2 - L2**2) / (2.0 * L1 * L2)

    # Defensive Saturation Clamp: Absorbs IEEE-754 machine epsilon rounding
    # prevents ValueError: math domain error when distance is near boundaries
    cos_elbow_angle = max(-1.0, min(1.0, cos_elbow_angle))
    elbow_rad = math.acos(cos_elbow_angle)

    # 5. Shoulder Pitch Calculation (Geometric Projection & Elevation)
    # Alpha = elevation to direct target vector; Beta = elevation offset from elbow flexion
    alpha = math.atan2(z, xy_radius)
    beta = math.atan2(L2 * math.sin(elbow_rad), L1 + L2 * math.cos(elbow_rad))
    shoulder_rad = alpha + beta

    # 6. Convert Radians to Degrees
    base_deg = math.degrees(base_rad)
    shoulder_deg = math.degrees(shoulder_rad)
    elbow_deg = math.degrees(elbow_rad)

    # 7. Physical Servo Calibration Mapping & Saturation Clamping
    # Straight forward along the X-axis (x > 0, y = 0) aligns with base servo 90°
    mapped_base = 90.0 + base_deg

    def clamp_angle(val: float) -> int:
        return max(0, min(180, int(round(val))))

    return {
        "base": clamp_angle(mapped_base),
        "shoulder": clamp_angle(shoulder_deg),
        "elbow": clamp_angle(elbow_deg)
    }