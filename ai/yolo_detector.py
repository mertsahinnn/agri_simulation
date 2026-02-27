"""
YOLO Yabancı Ot Tespit Modülü
================================
Bu modül, YOLO (You Only Look Once) modelini kullanarak
video karelerinde yabancı ot ve bitki tespiti yapar.

Özellikler:
  - Eğitilmiş YOLO modelini yükler ve inference çalıştırır
  - Model bulunamazsa "simülasyon modu"na geçer (demo/test için)
  - Her frame için bounding box, sınıf adı ve güven skoru döndürür
  - Tespit sonuçlarını frame üzerine çizer

Sınıflar:
  - weed (0): Yabancı ot → İLAÇLANACAK
  - crop (1): Bitki → İLAÇLANMAYACAK

Kullanım:
  detector = YOLODetector()
  results = detector.detect(frame)
  annotated = detector.draw_detections(frame, results)
"""

import sys
import os
import logging
import random
import time

# ── Proje kök dizinini Python path'ine ekle ──────────────────────────
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import YOLO_MODEL_PATH, YOLO_CONFIDENCE, YOLO_CLASSES, LOG_FORMAT, LOG_LEVEL

# ── Logging ayarları ──────────────────────────────────────────────────
logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("YOLODetector")

# ── OpenCV import ─────────────────────────────────────────────────────
try:
    import cv2
    import numpy as np
except ImportError:
    logger.critical("OpenCV bulunamadı! 'pip install opencv-python' çalıştırın.")
    sys.exit(1)

# ── YOLO import ───────────────────────────────────────────────────────
# ultralytics kütüphanesi yüklü değilse simülasyon moduna düşeriz
try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False
    logger.warning("ultralytics bulunamadı. Simülasyon modunda çalışılacak.")


# ═══════════════════════════════════════════════════════════════════════
# Renk sabitleri: BGR formatında (OpenCV standart)
# ═══════════════════════════════════════════════════════════════════════
WEED_COLOR = (0, 0, 255)       # Kırmızı — yabancı ot (tehlike)
CROP_COLOR = (0, 200, 0)       # Yeşil — bitki (güvenli)
TEXT_COLOR = (255, 255, 255)    # Beyaz — metin
BG_COLOR = (0, 0, 0)           # Siyah — arka plan


class Detection:
    """
    Tek bir tespit sonucunu temsil eder.

    Attributes:
        bbox (tuple): Bounding box koordinatları (x1, y1, x2, y2)
        class_id (int): Sınıf indeksi (0=weed, 1=crop)
        class_name (str): Sınıf adı ("weed" veya "crop")
        confidence (float): Güven skoru (0.0 - 1.0)
    """
    def __init__(self, bbox, class_id, class_name, confidence):
        self.bbox = bbox            # (x1, y1, x2, y2) piksel koordinatları
        self.class_id = class_id    # 0 = weed, 1 = crop
        self.class_name = class_name  # "weed" veya "crop"
        self.confidence = confidence  # 0.0 - 1.0 arası güven değeri

    def is_weed(self):
        """Bu tespit bir yabancı ot mu?"""
        return self.class_id == 0

    def __repr__(self):
        return f"Detection({self.class_name}, conf={self.confidence:.2f}, bbox={self.bbox})"


