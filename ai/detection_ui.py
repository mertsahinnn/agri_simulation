"""
YOLO Tespit UI — 4 Kameralı Yabancı Ot Tespit Paneli
======================================================
Bu UI, 4 ayrı video kaynağını (her nozzle için bir tane) eş zamanlı
olarak gösterir ve YOLO modeli ile yabancı ot tespiti yapar.

Mimari:
  ┌───────────┬───────────┐
  │ Kamera 1  │ Kamera 2  │  ← Video panelleri (2x2 grid)
  │ (N1 Sol)  │ (N2 Sol)  │     Her panelde YOLO bbox overlay
  ├───────────┼───────────┤
  │ Kamera 3  │ Kamera 4  │
  │ (N3 Sağ)  │ (N4 Sağ)  │
  └───────────┴───────────┘
  [🤖 AI: KAPALI] [📊 İstatistik]   ← Kontrol butonları
  [N1: ● ] [N2: ● ] [N3: ● ] [N4: ●]  ← Nozzle durumları
  Durum: Bağlı | FPS: 24 | Weed: 12    ← Durum çubuğu

Bağlantı:
  - TCP socket üzerinden spray_supervisor'a bağlanır
  - Weed tespit edilince nozzle açma komutu gönderir
  - AI_ON / AI_OFF komutuyla otomatik mod aç/kapat

Çalıştırma:
  python ai/detection_ui.py
"""

import sys
import os
import tkinter as tk
from tkinter import font as tkfont
import socket
import threading
import time
import logging

# ── Proje kök dizinini Python path'ine ekle ──────────────────────────
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import (
    SOCKET_HOST, SOCKET_PORT,
    NUM_NOZZLES,
    YOLO_CONFIDENCE, AI_VIDEO_PATHS,
    LOG_FORMAT, LOG_LEVEL,
)
from ai.yolo_detector import YOLODetector

# ── Logging ayarları ──────────────────────────────────────────────────
logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("DetectionUI")

# ── OpenCV ve PIL import ──────────────────────────────────────────────
try:
    import cv2
    import numpy as np
    from PIL import Image, ImageTk
except ImportError as e:
    logger.critical("Gerekli kütüphane bulunamadı: %s", e)
    logger.critical("Çalıştırın: pip install opencv-python Pillow")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════════════
# RENK SABİTLERİ — Koyu tema
# ═══════════════════════════════════════════════════════════════════════
BG        = "#0d1117"      # Ana arka plan (github-dark)
BG2       = "#161b22"      # Kart arka planı
CARD      = "#21262d"      # Panel kenarı
ACCENT    = "#e94560"      # Vurgu rengi
GREEN     = "#2ecc71"      # Aktif / başarılı
RED       = "#e74c3c"      # Hata / tehlike / weed
YELLOW    = "#f1c40f"      # Uyarı
BLUE      = "#3498db"      # Bilgi
TEXT      = "#e6edf3"      # Ana metin
SUBTEXT   = "#8b949e"      # Alt metin
NOZZLE_ON  = "#2ecc71"     # Nozzle açık
NOZZLE_OFF = "#30363d"     # Nozzle kapalı

# Video panel boyutları (her kamera için)
PANEL_WIDTH = 400
PANEL_HEIGHT = 300


