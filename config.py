"""
Agricultural Simulation - Central Configuration
================================================
All shared constants and settings for the simulation.
"""

# ── Network ───────────────────────────────────────────────────────────
SOCKET_HOST = "localhost"
SOCKET_PORT = 5005
VIDEO_STREAM_PORT = 5006  # MJPEG stream için RAM üzeri video aktarım portu

# ── Tractor ───────────────────────────────────────────────────────────
MAX_SPEED = 20.0          # km/h
MIN_SPEED = -20.0         # km/h (reverse)
MAX_STEERING = 0.6        # radians
SPEED_STEP = 0.5          # slider resolution

# Webots direksiyon yönü düzeltmesi:
# Eğer traktör otonom sürüşte ters yöne gidiyorsa bu değeri değiştirin.
#  1 = normal (pozitif açı = sola dönüş)
# -1 = ters   (pozitif açı = sağa dönüş, çoğu Webots Vehicle modeli)
STEERING_SIGN = -1

# ── Nozzles ───────────────────────────────────────────────────────────
NUM_NOZZLES = 4
NOZZLE_Y_OFFSETS = [-0.9, -0.3, 0.3, 0.9]   # relative to tractor center
SPRAYER_X_OFFSET = -1.9                       # rear offset of boom

# ── Spray Visuals ─────────────────────────────────────────────────────
SPRAY_OFF_TRANSPARENCY = 0.95
SPRAY_ON_TRANSPARENCY = 0.3
SPRAY_LIGHT_ON_INTENSITY = 0.5
SPRAY_LIGHT_OFF_INTENSITY = 0.0

# ── Ground Marks ──────────────────────────────────────────────────────
MAX_MARKS = 2000
MARK_INTERVAL = 10        # simulation steps between marks
MARK_HEIGHT = 0.005       # z-position of marks
MARK_SIZE = (0.5, 0.25, 0.005)
MARK_COLOR = (0.1, 0.6, 0.9)
MARK_TRANSPARENCY = 0.3

# ── Status Updates ────────────────────────────────────────────────────
STATUS_SEND_INTERVAL_MS = 50    # milliseconds between status updates to UI
UI_SEND_RATE_HZ = 10            # commands per second from UI

# ── Logging ───────────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_LEVEL = "INFO"

# ── AI / YOLO ─────────────────────────────────────────────────────────
# YOLO model dosyasının yolu (proje köküne göreceli)
# Kullanıcı kendi eğittiği modelin yolunu buraya yazacak
YOLO_MODEL_PATH = "models/best.pt"

# Tespit güven eşiği (bu değerin altındaki tespitler göz ardı edilir)
YOLO_CONFIDENCE = 0.5

# Sınıf isimleri (modeldeki sınıf sırasına uygun olmalı)
# 0 = weed (yabancı ot), 1 = crop (bitki)
YOLO_CLASSES = ["weed", "crop"]

# ── Kameralar (Sanal Kamera Veri Seti Yolları) ────────────────────────
CAMERA_NAMES = ["camera_1", "camera_2", "camera_3", "camera_4"]

# Her nozzle için kaynak görsel klasörü (proje köküne göreceli)
AI_DATASET_PATHS = [
    "ai/dataset/camera_1",   # Nozzle 1 — Sol Dış
    "ai/dataset/camera_2",   # Nozzle 2 — Sol İç
    "ai/dataset/camera_3",   # Nozzle 3 — Sağ İç
    "ai/dataset/camera_4",   # Nozzle 4 — Sağ Dış
]

# Desteklenen görsel formatları
AI_IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg"]

# Görseller arası otomatik geçiş süresi (milisaniye)
# 100ms = saniyede 10 görsel (Yüksek işlem gücü ister)
# 333ms = saniyede 3 görsel (Düşük donanımlı bilgisayarlar için kasmayı engeller)
AI_IMAGE_INTERVAL_MS = 333

# YOLO tahmininin kaç adımda bir çalışacağı (Performans için)
AI_DETECTION_INTERVAL = 1
