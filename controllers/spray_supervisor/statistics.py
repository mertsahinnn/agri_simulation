"""
Spray Statistics Module
========================
Tracks spraying performance metrics:
  - Per-nozzle active time
  - Total sprayed area estimate
  - AI detection counts
  - Efficiency ratio (weed-only vs total spray)
  - CSV export for post-analysis
"""
import sys
import os
import csv
import time
import logging
from datetime import datetime

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import NUM_NOZZLES, LOG_FORMAT, LOG_LEVEL

logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("Statistics")


class SprayStatistics:
    """Collects and reports spraying statistics over the simulation run."""

    def __init__(self, timestep_ms):
        """
        Args:
            timestep_ms: Simulation timestep in milliseconds.
        """
        self.timestep_s = timestep_ms / 1000.0
        self.start_time = datetime.now()

        # Per-nozzle tracking
        self.nozzle_active_steps = [0] * NUM_NOZZLES
        self.nozzle_total_on_time_s = [0.0] * NUM_NOZZLES

        # Global tracking
        self.total_steps = 0
        self.total_spray_steps = 0        # steps where any nozzle was on
        self.ai_detection_count = 0
        self.weed_spray_steps = 0         # steps where AI triggered spray
        self.manual_spray_steps = 0       # steps where manual triggered spray
        self.total_marks_placed = 0

        # Position tracking for route
        self.route_points = []
        self._last_route_record = 0
        self.ROUTE_RECORD_INTERVAL = 50   # record position every N steps

        # Event log
        self.events = []

    def update(self, nozzle_states, ai_mode, tractor_pos=None, mark_count=0):
        """
        Called every simulation step to update statistics.

        Args:
            nozzle_states: list[int] - current nozzle states (0/1)
            ai_mode: bool - whether AI mode is active
            tractor_pos: list[float] - [x, y, z] tractor position
            mark_count: int - current total mark count
        """
        self.total_steps += 1
        self.total_marks_placed = mark_count

        any_on = False
        for i in range(NUM_NOZZLES):
            if nozzle_states[i]:
                self.nozzle_active_steps[i] += 1
                self.nozzle_total_on_time_s[i] += self.timestep_s
                any_on = True

        if any_on:
            self.total_spray_steps += 1
            if ai_mode:
                self.weed_spray_steps += 1
            else:
                self.manual_spray_steps += 1

        # Record route
        if tractor_pos and self.total_steps - self._last_route_record >= self.ROUTE_RECORD_INTERVAL:
            self.route_points.append((tractor_pos[0], tractor_pos[1], self.total_steps))
            self._last_route_record = self.total_steps

    def log_event(self, event_type, details=""):
        """Log a timestamped event."""
        self.events.append({
            "step": self.total_steps,
            "time": datetime.now().isoformat(),
            "type": event_type,
            "details": details,
        })

    def get_summary(self):
        """
        Return a dictionary with all current statistics.
        """
        elapsed_s = self.total_steps * self.timestep_s
        total_on_time = sum(self.nozzle_total_on_time_s)
        max_possible_time = elapsed_s * NUM_NOZZLES

        efficiency = 0.0
        if self.total_spray_steps > 0:
            efficiency = (self.weed_spray_steps / self.total_spray_steps) * 100

        return {
            "elapsed_time_s": elapsed_s,
            "total_steps": self.total_steps,
            "nozzle_on_times_s": list(self.nozzle_total_on_time_s),
            "total_spray_time_s": total_on_time,
            "max_possible_spray_s": max_possible_time,
            "spray_duty_cycle_pct": (total_on_time / max_possible_time * 100) if max_possible_time > 0 else 0,
            "ai_spray_steps": self.weed_spray_steps,
            "manual_spray_steps": self.manual_spray_steps,
            "ai_efficiency_pct": efficiency,
            "total_marks": self.total_marks_placed,
            "route_points": len(self.route_points),
        }

    def get_status_string(self):
        """Compact status string for UI display."""
        s = self.get_summary()
        nozzle_times = [f"N{i+1}:{t:.1f}s" for i, t in enumerate(s["nozzle_on_times_s"])]
        return (f"Süre:{s['elapsed_time_s']:.0f}s | "
                f"İlaç:{s['total_spray_time_s']:.1f}s | "
                f"Verim:{s['ai_efficiency_pct']:.0f}% | "
                f"{' '.join(nozzle_times)}")

    def export_csv(self, filepath=None):
        """
        Export statistics to a CSV file.

        Args:
            filepath: Override output path. Defaults to project root.
        """
        if filepath is None:
            filepath = os.path.join(project_root, f"spray_stats_{self.start_time.strftime('%Y%m%d_%H%M%S')}.csv")

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Summary section
                writer.writerow(["=== İLAÇLAMA İSTATİSTİKLERİ ==="])
                writer.writerow(["Başlangıç", self.start_time.isoformat()])
                writer.writerow(["Bitiş", datetime.now().isoformat()])

                summary = self.get_summary()
                writer.writerow([])
                writer.writerow(["Metrik", "Değer"])
                writer.writerow(["Toplam Süre (s)", f"{summary['elapsed_time_s']:.1f}"])
                writer.writerow(["Toplam Adım", summary['total_steps']])
                writer.writerow(["Toplam İlaçlama Süresi (s)", f"{summary['total_spray_time_s']:.1f}"])
                writer.writerow(["İlaçlama Duty Cycle (%)", f"{summary['spray_duty_cycle_pct']:.1f}"])
                writer.writerow(["AI İlaçlama Adım", summary['ai_spray_steps']])
                writer.writerow(["Manuel İlaçlama Adım", summary['manual_spray_steps']])
                writer.writerow(["AI Verimlilik (%)", f"{summary['ai_efficiency_pct']:.1f}"])
                writer.writerow(["Toplam Yer İşareti", summary['total_marks']])

                # Per-nozzle stats
                writer.writerow([])
                writer.writerow(["Nozzle", "Aktif Süre (s)", "Aktif Adım"])
                for i in range(NUM_NOZZLES):
                    writer.writerow([f"N{i+1}", f"{self.nozzle_total_on_time_s[i]:.2f}",
                                     self.nozzle_active_steps[i]])

                # Route
                if self.route_points:
                    writer.writerow([])
                    writer.writerow(["=== ROTA ==="])
                    writer.writerow(["X", "Y", "Adım"])
                    for x, y, step in self.route_points:
                        writer.writerow([f"{x:.2f}", f"{y:.2f}", step])

                # Events
                if self.events:
                    writer.writerow([])
                    writer.writerow(["=== OLAYLAR ==="])
                    writer.writerow(["Adım", "Zaman", "Tür", "Detay"])
                    for e in self.events:
                        writer.writerow([e["step"], e["time"], e["type"], e["details"]])

            logger.info("İstatistikler kaydedildi: %s", filepath)
            return filepath
        except Exception as e:
            logger.error("CSV dışa aktarım hatası: %s", e)
            return None
