"""
Tractor Driver Controller
--------------------------
A simple vehicle.Driver controller that:
  - Reads speed/steering commands from the Supervisor via Receiver
  - Applies them to the Tractor using the Driver API
  - No socket, no supervisor API needed
"""
import sys
import os
import logging

# ── Add project root to path for config import ───────────────────────
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import LOG_FORMAT, LOG_LEVEL
from vehicle import Driver

# ── Logging setup ─────────────────────────────────────────────────────
logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("TractorDriver")

# ── Initialize Driver ─────────────────────────────────────────────────
driver = Driver()
timestep = int(driver.getBasicTimeStep())
logger.info("Traktör Driver başlatıldı, timestep: %dms", timestep)

# ── Get Receiver device ───────────────────────────────────────────────
receiver = driver.getDevice("receiver")
if receiver:
    receiver.enable(timestep)
    logger.info("Receiver aktif (kanal 1)")
else:
    logger.warning("Receiver bulunamadı!")

# ── Set initial driving parameters ────────────────────────────────────
driver.setGear(1)  # Vitesi 1'e al (Eğer boşta (0) olursa direksiyon döner ama araç gitmez)
driver.setCruisingSpeed(0.0)
driver.setSteeringAngle(0.0)

logger.info("=" * 45)
logger.info("Traktör Driver Kontrolcüsü")
logger.info("=" * 45)
logger.info("Supervisor'dan komut bekleniyor...")
logger.info("=" * 45)

# ── Simulation loop ──────────────────────────────────────────────────
step_count = 0

while driver.step() != -1:
    step_count += 1

    # ── Read commands from Supervisor via Receiver ──
    if receiver and receiver.getQueueLength() > 0:
        # Process all queued messages, use the latest one
        latest_speed = None
        latest_steering = None

        while receiver.getQueueLength() > 0:
            data = receiver.getString()
            receiver.nextPacket()

            try:
                parts = data.split(',')
                if len(parts) >= 2:
                    latest_speed = float(parts[0])
                    latest_steering = float(parts[1])
            except (ValueError, AttributeError):
                pass

        # Apply the latest command
        if latest_speed is not None and latest_steering is not None:
            driver.setCruisingSpeed(latest_speed)
            driver.setSteeringAngle(latest_steering)

            # Log occasionally
            if step_count % 100 == 0:
                logger.debug("Hız: %.1f km/h, Direksiyon: %.3f",
                             latest_speed, latest_steering)
