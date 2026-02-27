"""
Weed Detector Module
=====================
Uses the Webots Camera Recognition API to detect weeds in the field.
Each nozzle covers a specific Y-zone; the detector checks recognized objects
in each zone and returns which nozzles should be activated.

Recognition is based on the recognitionColors defined in the PROTOs:
  - CropPlant: (0.2, 0.6, 0.15)  → will NOT trigger spraying
  - Weed:      (0.35, 0.5, 0.1)  → WILL trigger spraying
"""
import sys
import os
import logging
import math

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import NUM_NOZZLES, NOZZLE_Y_OFFSETS, LOG_FORMAT, LOG_LEVEL

logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("WeedDetector")

# Recognition color of weeds (must match Weed.proto recognitionColors)
WEED_COLOR = (0.35, 0.5, 0.1)
COLOR_TOLERANCE = 0.15   # how close a detected color must be to match


def _color_distance(c1, c2):
    """Euclidean distance between two RGB color tuples."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _is_weed_color(color):
    """Check if the given recognition color matches weed color."""
    return _color_distance(color, WEED_COLOR) < COLOR_TOLERANCE


class WeedDetector:
    """
    Uses Webots Camera Recognition to detect weeds and map them to nozzle zones.

    The camera should be mounted on the tractor looking downward, covering
    the boom area. Each nozzle is responsible for a vertical strip of the
    camera image.
    """

    def __init__(self, camera, timestep):
        """
        Args:
            camera: A Webots Camera node with Recognition enabled.
            timestep: Simulation timestep in ms.
        """
        self.camera = camera
        self.timestep = timestep
        self.width = 0
        self.height = 0
        self._enabled = False
        self._detection_count = 0

        if camera is not None:
            self._setup_camera()
        else:
            logger.warning("Kamera bulunamadı – AI tespit devre dışı")

    def _setup_camera(self):
        """Enable camera and recognition."""
        try:
            self.camera.enable(self.timestep)
            self.camera.recognitionEnable(self.timestep)
            self.width = self.camera.getWidth()
            self.height = self.camera.getHeight()
            self._enabled = True
            logger.info("Kamera etkinleştirildi: %dx%d, recognition aktif",
                        self.width, self.height)
        except Exception as e:
            logger.error("Kamera başlatma hatası: %s", e)
            self._enabled = False

    @property
    def is_enabled(self):
        return self._enabled

    def detect(self):
        """
        Run weed detection on the current camera frame.

        Returns:
            list[int]: Nozzle activation states [n1, n2, n3, n4].
                       1 = weed detected in that zone, 0 = no weed.
        """
        nozzle_activations = [0] * NUM_NOZZLES

        if not self._enabled or self.camera is None:
            return nozzle_activations

        try:
            objects = self.camera.getRecognitionObjects()
        except Exception:
            return nozzle_activations

        if not objects:
            return nozzle_activations

        for obj in objects:
            try:
                colors = obj.getColors()
                # colors is a flat list: [r, g, b, r, g, b, ...]
                # Check first color triplet
                if len(colors) >= 3:
                    color = (colors[0], colors[1], colors[2])
                    if _is_weed_color(color):
                        # Determine which nozzle zone this object falls in
                        pos_on_image = obj.getPositionOnImage()
                        if pos_on_image and len(pos_on_image) >= 1:
                            x_pixel = pos_on_image[0]
                            zone = self._pixel_to_nozzle_zone(x_pixel)
                            if 0 <= zone < NUM_NOZZLES:
                                nozzle_activations[zone] = 1
                                self._detection_count += 1
            except Exception:
                continue

        return nozzle_activations

    def _pixel_to_nozzle_zone(self, x_pixel):
        """
        Map an x-pixel coordinate to a nozzle zone index.
        The camera image is divided into NUM_NOZZLES equal vertical strips.
        """
        if self.width <= 0:
            return -1
        zone_width = self.width / NUM_NOZZLES
        zone = int(x_pixel / zone_width)
        return min(zone, NUM_NOZZLES - 1)

    @property
    def total_detections(self):
        return self._detection_count
