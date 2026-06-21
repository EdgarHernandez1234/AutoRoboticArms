import math

# ---------------------------------------------------------
# 1. PHYSICAL HARDWARE CONSTANTS
# ---------------------------------------------------------
# Sourced directly from Gavin's mechanical blueprint (in centimeters)
L1 = 12.0  # Length of the main shoulder linkage
L2 = 10.0  # Length of the forearm linkage

# ---------------------------------------------------------
# 2. CUSTOM EXCEPTION DEFINITIONS
# ---------------------------------------------------------
class WorkspaceEnvelopeViolation(Exception):
    """
    Exception raised when a requested (X, Y, Z) coordinate lies 
    outside the physical reach of the mechatronic linkages.
    """
    pass

# ---------------------------------------------------------
# 3. KINEMATIC SOLVER ENGINE
# ---------------------------------------------------------
def calculate_joint_angles(x: float, y: float, z: float) -> dict:
    """
    Transforms 3D Cartesian coordinates into 3-Axis joint telemetry.
    Returns a dictionary of safe, constrained servo integer angles (0-180).
    """
    
    # 1. Base Yaw Calculation (The Horizontal Plane)
    # math.atan2 handles all 4 spatial quadrants safely
    base_rad = math.atan2(y, x)
    
    # Calculate the straight-line radial distance from the base origin
    xy_radius = math.sqrt(x**2 + y**2)
    
    # Calculate the 3D hypotenuse (direct line from shoulder pivot to target)
    distance_squared = xy_radius**2 + z**2
    distance = math.sqrt(distance_squared)

    # 2. Safety Perimeter Assertion (Boundary Value Analysis)
    # The arm cannot reach further than its two links laid flat, 
    # nor fold tighter than their physical difference.
    if distance > (L1 + L2) or distance < abs(L1 - L2):
        raise WorkspaceEnvelopeViolation(
            f"Target ({x}, {y}, {z}) breached safety envelope. Distance: {distance:.2f}cm"
        )

    # 3. Elbow Pitch Calculation (Law of Cosines)
    # c^2 = a^2 + b^2 - 2ab*cos(C)
    cos_elbow_angle = (distance_squared - L1**2 - L2**2) / (2 * L1 * L2)
    
    # Clamp float precision drift safely before acos to prevent math domain errors
    cos_elbow_angle = max(-1.0, min(1.0, cos_elbow_angle)) 
    elbow_rad = math.acos(cos_elbow_angle)

    # 4. Shoulder Pitch Calculation (Geometric Projection)
    # The shoulder must point at the target, then compensate for the elbow's drop
    alpha = math.atan2(z, xy_radius)
    beta = math.atan2(L2 * math.sin(elbow_rad), L1 + L2 * math.cos(elbow_rad))
    shoulder_rad = alpha + beta

    # 5. Radians to Degrees Conversion
    base_deg = math.degrees(base_rad)
    shoulder_deg = math.degrees(shoulder_rad)
    elbow_deg = math.degrees(elbow_rad)

    # 6. Actuator Calibration & Constraint Mapping
    # Standard hobby servos expect inputs between 0 and 180 degrees.
    # (Assuming 90 degrees is the default 'rest' / forward position)
    
    mapped_base = 90 + base_deg  # Offset so straight ahead is 90
    
    def clamp_angle(angle: float) -> int:
        return max(0, min(180, int(round(angle))))

    return {
        "base": clamp_angle(mapped_base),
        "shoulder": clamp_angle(shoulder_deg),
        "elbow": clamp_angle(elbow_deg)
    }

# ---------------------------------------------------------
# 4. LOCAL MODULE TESTING
# ---------------------------------------------------------
if __name__ == "__main__":
    # If run standalone, execute a quick math continuity check
    print("Testing Nominal Coordinate (0, 10, 10)...")
    try:
        angles = calculate_joint_angles(0.0, 10.0, 10.0)
        print(f"Success! Motor Targets: {angles}")
    except WorkspaceEnvelopeViolation as e:
        print(f"Failed: {e}")