class YOLODetector:
    """
    YOLO tabanlı yabancı ot / bitki tespit sınıfı.

    Gerçek bir YOLO modeli yüklü değilse otomatik olarak
    simülasyon moduna geçer ve rastgele tespitler üretir.
    """

    def __init__(self, model_path=None):
        """
        Detektörü başlat.

        Args:
            model_path (str, optional): YOLO .pt model dosyasının yolu.
                                        None ise config.py'den okunur.
        """
        # Model yolunu belirle (parametre > config > varsayılan)
        self.model_path = model_path or YOLO_MODEL_PATH
        self.confidence_threshold = YOLO_CONFIDENCE
        self.class_names = YOLO_CLASSES  # ["weed", "crop"]

        # Durum değişkenleri
        self.model = None
        self.simulation_mode = False

        # İstatistik sayaçları
        self.total_frames = 0        # toplam işlenen frame sayısı
        self.total_detections = 0    # toplam tespit sayısı
        self.total_weeds = 0         # toplam yabancı ot tespiti
        self.total_crops = 0         # toplam bitki tespiti

        # ── Model yükleme ──
        self._load_model()

    def _load_model(self):
        """
        YOLO modelini yüklemeyi dene.
        Başarısız olursa simülasyon moduna geç.
        """
        # Önce model dosyasını proje köküne göre çöz
        abs_model_path = os.path.join(project_root, self.model_path)

        if ULTRALYTICS_AVAILABLE and os.path.exists(abs_model_path):
            # ── Gerçek model yükleme ──
            try:
                self.model = YOLO(abs_model_path)
                self.simulation_mode = False
                logger.info("✅ YOLO modeli yüklendi: %s", abs_model_path)
            except Exception as e:
                logger.error("Model yükleme hatası: %s", e)
                self._enable_simulation_mode()
        else:
            # ── Model bulunamadı → simülasyon modu ──
            if not ULTRALYTICS_AVAILABLE:
                logger.warning("ultralytics kütüphanesi yüklü değil")
            else:
                logger.warning("Model dosyası bulunamadı: %s", abs_model_path)
            self._enable_simulation_mode()

    def _enable_simulation_mode(self):
        """Simülasyon modunu aktifleştir (demo/test için)."""
        self.simulation_mode = True
        self.model = None
        logger.info("🔄 SİMÜLASYON MODU aktif — rastgele tespitler üretilecek")

    # ══════════════════════════════════════════════════════════════════
    # ANA TESPİT FONKSİYONU
    # ══════════════════════════════════════════════════════════════════

    def detect(self, frame):
        """
        Verilen frame üzerinde yabancı ot tespiti yap.

        Args:
            frame (np.ndarray): BGR formatında OpenCV görüntüsü

        Returns:
            list[Detection]: Tespit edilen nesnelerin listesi
        """
        if frame is None:
            return []

        self.total_frames += 1

        if self.simulation_mode:
            # ── Simülasyon: rastgele tespit üret ──
            return self._simulate_detections(frame)
        else:
            # ── Gerçek YOLO inference ──
            return self._run_yolo(frame)

    def _run_yolo(self, frame):
        """
        Gerçek YOLO modeli ile inference çalıştır.

        Args:
            frame (np.ndarray): Giriş görüntüsü

        Returns:
            list[Detection]: Tespit sonuçları
        """
        detections = []

        try:
            # YOLO inference — verbose=False ile gereksiz log'ları kapat
            results = self.model(frame, conf=self.confidence_threshold, verbose=False)

            # İlk sonuç üzerinde çalış (tek frame gönderiyoruz)
            if results and len(results) > 0:
                result = results[0]

                # Her tespit edilen nesne için
                for box in result.boxes:
                    # Bounding box koordinatlarını al (x1, y1, x2, y2)
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)

                    # Sınıf ID ve güven skoru
                    class_id = int(box.cls[0].cpu().numpy())
                    confidence = float(box.conf[0].cpu().numpy())

                    # Sınıf adını belirle
                    if class_id < len(self.class_names):
                        class_name = self.class_names[class_id]
                    else:
                        class_name = f"unknown_{class_id}"

                    # Detection nesnesi oluştur ve listeye ekle
                    det = Detection(
                        bbox=(x1, y1, x2, y2),
                        class_id=class_id,
                        class_name=class_name,
                        confidence=confidence
                    )
                    detections.append(det)

                    # İstatistikleri güncelle
                    self.total_detections += 1
                    if det.is_weed():
                        self.total_weeds += 1
                    else:
                        self.total_crops += 1

        except Exception as e:
            logger.error("YOLO inference hatası: %s", e)

        return detections

    def _simulate_detections(self, frame):
        """
        Model olmadığında demo için rastgele tespitler üret.

        Her ~30 frame'de bir rastgele 1-4 tespit oluşturur.
        Tespit boyutu ve konumu frame boyutuna göre ölçeklenir.

        Args:
            frame (np.ndarray): Giriş görüntüsü (boyut referansı için)

        Returns:
            list[Detection]: Rastgele üretilmiş tespitler
        """
        detections = []
        h, w = frame.shape[:2]

        # Her 30 frame'de bir yeni tespitler üret (performans için)
        if self.total_frames % 30 != 0:
            # Önceki tespitleri geri döndür (cache)
            if hasattr(self, '_cached_detections'):
                return self._cached_detections
            return []

        # Rastgele 1-4 arası tespit sayısı
        num_detections = random.randint(1, 4)

        for _ in range(num_detections):
            # Rastgele bounding box oluştur
            box_w = random.randint(w // 10, w // 4)   # kutu genişliği
            box_h = random.randint(h // 10, h // 4)   # kutu yüksekliği
            x1 = random.randint(0, w - box_w)         # sol üst x
            y1 = random.randint(0, h - box_h)         # sol üst y
            x2 = x1 + box_w                           # sağ alt x
            y2 = y1 + box_h                           # sağ alt y

            # %40 weed, %60 crop olasılığı
            is_weed = random.random() < 0.4
            class_id = 0 if is_weed else 1
            class_name = "weed" if is_weed else "crop"
            confidence = random.uniform(0.55, 0.95)    # rastgele güven

            det = Detection(
                bbox=(x1, y1, x2, y2),
                class_id=class_id,
                class_name=class_name,
                confidence=confidence
            )
            detections.append(det)

            # İstatistikleri güncelle
            self.total_detections += 1
            if is_weed:
                self.total_weeds += 1
            else:
                self.total_crops += 1

        # Önbelleğe al
        self._cached_detections = detections
        return detections

    # ══════════════════════════════════════════════════════════════════
    # GÖRSELLEŞTIRME
    # ══════════════════════════════════════════════════════════════════

    def draw_detections(self, frame, detections):
        """
        Tespit sonuçlarını frame üzerine çiz.

        Weed → kırmızı kutu + etiket
        Crop → yeşil kutu + etiket

        Args:
            frame (np.ndarray): Üzerine çizilecek görüntü
            detections (list[Detection]): Çizilecek tespitler

        Returns:
            np.ndarray: Üzerine çizim yapılmış görüntü (kopyası)
        """
        # Orijinal frame'i bozmamak için kopya oluştur
        annotated = frame.copy()

        for det in detections:
            x1, y1, x2, y2 = det.bbox

            # Sınıfa göre renk seç
            color = WEED_COLOR if det.is_weed() else CROP_COLOR

            # ── Bounding box çiz ──
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            # ── Etiket metni hazırla ──
            label = f"{det.class_name} {det.confidence:.0%}"

            # Etiket arka planı için metin boyutunu hesapla
            (text_w, text_h), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
            )

            # Etiket arka planı (yarı saydam dikdörtgen)
            cv2.rectangle(
                annotated,
                (x1, y1 - text_h - 8),
                (x1 + text_w + 8, y1),
                color, -1  # dolu dikdörtgen
            )

            # Etiket metni (beyaz)
            cv2.putText(
                annotated, label,
                (x1 + 4, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                TEXT_COLOR, 1, cv2.LINE_AA
            )

        return annotated

    def has_weed(self, detections):
        """
        Tespit listesinde yabancı ot var mı kontrol et.

        Args:
            detections (list[Detection]): Kontrol edilecek tespitler

        Returns:
            bool: Yabancı ot tespit edildiyse True
        """
        return any(d.is_weed() for d in detections)

    def count_weeds(self, detections):
        """
        Tespit listesindeki yabancı ot sayısını döndür.

        Args:
            detections (list[Detection]): Sayılacak tespitler

        Returns:
            int: Yabancı ot tespiti sayısı
        """
        return sum(1 for d in detections if d.is_weed())

    def get_stats(self):
        """
        Toplam tespit istatistiklerini döndür.

        Returns:
            dict: İstatistik sözlüğü
        """
        return {
            "total_frames": self.total_frames,
            "total_detections": self.total_detections,
            "total_weeds": self.total_weeds,
            "total_crops": self.total_crops,
            "simulation_mode": self.simulation_mode,
        }
