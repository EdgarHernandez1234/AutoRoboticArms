"""
test_kinematics.py
Automated boundary value analysis (BVA) and mathematical regression tests
for Option B's 3-DoF geometric inverse kinematics solver.
"""

import math
import os
import sys
import pytest
host_main = os.path.abspath(os.path.join(os.path.dirname(__file__), "../orchestrator_node"))
sys.path.append(host_main)
from kinematics import (
    calculate_joint_angles,
    WorkspaceEnvelopeViolation,
    SAFE_MIN_REACH,
    SAFE_MAX_REACH,
    L1,
    L2
)


def test_nominal_forward_reach():
    """Validates nominal safe coordinates directly in front of the arm."""
    angles = calculate_joint_angles(10.0, 0.0, 10.0)
    assert 0 <= angles["base"] <= 180
    assert 0 <= angles["shoulder"] <= 180
    assert 0 <= angles["elbow"] <= 180
    # Y = 0 facing forward must yield base yaw at 90 degrees
    assert angles["base"] == 90


def test_base_yaw_quadrant_resolution():
    """Asserts that atan2 resolves positive and negative lateral quadrants cleanly."""
    # Target towards positive Y (left sweep)
    left_target = calculate_joint_angles(10.0, 5.0, 8.0)
    assert left_target["base"] > 90

    # Target towards negative Y (right sweep)
    right_target = calculate_joint_angles(10.0, -5.0, 8.0)
    assert right_target["base"] < 90


@pytest.mark.parametrize("x, y, z", [
    (25.0, 0.0, 0.0),       # Far over-extension (> 21.5 cm)
    (15.3, 15.3, 0.0),      # Diagonal over-extension (~21.64 cm)
    (0.5, 0.5, 0.5),        # Self-collision / too close (< 2.5 cm)
    (0.0, 0.0, 0.0),        # Origin singularity
    (0.0, 0.0, 22.5),       # Excessive vertical height
])
def test_workspace_envelope_rejections(x, y, z):
    """Verifies that unreachable coordinates raise WorkspaceEnvelopeViolation."""
    with pytest.raises(WorkspaceEnvelopeViolation):
        calculate_joint_angles(x, y, z)


def test_floating_point_domain_clamping():
    """
    Simulates a coordinate right on the boundary where IEEE-754 float precision
    could cause cos_elbow to compute as 1.0000000000000002 without domain clamping.
    """
    # Exact maximum boundary distance target (21.5 cm)
    # (12.413)^2 + (12.413)^2 + (12.413)^2 ≈ 21.5^2
    target_comp = 21.5 / math.sqrt(3)
    angles = calculate_joint_angles(target_comp, target_comp, target_comp)
    assert isinstance(angles["elbow"], int)
    assert 0 <= angles["elbow"] <= 180


def test_cushioned_boundary_values():
    """Tests points just inside and outside the cushioned limits."""
    # Just inside max boundary (21.4 cm) -> Should pass
    angles = calculate_joint_angles(21.4, 0.0, 0.0)
    assert isinstance(angles, dict)

    # Just outside max boundary (21.6 cm) -> Should fail
    with pytest.raises(WorkspaceEnvelopeViolation):
        calculate_joint_angles(21.6, 0.0, 0.0)

    # Just inside min boundary (2.6 cm) -> Should pass
    angles_min = calculate_joint_angles(2.6, 0.0, 0.0)
    assert isinstance(angles_min, dict)

    # Just outside min boundary (2.4 cm) -> Should fail
    with pytest.raises(WorkspaceEnvelopeViolation):
        calculate_joint_angles(2.4, 0.0, 0.0)