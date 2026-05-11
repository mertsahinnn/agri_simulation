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

from config import MAX_SPEED, MAX_STEERING, STEERING_SIGN, LOG_FORMAT, LOG_LEVEL

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
        self.pid = PIDController(kp=2.0, ki=0.05, kd=0.3)

        # Debug: adım sayacı (loglama için)
        self._step_count = 0

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
                # Traktörün dönüş çapı (Turning Radius) geniş olduğu için +3 metre yetmiyor.
                # Daha rahat bir kavis çizebilmesi için dönüş boşluğunu +6 metreye çıkardık.
                if i % 2 == 0:
                    self.waypoints.append((x_end + 6, (y + next_y) / 2, "TURN"))
                else:
                    self.waypoints.append((x_start - 6, (y + next_y) / 2, "TURN"))

    def start(self, tractor_pos=None, tractor_heading=None):
        """Start autonomous driving from the nearest waypoint to the tractor's current position."""
        if not self.waypoints:
            logger.warning("Waypoint yok, otonom sürüş başlatılamadı")
            return

        if tractor_pos is not None:
            # Traktörün mevcut pozisyonuna en yakın DRIVE waypoint'ini bul
            best_idx = 0
            best_dist = float('inf')
            for i, (wx, wy, wt) in enumerate(self.waypoints):
                if wt == "DRIVE":
                    d = math.sqrt((wx - tractor_pos[0])**2 + (wy - tractor_pos[1])**2)
                    if d < best_dist:
                        best_dist = d
                        best_idx = i

            # Traktörün bakış yönüne göre: eğer bir sonraki waypoint traktörün
            # önündeyse best_idx'i kullan, değilse +1 yap (ters yöne gitmesin)
            if tractor_heading is not None and best_idx + 1 < len(self.waypoints):
                wx, wy, _ = self.waypoints[best_idx]
                dx = wx - tractor_pos[0]
                dy = wy - tractor_pos[1]
                angle_to_wp = math.atan2(dy, dx)
                angle_diff = abs(math.atan2(math.sin(angle_to_wp - tractor_heading),
                                            math.cos(angle_to_wp - tractor_heading)))
                # Eğer waypoint traktörün arkasındaysa (±90°'den fazla), bir sonrakine atla
                if angle_diff > math.pi / 2:
                    best_idx = min(best_idx + 1, len(self.waypoints) - 1)
                    logger.info("İlk waypoint arkanızda, bir sonrakine atlanıyor: WP %d", best_idx)

            self.current_wp_index = best_idx
            logger.info("En yakın waypoint: %d (mesafe: %.1fm)", best_idx, best_dist)
        else:
            self.current_wp_index = 0

        self.state = self.STATE_DRIVING
        self.pid.reset()
        self.last_wp = (tractor_pos[0], tractor_pos[1]) if tractor_pos else None
        logger.info("Otonom sürüş başladı (WP %d/%d)", self.current_wp_index, len(self.waypoints))

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

    def compute(self, tractor_pos, tractor_orientation, dt=0.01):
        """
        Compute speed and steering commands for the current step.

        Args:
            tractor_pos: [x, y, z] current tractor position.
            tractor_orientation: 3x3 rotation matrix (flat list of 9).
            dt: Simulation timestep in seconds.

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
        # U-Dönüşü noktaları için toleransı (reach_dist) genişletiyoruz çünkü traktörün o noktaya 
        # milimetrik değmesine gerek yok, kavis çizip yan sıraya geçmesi yeterli.
        reach_dist = 4.0 if wp_type == "TURN" else 2.0
        
        if distance < reach_dist:
            self.last_wp = (wp_x, wp_y)
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
            return self.compute(tractor_pos, tractor_orientation, dt)

        # Speed depends on state
        speed = self.turning_speed if self.state == self.STATE_TURNING else self.driving_speed

        # Get current tractor heading from orientation matrix
        # rotation matrix: [cos, -sin, 0, sin, cos, 0, 0, 0, 1]
        cos_a = tractor_orientation[0]
        sin_a = tractor_orientation[3]
        current_heading = math.atan2(sin_a, cos_a)

        # Debug adım sayacı
        self._step_count += 1

        if self.state == self.STATE_DRIVING:
            # === STANLEY CONTROLLER (Path Tracking) ===
            # Önceki waypoint'i bul ve sanal bir doğru (line) oluştur
            if not hasattr(self, 'last_wp') or self.last_wp is None:
                self.last_wp = (tractor_pos[0], tractor_pos[1])
            px, py = self.last_wp

            # Line direction vector (Sıranın yönü)
            lx = wp_x - px
            ly = wp_y - py
            line_len = math.sqrt(lx**2 + ly**2)

            if line_len > 0:
                nx = lx / line_len
                ny = ly / line_len

                # Tractor to previous waypoint vector
                vx = tractor_pos[0] - px
                vy = tractor_pos[1] - py

                # Cross-Track Error (CTE): Traktörün sıranın merkezine olan yanal uzaklığı
                cte = vx * ny - vy * nx

                # Path Heading (Sıranın açısı)
                path_heading = math.atan2(ly, lx)
            else:
                cte = 0.0
                path_heading = math.atan2(dy, dx)

            # Heading Error (Sıra açısı - Traktör açısı)
            heading_error = path_heading - current_heading
            heading_error = math.atan2(math.sin(heading_error), math.cos(heading_error))

            # Adaptive Stanley Gain — hız arttıkça k düşer (stabilite için)
            k = 0.6 / max(1.0, speed)
            v_safe = max(0.5, speed)

            # STEERING_SIGN: Webots direksiyon yönünü config'den kontrol et
            raw_steer = heading_error + math.atan2(k * cte, v_safe)
            steering = STEERING_SIGN * raw_steer
            steering = max(-MAX_STEERING, min(MAX_STEERING, steering))

            # Debug log (her 20 adımda bir)
            if self._step_count % 20 == 0:
                logger.debug("DRIVE | HDG:%.2f TGT:%.2f ERR:%.2f CTE:%.3f STR:%.3f",
                             current_heading, path_heading, heading_error, cte, steering)

        else:
            # === PID CONTROLLER (U-Dönüşleri / Noktaya Yönelme) ===
            target_heading = math.atan2(dy, dx)
            heading_error = target_heading - current_heading
            heading_error = math.atan2(math.sin(heading_error), math.cos(heading_error))

            # STEERING_SIGN ile Webots uyumu sağlanıyor
            steering = self.pid.compute(STEERING_SIGN * heading_error, dt)

            # Debug log
            if self._step_count % 20 == 0:
                logger.debug("TURN  | HDG:%.2f TGT:%.2f ERR:%.2f STR:%.3f",
                             current_heading, target_heading, heading_error, steering)

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
