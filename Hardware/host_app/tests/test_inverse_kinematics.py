import os
import sys
import pytest
import math
IK_main = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src"))

# Add the parent directory to the system path to add the main conductor file for unit testing
sys.path.append(IK_main)

from inverse_kinematics import calculate_joint_angles, WorkspaceEnvelopeViolation
# ---------------------------------------------------------
# TEST SUITE: INVERSE KINEMATICS & SPATIAL BOUNDARIES
# ---------------------------------------------------------

def test_nominal_coordinate_translation():
    """
    Test a standard, safe coordinate that is well within the arm's physical reach.
    Asserts that the IK solver returns a properly formatted dictionary of valid integers.
    """
    # Provide a safe spatial target (x=10.0, y=10.0, z=10.0)
    result = calculate_joint_angles(10.0, 10.0, 10.0)
    
    # 1. Verify the data contract shape
    assert isinstance(result, dict)
    assert "base" in result
    assert "shoulder" in result
    assert "elbow" in result
    
    # 2. Verify all calculated angles are clamped to safe 8-bit limits (0 to 180 degrees)
    assert 0 <= result["base"] <= 180
    assert 0 <= result["shoulder"] <= 180
    assert 0 <= result["elbow"] <= 180

def test_maximum_envelope_violation():
    """
    Boundary Value Analysis (BVA): Maximum Reach
    Gavin's physical design has a 12cm shoulder and 10cm forearm (Max Reach = 22cm).
    Commanding a 30cm reach should instantly trigger our custom software failsafe.
    """
    with pytest.raises(WorkspaceEnvelopeViolation) as exc_info:
        # Pushing the arm 30cm straight out on the X-axis
        calculate_joint_angles(30.0, 0.0, 0.0)
        
    # Verify the exception message correctly identifies the breach
    assert "breached safety envelope" in str(exc_info.value)

def test_minimum_envelope_violation():
    """
    Boundary Value Analysis (BVA): Minimum Reach
    The physical arm cannot fold into a space tighter than the difference 
    of its links (12cm - 10cm = 2cm minimum radius).
    Commanding a 1cm reach should trigger the failsafe to prevent mechanical binding.
    """
    with pytest.raises(WorkspaceEnvelopeViolation):
        # Pushing the target 1cm away from the origin
        calculate_joint_angles(1.0, 0.0, 0.0)

def test_origin_singularity_rejection():
    """
    Boundary Value Analysis (BVA): Absolute Zero
    Commanding the arm to enter its own physical base origin (0,0,0) is a mathematical 
    singularity for IK solvers and must be explicitly rejected by the envelope limits.
    """
    with pytest.raises(WorkspaceEnvelopeViolation):
        calculate_joint_angles(0.0, 0.0, 0.0)

# ---------------------------------------------------------
# ADVANCED MECHATRONICS INDUSTRY VERIFICATION HARNESS
# ---------------------------------------------------------

def test_floating_point_precision_clamping():
    """
    Precision Check: Asserts that our internal float-clamping guard prevents
    rounding drift from throwing a math domain error when links are fully stretched.
    Total maximum reach is exactly 22.0cm (12cm + 10cm).
    """
    # Placing target right on the knife-edge boundary of the reach
    try:
        result = calculate_joint_angles(22.0, 0.0, 0.0)
        
        # Verify the calculations return valid, clean numeric parameters
        assert isinstance(result["elbow"], int)
        assert not math.isnan(result["elbow"])
    except ValueError:
        pytest.fail("Math tracking engine suffered a floating-point domain crash!")

@pytest.mark.parametrize(
    "x, y, z, expected_base",
    [
        (10.0, 0.0, 5.0, 90),    # Target straight ahead -> Base angle must equal 90
        (0.0, 10.0, 5.0, 180),   # Target 90-degrees left -> Base angle must scale to 180
        (0.0, -10.0, 5.0, 0),    # Target 90-degrees right -> Base angle must scale to 0
    ]
)
def test_horizontal_plane_yaw_determinism(x, y, z, expected_base):
    """
    Singularity Check: Verifies math quadrant mapping using math.atan2.
    Enforces that base rotation maps perfectly across quadrant transitions.
    """
    angles = calculate_joint_angles(x, y, z)
    assert angles["base"] == expected_base

def test_integer_conversion_continuity():
    """
    Continuity Check: Verifies that fractional intermediate angles 
    round deterministically rather than shifting or truncating erratically.
    """
    # Test values that evaluate to tight boundaries
    case_a = calculate_joint_angles(10.123, 5.456, 7.89)
    case_b = calculate_joint_angles(10.124, 5.456, 7.89)
    
    # Structural positions must change incrementally without massive jumps
    assert abs(case_a["shoulder"] - case_b["shoulder"]) <= 1