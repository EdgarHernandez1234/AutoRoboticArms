"""
trajectory.py
Cartesian Linear Interpolation & Multi-Waypoint Trajectory Engine
for the 3-Axis AutoRoboticArms Platform.

Subdivides multi-waypoint 3D Cartesian paths into equidistant
spatial steps and evaluates IK continuity across the physical envelope.
"""

import math
from typing import List, Tuple, Dict
from kinematics import calculate_joint_angles, WorkspaceEnvelopeViolation


class TrajectoryPlanner:
    def __init__(self, step_size_cm: float = 0.5):
        """
        :param step_size_cm: Maximum Cartesian distance (in cm) between consecutive
                             interpolated intermediate path points.
        """
        if step_size_cm <= 0.0:
            raise ValueError("step_size_cm must be greater than zero.")
        self.step_size_cm = step_size_cm

    def interpolate_linear_segment(
        self, start: Tuple[float, float, float], end: Tuple[float, float, float]
    ) -> List[Tuple[float, float, float]]:
        """
        Computes an ordered list of equidistant 3D points connecting start to end.
        Guarantees that both start and end coordinates are included.
        """
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dz = end[2] - start[2]
        distance = math.sqrt(dx**2 + dy**2 + dz**2)

        if distance < 1e-6:
            return [start]

        num_segments = math.ceil(distance / self.step_size_cm)
        path = []

        for i in range(num_segments + 1):
            t = i / float(num_segments)
            px = start[0] + t * dx
            py = start[1] + t * dy
            pz = start[2] + t * dz
            path.append((round(px, 3), round(py, 3), round(pz, 3)))

        return path

    def plan_multi_waypoint_path(
        self, waypoints: List[Tuple[float, float, float]]
    ) -> List[Tuple[float, float, float]]:
        """
        Connects an ordered sequence of Cartesian waypoints into a continuous path.
        Eliminates duplicate seam points between adjacent segments.
        """
        if not waypoints:
            return []
        if len(waypoints) == 1:
            return [waypoints[0]]

        full_path = [waypoints[0]]

        for i in range(len(waypoints) - 1):
            segment = self.interpolate_linear_segment(waypoints[i], waypoints[i + 1])
            # Exclude the first point of subsequent segments to avoid duplicate waypoints
            full_path.extend(segment[1:])

        return full_path

    def generate_joint_trajectory(
        self, waypoints: List[Tuple[float, float, float]]
    ) -> List[Tuple[int, int, int]]:
        """
        Converts a Cartesian waypoint path into an atomically-verified sequence
        of integer joint angle tuples: (base, shoulder, elbow).

        Raises WorkspaceEnvelopeViolation immediately if ANY intermediate step
        breaches the physical boundary, preventing partial execution.
        """
        cartesian_path = self.plan_multi_waypoint_path(waypoints)
        joint_trajectory: List[Tuple[int, int, int]] = []

        for pt in cartesian_path:
            # calculate_joint_angles validates workspace reach (2.5 cm - 21.5 cm)
            # and returns clamped integer joint angles
            angles = calculate_joint_angles(pt[0], pt[1], pt[2])
            joint_trajectory.append((angles["base"], angles["shoulder"], angles["elbow"]))

        return joint_trajectory