class VideoPanel:
    """
    Tek bir kamera video panelini temsil eder.

    Her panel:
    - Bir video dosyası açar (yoksa placeholder gösterir)
    - YOLO detector ile tespitleri çizer
    - Nozzle durum sonucunu döndürür
    """

    def __init__(self, parent, camera_index, nozzle_name, detector):
        """
        Video paneli oluştur.

        Args:
            parent: Tkinter parent widget
            camera_index (int): Kamera indeksi (0-3)
            nozzle_name (str): Nozzle etiket adı (ör. "N1 Sol Dış")
            detector (YOLODetector): Paylaşılan YOLO detector
        """
        self.camera_index = camera_index
        self.nozzle_name = nozzle_name
        self.detector = detector
        self.cap = None           # OpenCV VideoCapture nesnesi
        self.is_playing = False   # Video oynatılıyor mu
        self.has_weed = False     # Son frame'de weed var mı
        self.frame_count = 0      # Toplam işlenen frame
        self.last_detections = [] # Son tespit sonuçları

        # ── Panel çerçevesi ──
        self.frame = tk.Frame(parent, bg=BG2, relief="flat", bd=1,
                              highlightbackground=CARD, highlightthickness=1)

        # ── Başlık ──
        header = tk.Frame(self.frame, bg=CARD, height=28)
        header.pack(fill="x")
        header.pack_propagate(False)

        self.title_label = tk.Label(
            header, text=f"📷 {nozzle_name}",
            font=("Segoe UI", 9, "bold"), fg=TEXT, bg=CARD
        )
        self.title_label.pack(side="left", padx=8)

        # Nozzle durumu göstergesi (başlık sağında)
        self.nozzle_indicator = tk.Label(
            header, text="● KAPALI", font=("Segoe UI", 8),
            fg=SUBTEXT, bg=CARD
        )
        self.nozzle_indicator.pack(side="right", padx=8)

        # ── Video görüntü alanı (Tkinter Label ile) ──
        self.video_label = tk.Label(
            self.frame, bg="#000000",
            width=PANEL_WIDTH, height=PANEL_HEIGHT
        )
        self.video_label.pack(padx=2, pady=2)

        # ── Tespit bilgisi alt çubuğu ──
        info_bar = tk.Frame(self.frame, bg=BG2, height=22)
        info_bar.pack(fill="x")
        info_bar.pack_propagate(False)

        self.info_label = tk.Label(
            info_bar, text="Video bekleniyor...",
            font=("Segoe UI", 8), fg=SUBTEXT, bg=BG2
        )
        self.info_label.pack(side="left", padx=8)

        self.weed_count_label = tk.Label(
            info_bar, text="🌿 0",
            font=("Segoe UI", 8, "bold"), fg=GREEN, bg=BG2
        )
        self.weed_count_label.pack(side="right", padx=8)

        # ── Placeholder görüntü oluştur ──
        self._show_placeholder()

    def _show_placeholder(self):
        """Video yokken gösterilecek placeholder görüntü oluştur."""
        # Siyah arka plan üzerine bilgi mesajı
        placeholder = np.zeros((PANEL_HEIGHT, PANEL_WIDTH, 3), dtype=np.uint8)

        # Ortalanmış metin
        text = "Video bulunamadi"
        text2 = f"ai/videos/camera_{self.camera_index + 1}.mp4"

        cv2.putText(placeholder, text,
                    (PANEL_WIDTH // 2 - 120, PANEL_HEIGHT // 2 - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 100), 1)
        cv2.putText(placeholder, text2,
                    (PANEL_WIDTH // 2 - 150, PANEL_HEIGHT // 2 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 80), 1)

        self._update_image(placeholder)

    def open_video(self, video_path):
        """
        Video dosyasını aç.

        Args:
            video_path (str): Video dosyasının tam yolu

        Returns:
            bool: Başarılı ise True
        """
        # Önceki video'yu kapat
        if self.cap is not None:
            self.cap.release()

        # Dosya var mı kontrol et
        abs_path = os.path.join(project_root, video_path)
        if not os.path.exists(abs_path):
            logger.warning("Video bulunamadı: %s", abs_path)
            self._show_placeholder()
            return False

        # OpenCV ile video aç
        self.cap = cv2.VideoCapture(abs_path)
        if not self.cap.isOpened():
            logger.error("Video açılamadı: %s", abs_path)
            self._show_placeholder()
            return False

        self.is_playing = True
        self.info_label.config(text=f"▶ {os.path.basename(video_path)}")
        logger.info("Kamera %d: Video açıldı — %s", self.camera_index + 1, abs_path)
        return True

    def process_frame(self, ai_enabled):
        """
        Bir sonraki frame'i oku, YOLO ile analiz et ve göster.

        Args:
            ai_enabled (bool): AI tespit aktif mi?

        Returns:
            bool: Weed tespit edildiyse True
        """
        if self.cap is None or not self.is_playing:
            return False

        # ── Frame oku ──
        ret, frame = self.cap.read()

        # Video sona erdiyse başa sar (loop)
        if not ret:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret:
                return False

        self.frame_count += 1

        # Frame'i panel boyutuna ölçekle
        frame = cv2.resize(frame, (PANEL_WIDTH, PANEL_HEIGHT))

        # ── AI tespiti ──
        self.has_weed = False
        if ai_enabled:
            # YOLO ile tespit yap
            self.last_detections = self.detector.detect(frame)

            # Weed var mı kontrol et
            self.has_weed = self.detector.has_weed(self.last_detections)
            weed_count = self.detector.count_weeds(self.last_detections)
            total_count = len(self.last_detections)

            # Tespitleri frame üzerine çiz
            frame = self.detector.draw_detections(frame, self.last_detections)

            # Bilgi etiketini güncelle
            self.weed_count_label.config(
                text=f"🌾 {total_count - weed_count} | 🌿 {weed_count}",
                fg=RED if self.has_weed else GREEN
            )

            # Nozzle göstergesini güncelle
            if self.has_weed:
                self.nozzle_indicator.config(text="● İLAÇLA", fg=RED)
                self.title_label.config(fg=RED)
            else:
                self.nozzle_indicator.config(text="● TEMİZ", fg=GREEN)
                self.title_label.config(fg=TEXT)
        else:
            # AI kapalı — sadece video göster
            self.nozzle_indicator.config(text="● AI KAPALI", fg=SUBTEXT)
            self.title_label.config(fg=TEXT)

        # ── Frame'i Tkinter'a çevir ve göster ──
        self._update_image(frame)
        return self.has_weed

    def _update_image(self, frame):
        """
        OpenCV BGR frame'ini Tkinter PhotoImage'a çevir ve göster.

        Args:
            frame (np.ndarray): BGR formatında OpenCV görüntüsü
        """
        # BGR → RGB dönüşümü (OpenCV BGR, Tkinter RGB kullanır)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # NumPy array → PIL Image → Tkinter PhotoImage
        pil_image = Image.fromarray(rgb)
        tk_image = ImageTk.PhotoImage(pil_image)

        # Label'ı güncelle (referansı sakla, garbage collection engelle)
        self.video_label.config(image=tk_image)
        self.video_label.image = tk_image  # referans tutma zorunlu!

    def release(self):
        """Video kaynağını serbest bırak."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.is_playing = False


class DetectionUI:
    """
    4 Kameralı Yabancı Ot Tespit Paneli.

    Ana UI sınıfı. 4 VideoPanel'i 2x2 grid'de düzenler,
    YOLO tespitlerini yönetir ve spray_supervisor'a bağlanır.
    """

    def __init__(self, root):
        """
        UI'yı oluştur ve başlat.

        Args:
            root: Tkinter root penceresi
        """
        self.root = root
        self.root.title("🔬 AI Yabancı Ot Tespit Paneli")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        # ── Fontlar ──
        self.title_font = tkfont.Font(family="Segoe UI", size=13, weight="bold")
        self.btn_font   = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.small_font = tkfont.Font(family="Segoe UI", size=9)
        self.mono_font  = tkfont.Font(family="Consolas", size=10)

        # ── Durum değişkenleri ──
        self.ai_enabled = False          # AI tespit açık/kapalı
        self.connected = False           # Supervisor bağlantısı
        self.sock = None                 # TCP socket
        self.sock_lock = threading.Lock()
        self.nozzle_states = [0] * NUM_NOZZLES  # Mevcut nozzle durumları
        self.fps = 0                     # Anlık FPS
        self._frame_times = []           # FPS hesabı için zaman damgaları

        # ── YOLO Detector (tüm paneller paylaşır) ──
        self.detector = YOLODetector()
        logger.info("YOLO Detector başlatıldı (simülasyon=%s)",
                     self.detector.simulation_mode)

        # ── UI Bileşenleri ──
        self._build_ui()

        # ── Videoları aç ──
        self._open_videos()

        # ── Ana döngüyü başlat ──
        self._update_loop()

    # ══════════════════════════════════════════════════════════════════
    # UI OLUŞTURMA
    # ══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        """Tüm UI bileşenlerini oluştur."""

        # ── Başlık çubuğu ──
        header = tk.Frame(self.root, bg=ACCENT, height=40)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="🔬  AI YABANCI OT TESPİT PANELİ",
                 font=self.title_font, fg="white", bg=ACCENT
                 ).pack(side="left", padx=14)

        # Bağlantı göstergesi (sağ üst)
        self.conn_label = tk.Label(
            header, text="● BAĞLI DEĞİL",
            font=self.small_font, fg=RED, bg=ACCENT
        )
        self.conn_label.pack(side="right", padx=14)

        # Simülasyon modu uyarısı
        if self.detector.simulation_mode:
            sim_banner = tk.Frame(self.root, bg="#332200", height=24)
            sim_banner.pack(fill="x")
            sim_banner.pack_propagate(False)
            tk.Label(sim_banner,
                     text="⚠ SİMÜLASYON MODU — YOLO modeli bulunamadı, rastgele tespitler gösteriliyor",
                     font=self.small_font, fg=YELLOW, bg="#332200"
                     ).pack(padx=10)

        # ── Video panelleri (2x2 grid) ──
        grid_frame = tk.Frame(self.root, bg=BG)
        grid_frame.pack(fill="both", expand=True, padx=6, pady=6)

        # Nozzle isimleri
        nozzle_names = ["N1 — Sol Dış", "N2 — Sol İç", "N3 — Sağ İç", "N4 — Sağ Dış"]

        # 4 paneli 2x2 grid olarak yerleştir
        self.panels = []
        for i in range(NUM_NOZZLES):
            row = i // 2   # 0, 0, 1, 1
            col = i % 2    # 0, 1, 0, 1

            panel = VideoPanel(grid_frame, i, nozzle_names[i], self.detector)
            panel.frame.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            self.panels.append(panel)

        # Grid ağırlıklarını ayarla (eşit dağılım)
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)
        grid_frame.grid_rowconfigure(0, weight=1)
        grid_frame.grid_rowconfigure(1, weight=1)

        # ── Kontrol çubuğu ──
        control_frame = tk.Frame(self.root, bg=BG, height=50)
        control_frame.pack(fill="x", padx=10, pady=(0, 4))

        # Bağlan butonu
        self.connect_btn = tk.Button(
            control_frame, text="🔗 BAĞLAN", font=self.btn_font,
            bg=BLUE, fg="white", relief="flat", cursor="hand2",
            width=12, command=self._toggle_connection
        )
        self.connect_btn.pack(side="left", padx=4)

        # AI aç/kapat butonu
        self.ai_btn = tk.Button(
            control_frame, text="🤖 AI: KAPALI", font=self.btn_font,
            bg=NOZZLE_OFF, fg=TEXT, relief="flat", cursor="hand2",
            width=14, command=self._toggle_ai
        )
        self.ai_btn.pack(side="left", padx=4)

        # FPS göstergesi
        self.fps_label = tk.Label(
            control_frame, text="FPS: --",
            font=self.mono_font, fg=SUBTEXT, bg=BG
        )
        self.fps_label.pack(side="right", padx=10)

        # ── Nozzle durumları ──
        nozzle_frame = tk.Frame(self.root, bg=BG2)
        nozzle_frame.pack(fill="x", padx=10, pady=(0, 4))

        tk.Label(nozzle_frame, text="NOZZLE DURUMU:",
                 font=self.small_font, fg=SUBTEXT, bg=BG2
                 ).pack(side="left", padx=8, pady=6)

        self.nozzle_labels = []
        nozzle_short = ["N1 Sol", "N2 Sol", "N3 Sağ", "N4 Sağ"]
        for i in range(NUM_NOZZLES):
            lbl = tk.Label(
                nozzle_frame, text=f"  {nozzle_short[i]}: ◯  ",
                font=("Segoe UI", 10, "bold"),
                fg=SUBTEXT, bg=BG2
            )
            lbl.pack(side="left", padx=6, pady=6)
            self.nozzle_labels.append(lbl)

        # ── Durum çubuğu ──
        status_bar = tk.Frame(self.root, bg=CARD, height=28)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)

        self.status_label = tk.Label(
            status_bar, text="Hazır — Video dosyalarını ai/videos/ klasörüne koyun",
            font=self.small_font, fg=SUBTEXT, bg=CARD
        )
        self.status_label.pack(side="left", padx=10, pady=4)

        self.stats_label = tk.Label(
            status_bar, text="",
            font=self.small_font, fg=SUBTEXT, bg=CARD
        )
        self.stats_label.pack(side="right", padx=10, pady=4)

    # ══════════════════════════════════════════════════════════════════
    # VİDEO YÖNETİMİ
    # ══════════════════════════════════════════════════════════════════

    def _open_videos(self):
        """Config'deki video dosyalarını aç."""
        opened = 0
        for i, path in enumerate(AI_VIDEO_PATHS):
            if i < len(self.panels):
                if self.panels[i].open_video(path):
                    opened += 1

        if opened == 0:
            self.status_label.config(
                text="⚠ Hiçbir video bulunamadı — ai/videos/ klasörüne video ekleyin"
            )
        else:
            self.status_label.config(text=f"✅ {opened}/{NUM_NOZZLES} video yüklendi")

    # ══════════════════════════════════════════════════════════════════
    # ANA GÜNCELLEME DÖNGÜSÜ
    # ══════════════════════════════════════════════════════════════════

    def _update_loop(self):
        """
        Tkinter ana döngüsü — her 33ms'de bir çağrılır (~30 FPS).

        Her çağrıda:
        1. Her video panelin frame'ini güncelle
        2. YOLO tespiti yap (AI açıksa)
        3. Nozzle kararlarını hesapla
        4. Supervisor'a gönder
        5. UI'yı güncelle
        """
        start_time = time.time()

        # ── Her paneli güncelle ──
        new_nozzle_states = [0] * NUM_NOZZLES

        for i, panel in enumerate(self.panels):
            # Frame'i işle ve weed durumunu al
            has_weed = panel.process_frame(self.ai_enabled)

            # Weed tespit edildiyse bu nozzle'ı aç
            if has_weed and self.ai_enabled:
                new_nozzle_states[i] = 1

        # ── Nozzle durumlarını güncelle ──
        self.nozzle_states = new_nozzle_states
        self._update_nozzle_display()

        # ── Supervisor'a nozzle kararını gönder ──
        if self.connected and self.ai_enabled:
            self._send_nozzle_states()

        # ── FPS hesapla ──
        elapsed = time.time() - start_time
        self._frame_times.append(elapsed)
        if len(self._frame_times) > 30:
            self._frame_times.pop(0)
        avg_time = sum(self._frame_times) / len(self._frame_times)
        self.fps = 1.0 / avg_time if avg_time > 0 else 0
        self.fps_label.config(text=f"FPS: {self.fps:.0f}")

        # ── İstatistikleri güncelle ──
        stats = self.detector.get_stats()
        mode = "SİM" if stats["simulation_mode"] else "YOLO"
        self.stats_label.config(
            text=f"[{mode}] Frame:{stats['total_frames']} | "
                 f"Weed:{stats['total_weeds']} | Crop:{stats['total_crops']}"
        )

        # ── Sonraki frame için zamanlayıcı ──
        # 33ms ≈ 30 FPS hedefi
        self.root.after(33, self._update_loop)

    # ══════════════════════════════════════════════════════════════════
    # NOZZLE GÖRÜNTÜSÜ
    # ══════════════════════════════════════════════════════════════════

    def _update_nozzle_display(self):
        """Nozzle durum göstergelerini güncelle."""
        for i in range(NUM_NOZZLES):
            if self.nozzle_states[i]:
                # Nozzle açık → kırmızı (ilaçlıyor)
                self.nozzle_labels[i].config(
                    text=f"  N{i+1}: ● İLAÇ  ",
                    fg=RED, bg="#3d1f1f"
                )
            else:
                # Nozzle kapalı → yeşil (temiz)
                self.nozzle_labels[i].config(
                    text=f"  N{i+1}: ◯ TEMİZ  ",
                    fg=GREEN if self.ai_enabled else SUBTEXT,
                    bg=BG2
                )

    # ══════════════════════════════════════════════════════════════════
    # BAĞLANTI YÖNETİMİ
    # ══════════════════════════════════════════════════════════════════

    def _toggle_connection(self):
        """Supervisor bağlantısını aç/kapat."""
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        """Spray supervisor'a TCP bağlantısı kur."""
        def connect_thread():
            try:
                new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                new_sock.settimeout(3)
                new_sock.connect((SOCKET_HOST, SOCKET_PORT))
                new_sock.settimeout(1.0)

                with self.sock_lock:
                    self.sock = new_sock
                    self.connected = True

                logger.info("Supervisor'a bağlandı (%s:%d)", SOCKET_HOST, SOCKET_PORT)

                # UI'yı güncelle (ana thread'den)
                self.root.after(0, lambda: self._set_connected_ui(True))

            except Exception as e:
                logger.warning("Bağlantı hatası: %s", e)
                self.root.after(0, lambda: self.status_label.config(
                    text=f"❌ Bağlantı hatası: {e}"
                ))

        threading.Thread(target=connect_thread, daemon=True).start()

    def _disconnect(self):
        """Mevcut bağlantıyı kes."""
        with self.sock_lock:
            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None
            self.connected = False

        self._set_connected_ui(False)
        logger.info("Bağlantı kesildi")

    def _set_connected_ui(self, connected):
        """Bağlantı durumuna göre UI'yı güncelle."""
        if connected:
            self.conn_label.config(text="● BAĞLI", fg=GREEN)
            self.connect_btn.config(text="🔗 BAĞLANTIYI KES", bg=RED)
            self.status_label.config(text="✅ Supervisor'a bağlandı")
        else:
            self.conn_label.config(text="● BAĞLI DEĞİL", fg=RED)
            self.connect_btn.config(text="🔗 BAĞLAN", bg=BLUE)
            self.status_label.config(text="Bağlantı kesildi")

    # ══════════════════════════════════════════════════════════════════
    # AI MODU
    # ══════════════════════════════════════════════════════════════════

    def _toggle_ai(self):
        """AI tespit modunu aç/kapat."""
        self.ai_enabled = not self.ai_enabled

        if self.ai_enabled:
            self.ai_btn.config(text="🤖 AI: AKTİF", bg=GREEN)
            logger.info("AI tespit AKTİF")

            # Supervisor'a AI_ON komutu gönder
            self._send_command("AI_ON\n")
        else:
            self.ai_btn.config(text="🤖 AI: KAPALI", bg=NOZZLE_OFF)
            logger.info("AI tespit KAPALI")

            # Supervisor'a AI_OFF komutu gönder
            self._send_command("AI_OFF\n")

            # Tüm nozzle'ları kapat
            self.nozzle_states = [0] * NUM_NOZZLES
            self._update_nozzle_display()

    # ══════════════════════════════════════════════════════════════════
    # VERİ GÖNDERİMİ
    # ══════════════════════════════════════════════════════════════════

    def _send_nozzle_states(self):
        """
        Mevcut nozzle durumlarını supervisor'a gönder.

        Format: 0,0,n1,n2,n3,n4
        İlk iki değer speed ve steering (0 çünkü bu UI kontrol etmiyor)
        """
        with self.sock_lock:
            if not self.connected or not self.sock:
                return
            try:
                n = self.nozzle_states
                # speed=0, steering=0, ardından nozzle durumları
                cmd = f"0,0,{n[0]},{n[1]},{n[2]},{n[3]}\n"
                self.sock.sendall(cmd.encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.connected = False
                self.root.after(0, lambda: self._set_connected_ui(False))

    def _send_command(self, command):
        """
        Ham metin komutu gönder.

        Args:
            command (str): Gönderilecek komut (ör. "AI_ON\n")
        """
        with self.sock_lock:
            if not self.connected or not self.sock:
                return
            try:
                self.sock.sendall(command.encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.connected = False

    # ══════════════════════════════════════════════════════════════════
    # TEMİZLİK
    # ══════════════════════════════════════════════════════════════════

    def cleanup(self):
        """Tüm kaynakları serbest bırak."""
        # Videoları kapat
        for panel in self.panels:
            panel.release()

        # Socket'i kapat
        self._disconnect()

        logger.info("UI kapatıldı, kaynaklar serbest bırakıldı")


# ══════════════════════════════════════════════════════════════════════
# ANA GİRİŞ NOKTASI
# ══════════════════════════════════════════════════════════════════════

def main():
    """Uygulamayı başlat."""
    root = tk.Tk()

    # Pencere boyutu (2x2 grid + kontroller)
    root.geometry("850x760")
    root.minsize(700, 600)

    # UI'yı oluştur
    app = DetectionUI(root)

    # Kapatma olayını yakala
    def on_close():
        app.cleanup()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    logger.info("=" * 55)
    logger.info("AI Yabancı Ot Tespit Paneli başlatıldı")
    logger.info("=" * 55)
    logger.info("Video dosyalarını ai/videos/ klasörüne koyun")
    logger.info("YOLO modeli: %s", app.detector.model_path)
    logger.info("Simülasyon modu: %s", app.detector.simulation_mode)
    logger.info("=" * 55)

    # Tkinter ana döngüsü
    root.mainloop()


if __name__ == "__main__":
    main()
