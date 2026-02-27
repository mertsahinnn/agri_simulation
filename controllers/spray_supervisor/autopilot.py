"""
Autopilot Module
=================
Autonomous driving along crop rows with U-turns at row ends.

Uses a simple PID controller for steering and waypoint-based navigation.
The tractor follows predefined waypoints along crop rows, performing
U-turns at the end of each row to move to the next one.
"""
import sys
import os
import math
import logging

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import MAX_SPEED, MAX_STEERING, LOG_FORMAT, LOG_LEVEL

logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("Autopilot")


class PIDController:
    """Simple PID controller for steering."""

    def __init__(self, kp=2.0, ki=0.0, kd=0.5, output_limit=None):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limit = output_limit or MAX_STEERING

        self._prev_error = 0.0
        self._integral = 0.0

    def compute(self, error, dt=0.01):
        """
        Compute PID output.

        Args:
            error: Current error (target - current angle).
            dt: Time delta in seconds.

        Returns:
            float: PID output clamped to output_limit.
        """
        self._integral += error * dt
        # Anti-windup
        self._integral = max(-1.0, min(1.0, self._integral))

        derivative = (error - self._prev_error) / dt if dt > 0 else 0.0
        self._prev_error = error

        output = self.kp * error + self.ki * self._integral + self.kd * derivative
        return max(-self.output_limit, min(self.output_limit, output))

    def reset(self):
        self._prev_error = 0.0
        self._integral = 0.0


class Autopilot:
    """
    Autonomous navigation along crop rows.

    Generates waypoints for straight rows with U-turns,
    and computes speed/steering commands using PID control.
    """

    # States
    STATE_IDLE = "IDLE"
    STATE_DRIVING = "DRIVING"
    STATE_TURNING = "TURNING"
    STATE_FINISHED = "FINISHED"

    def __init__(self, row_y_positions, row_x_start=-18, row_x_end=18,
                 driving_speed=5.0, turning_speed=3.0):
        """
        Args:
            row_y_positions: List of Y coordinates for each crop row.
            row_x_start: X coordinate where rows start.
            row_x_end: X coordinate where rows end.
            driving_speed: Speed in km/h while driving straight.
            turning_speed: Speed in km/h during U-turns.
        """
        self.driving_speed = min(driving_speed, MAX_SPEED)
        self.turning_speed = min(turning_speed, MAX_SPEED)

        # Generate waypoints
        self.waypoints = []
        self._generate_waypoints(row_y_positions, row_x_start, row_x_end)

        self.current_wp_index = 0
        self.state = self.STATE_IDLE
        self.pid = PIDController(kp=2.5, ki=0.01, kd=0.8)

        # Threshold for reaching a waypoint (meters)
        self.wp_reach_distance = 2.0

        logger.info("Autopilot hazır: %d waypoint, %d sıra",
                     len(self.waypoints), len(row_y_positions))

    def _generate_waypoints(self, row_y_positions, x_start, x_end):
        """Generate waypoints for zigzag pattern across rows."""
        for i, y in enumerate(row_y_positions):
            if i % 2 == 0:
                # Even rows: left to right
                self.waypoints.append((x_start, y, "DRIVE"))
                self.waypoints.append((x_end, y, "DRIVE"))
            else:
                # Odd rows: right to left
                self.waypoints.append((x_end, y, "DRIVE"))
                self.waypoints.append((x_start, y, "DRIVE"))

            # Add turn waypoint between rows (except after last)
            if i < len(row_y_positions) - 1:
                next_y = row_y_positions[i + 1]
                if i % 2 == 0:
                    self.waypoints.append((x_end + 3, (y + next_y) / 2, "TURN"))
                else:
                    self.waypoints.append((x_start - 3, (y + next_y) / 2, "TURN"))

    def start(self):
        """Start autonomous driving."""
        if self.waypoints:
            self.current_wp_index = 0
            self.state = self.STATE_DRIVING
            self.pid.reset()
            logger.info("Otonom sürüş başladı")
        else:
            logger.warning("Waypoint yok, otonom sürüş başlatılamadı")

    def stop(self):
        """Stop autonomous driving."""
        self.state = self.STATE_IDLE
        self.pid.reset()
        logger.info("Otonom sürüş durduruldu")

    @property
    def is_active(self):
        return self.state in (self.STATE_DRIVING, self.STATE_TURNING)

    @property
    def progress_percent(self):
        if not self.waypoints:
            return 0.0
        return (self.current_wp_index / len(self.waypoints)) * 100

    def compute(self, tractor_pos, tractor_orientation):
        """
        Compute speed and steering commands for the current step.

        Args:
            tractor_pos: [x, y, z] current tractor position.
            tractor_orientation: 3x3 rotation matrix (flat list of 9).

        Returns:
            tuple: (speed, steering) commands.
        """
        if not self.is_active or self.current_wp_index >= len(self.waypoints):
            self.state = self.STATE_FINISHED
            return 0.0, 0.0

        # Current waypoint
        wp_x, wp_y, wp_type = self.waypoints[self.current_wp_index]

        # Compute distance and bearing to waypoint
        dx = wp_x - tractor_pos[0]
        dy = wp_y - tractor_pos[1]
        distance = math.sqrt(dx ** 2 + dy ** 2)

        # Check if we reached the waypoint
        if distance < self.wp_reach_distance:
            self.current_wp_index += 1
            self.pid.reset()
            logger.info("Waypoint %d/%d ulaşıldı (%.0f%%)",
                        self.current_wp_index, len(self.waypoints),
                        self.progress_percent)

            if self.current_wp_index >= len(self.waypoints):
                self.state = self.STATE_FINISHED
                logger.info("Tüm sıralar tamamlandı!")
                return 0.0, 0.0

            # Update state based on next waypoint type
            next_type = self.waypoints[self.current_wp_index][2]
            self.state = self.STATE_TURNING if next_type == "TURN" else self.STATE_DRIVING
            return self.compute(tractor_pos, tractor_orientation)

        # Compute heading to waypoint
        target_heading = math.atan2(dy, dx)

        # Get current tractor heading from orientation matrix
        # rotation matrix: [cos, -sin, 0, sin, cos, 0, 0, 0, 1]
        cos_a = tractor_orientation[0]
        sin_a = tractor_orientation[3]
        current_heading = math.atan2(sin_a, cos_a)

        # Heading error (normalized to [-pi, pi])
        heading_error = target_heading - current_heading
        heading_error = math.atan2(math.sin(heading_error), math.cos(heading_error))

        # PID steering
        steering = self.pid.compute(heading_error)

        # Speed depends on state
        speed = self.turning_speed if self.state == self.STATE_TURNING else self.driving_speed

        # Reduce speed when turning sharply
        if abs(steering) > MAX_STEERING * 0.5:
            speed *= 0.6

        return speed, steering

    def get_status_string(self):
        """Return a compact status string."""
        if self.state == self.STATE_IDLE:
            return "OTONOM: BEKLEMEDE"
        elif self.state == self.STATE_FINISHED:
            return "OTONOM: TAMAMLANDI"
        else:
            return f"OTONOM: {self.state} | WP:{self.current_wp_index}/{len(self.waypoints)} | {self.progress_percent:.0f}%"
