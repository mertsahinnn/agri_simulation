"""
Weed Detector Module (YOLO + Dataset Integrated)
=================================================
Reads frames from external dataset folders mimicking Webots cameras.
Returns nozzle activations as confidence values (0.0 to 1.0) for variable rate spraying.
"""
import sys
import os
import logging
import cv2
import glob
import time
import numpy as np

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import NUM_NOZZLES, LOG_FORMAT, LOG_LEVEL, AI_DATASET_PATHS, AI_IMAGE_EXTENSIONS, AI_IMAGE_INTERVAL_MS

logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("WeedDetector")

# Import YOLO Detector
try:
    sys.path.insert(0, os.path.join(project_root, 'ai'))
    from yolo_detector import YOLODetector
except ImportError as e:
    logger.critical("yolo_detector modülü bulunamadı! %s", e)
    sys.exit(1)

class WeedDetector:
    def __init__(self, cameras=None, timestep=10):
        # We accept 'cameras' for backward compatibility with spray_supervisor
        self.timestep = timestep
        self._enabled = False
        self._detection_count = 0
        
        # Initialize YOLO
        self.yolo = YOLODetector()
        
        # Setup dataset loaders
        self.dataset_images = [[] for _ in range(NUM_NOZZLES)]
        self.current_indices = [0] * NUM_NOZZLES
        self.last_update_times = [0] * NUM_NOZZLES
        self.last_activations = [0.0] * NUM_NOZZLES
        self.last_detected_indices = [-1] * NUM_NOZZLES
        
        self._setup_datasets()

    def _setup_datasets(self):
        try:
            for i, path in enumerate(AI_DATASET_PATHS):
                abs_path = os.path.join(project_root, path)
                if os.path.isdir(abs_path):
                    # Find all images
                    images = []
                    for ext in AI_IMAGE_EXTENSIONS:
                        images.extend(glob.glob(os.path.join(abs_path, f"*{ext}")))
                        images.extend(glob.glob(os.path.join(abs_path, f"*{ext.upper()}")))
                    
                    images.sort() # Ensure consistent order
                    self.dataset_images[i] = images
                    logger.info("Kamera %d veri seti: %d görsel bulundu (%s)", i+1, len(images), path)
                else:
                    logger.warning("Kamera %d veri seti yolu bulunamadı: %s", i+1, abs_path)
            
            self._enabled = any(len(imgs) > 0 for imgs in self.dataset_images)
            if self._enabled:
                logger.info("Veri seti tabanlı kamera okuyucu etkinleştirildi (Gerçek dünya fotoğrafları kullanılacak).")
            else:
                logger.error("Hiç görsel bulunamadı! Lütfen ai/dataset/ klasörlerine resimleri koyun.")
        except Exception as e:
            logger.error("Veri seti başlatma hatası: %s", e)
            self._enabled = False

    @property
    def is_enabled(self):
        return self._enabled

    def detect(self):
        """
        Run YOLO detection on frames from dataset folders.
        Returns:
            list[float]: Nozzle activation confidence/intensity [0.0 - 1.0] for each nozzle.
        """
        nozzle_activations = [0.0] * NUM_NOZZLES

        if not self._enabled:
            return nozzle_activations

        current_time_ms = time.time() * 1000

        for i in range(NUM_NOZZLES):
            images = self.dataset_images[i]
            if not images:
                continue
                
            # Time-based slideshow logic:
            # Advance to the next image if AI_IMAGE_INTERVAL_MS has passed
            if current_time_ms - self.last_update_times[i] > AI_IMAGE_INTERVAL_MS:
                self.current_indices[i] = (self.current_indices[i] + 1) % len(images)
                self.last_update_times[i] = current_time_ms

            # Resim değişmediyse, YOLO'yu tekrar çalıştırmak yerine önceki sonucu kullan
            if self.current_indices[i] == self.last_detected_indices[i]:
                nozzle_activations[i] = self.last_activations[i]
                continue

            try:
                # Read next image from dataset
                img_path = images[self.current_indices[i]]
                img_bgr = cv2.imread(img_path)
                
                if img_bgr is not None:
                    # Run YOLO detection
                    detections = self.yolo.detect(img_bgr)
                    
                    # Annotate and save for dashboard presentation
                    annotated = self.yolo.draw_detections(img_bgr, detections)
                    annot_dir = os.path.join(project_root, "ai", "dataset", "annotated")
                    os.makedirs(annot_dir, exist_ok=True)
                    cv2.imwrite(os.path.join(annot_dir, f"camera_{i+1}.jpg"), annotated)
                    
                    max_confidence = 0.0
                    for det in detections:
                        if det.is_weed():
                            self._detection_count += 1
                            if det.confidence > max_confidence:
                                max_confidence = det.confidence
                                
                    self.last_activations[i] = max_confidence
                    self.last_detected_indices[i] = self.current_indices[i]
                    nozzle_activations[i] = max_confidence
                    
            except Exception as e:
                logger.error("Kamera %d okuma/tespit hatası: %s", i+1, e)
                nozzle_activations[i] = self.last_activations[i]

        return nozzle_activations

    @property
    def current_image_paths(self):
        """Returns relative paths of currently active images in dataset (e.g. 'dataset/camera_1/img.jpg')"""
        paths = [""] * NUM_NOZZLES
        if not self._enabled:
            return paths
        
        for i in range(NUM_NOZZLES):
            if self.dataset_images[i]:
                idx = self.current_indices[i]
                abs_p = self.dataset_images[i][idx]
                parts = abs_p.split(os.sep)
                try:
                    # Find 'ai' folder and return everything after it
                    ai_idx = parts.index("ai")
                    paths[i] = "/".join(parts[ai_idx+1:])
                except ValueError:
                    # Fallback if 'ai' is not exact in path (some windows issues)
                    # Let's just use replace
                    rel_p = abs_p.replace("\\", "/").split("/ai/")[-1]
                    paths[i] = rel_p
        return paths

    @property
    def total_detections(self):
        return self._detection_count
