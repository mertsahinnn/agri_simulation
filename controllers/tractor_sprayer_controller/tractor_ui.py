"""
Tractor + Sprayer Controller UI (Consolidated)
================================================
Dark-themed control panel for the Webots agricultural simulation.
Merges steering wheel visualization and boom status from the legacy UI
with the modern dark-themed design.

Connects to the spray_supervisor via TCP socket.

Run:  python tractor_ui.py
"""

import sys
import os
import tkinter as tk
from tkinter import font as tkfont
import socket
import threading
import math
import time
import logging

# ── Add project root to path for config import ───────────────────────
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import (
    SOCKET_HOST, SOCKET_PORT,
    MAX_SPEED, MIN_SPEED, MAX_STEERING, SPEED_STEP,
    NUM_NOZZLES, UI_SEND_RATE_HZ,
    LOG_FORMAT, LOG_LEVEL,
)

# ── Logging setup ─────────────────────────────────────────────────────
logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("TractorUI")

# ── Colours ───────────────────────────────────────────────────────────
BG        = "#1a1a2e"
BG2       = "#16213e"
CARD      = "#0f3460"
ACCENT    = "#e94560"
GREEN     = "#2ecc71"
RED       = "#e74c3c"
YELLOW    = "#f39c12"
BLUE      = "#3498db"
TEXT      = "#eaeaea"
SUBTEXT   = "#94a3b8"
NOZZLE_ON = "#2ecc71"
NOZZLE_OFF = "#334155"
DARK_METAL = "#2c3e50"


class TractorUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🚜 Traktör Kontrol Paneli")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        # ── Fonts ──
        self.title_font  = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        self.label_font  = tkfont.Font(family="Segoe UI", size=11)
        self.value_font  = tkfont.Font(family="Consolas", size=13, weight="bold")
        self.small_font  = tkfont.Font(family="Segoe UI", size=9)
        self.btn_font    = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.nozzle_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")

        # ── State ──
        self.sock = None
        self.sock_lock = threading.Lock()
        self.connected = False
        self._sock_generation = 0
        self.speed_var = tk.DoubleVar(value=0.0)
        self.steer_var = tk.DoubleVar(value=0.0)
        self.nozzle_vars = [tk.IntVar(value=0) for _ in range(NUM_NOZZLES)]
        self.status_text = tk.StringVar(value="Bağlantı bekleniyor...")
        self.ai_mode = False
        self.autopilot_mode = False
        # ── Canvas parameters for steering wheel ──
        self.canvas_size = 180
        self.canvas_center = self.canvas_size // 2
        self.canvas_radius = 70

        self._build_ui()
        self._start_sender()

    # ── UI Construction ───────────────────────────────────────────────
    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        # --- Header ---
        header = tk.Frame(self.root, bg=ACCENT, height=44)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="🚜  TRAKTÖR KONTROL PANELİ",
                 font=self.title_font, fg="white", bg=ACCENT).pack(side="left", padx=14)

        self.conn_indicator = tk.Label(header, text="● BAĞLI DEĞİL",
                                       font=self.small_font, fg=RED, bg=ACCENT)
        self.conn_indicator.pack(side="right", padx=14)

        # --- Connection ---
        conn_frame = tk.Frame(self.root, bg=BG, pady=6)
        conn_frame.pack(fill="x", padx=12)

        self.connect_btn = tk.Button(
            conn_frame, text="BAĞLAN", font=self.btn_font,
            bg=GREEN, fg="white", activebackground="#27ae60",
            relief="flat", cursor="hand2", width=14,
            command=self._toggle_connection
        )
        self.connect_btn.pack(side="left")

        self.status_label = tk.Label(conn_frame, textvariable=self.status_text,
                                     font=self.small_font, fg=SUBTEXT, bg=BG)
        self.status_label.pack(side="left", padx=10)

        tk.Frame(self.root, bg=CARD, height=2).pack(fill="x", padx=12, pady=2)

        # --- Top Row: Steering Wheel + Speed ─────────────────────────
        top_frame = tk.Frame(self.root, bg=BG)
        top_frame.pack(fill="x", **pad)

        # LEFT: Steering Wheel Canvas
        steer_card = tk.Frame(top_frame, bg=BG2, relief="flat", bd=0)
        steer_card.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(steer_card, text="DİREKSİYON", font=self.label_font,
                 fg=TEXT, bg=BG2).pack(pady=(8, 2))

        self.steer_canvas = tk.Canvas(steer_card, width=self.canvas_size,
                                      height=self.canvas_size, bg=BG2,
                                      highlightthickness=0, cursor="hand2")
        self.steer_canvas.pack(pady=4)
        self.steer_canvas.bind("<Motion>", self._on_canvas_motion)
        self.steer_canvas.bind("<Button-1>", self._on_canvas_click)

        self.steer_angle_label = tk.Label(steer_card, text="0.00°",
                                          font=self.value_font, fg=ACCENT, bg=BG2)
        self.steer_angle_label.pack()

        self.steer_direction_label = tk.Label(steer_card, text="DÜZ",
                                              font=self.small_font, fg=GREEN, bg=BG2)
        self.steer_direction_label.pack(pady=(0, 8))

        # RIGHT: Speed Slider
        speed_card = tk.Frame(top_frame, bg=BG2, relief="flat", bd=0)
        speed_card.pack(side="right", fill="both", expand=True, padx=(6, 0))

        tk.Label(speed_card, text="HIZ (km/h)", font=self.label_font,
                 fg=TEXT, bg=BG2).pack(pady=(8, 2))

        speed_inner = tk.Frame(speed_card, bg=BG2)
        speed_inner.pack(fill="both", expand=True, padx=16, pady=4)

        tk.Label(speed_inner, text=f"{int(MAX_SPEED)}",
                 font=self.small_font, fg=GREEN, bg=BG2).pack(side="top")

        self.speed_slider = tk.Scale(
            speed_inner, from_=MAX_SPEED, to=MIN_SPEED, resolution=SPEED_STEP,
            orient="vertical", variable=self.speed_var,
            bg=BG2, fg=TEXT, troughcolor=CARD, highlightthickness=0,
            activebackground=ACCENT, sliderrelief="flat",
            font=self.small_font, showvalue=False, width=18
        )
        self.speed_slider.pack(fill="both", expand=True, padx=8)

        tk.Label(speed_inner, text=f"{int(MIN_SPEED)}",
                 font=self.small_font, fg=RED, bg=BG2).pack(side="bottom")

        self.speed_display = tk.Label(speed_card, text="0 km/h",
                                      font=self.value_font, fg=BLUE, bg=BG2)
        self.speed_display.pack(pady=(4, 8))

        self.speed_var.trace_add("write", self._on_speed_change)
        self.steer_var.trace_add("write", self._on_steer_change)

        tk.Frame(self.root, bg=CARD, height=2).pack(fill="x", padx=12, pady=2)

        # --- Nozzle Controls + Boom Visual ────────────────────────────
        nozzle_frame = tk.Frame(self.root, bg=BG)
        nozzle_frame.pack(fill="x", **pad)

        tk.Label(nozzle_frame, text="💧 NOZZLE'LAR", font=self.label_font,
                 fg=TEXT, bg=BG).pack(anchor="w", pady=(0, 4))

        nozzle_row = tk.Frame(nozzle_frame, bg=BG)
        nozzle_row.pack(fill="x")

        nozzle_labels = ["N1\n(Sol Dış)", "N2\n(Sol İç)", "N3\n(Sağ İç)", "N4\n(Sağ Dış)"]
        self.nozzle_btns = []
        for i in range(NUM_NOZZLES):
            btn = tk.Button(
                nozzle_row, text=nozzle_labels[i] if i < len(nozzle_labels) else f"N{i+1}",
                font=self.nozzle_font, width=9, height=2,
                bg=NOZZLE_OFF, fg=TEXT, relief="flat",
                activebackground=CARD, cursor="hand2",
                command=lambda idx=i: self._toggle_nozzle(idx)
            )
            btn.pack(side="left", padx=4, pady=4, expand=True)
            self.nozzle_btns.append(btn)

        # All on / all off
        all_row = tk.Frame(nozzle_frame, bg=BG)
        all_row.pack(fill="x", pady=(6, 0))

        tk.Button(all_row, text="✅ TÜMÜNÜ AÇ", font=self.small_font,
                  bg=GREEN, fg="white", relief="flat", cursor="hand2",
                  command=self._all_nozzles_on, width=16).pack(side="left", padx=4, expand=True, fill="x")

        tk.Button(all_row, text="❌ TÜMÜNÜ KAPAT", font=self.small_font,
                  bg=RED, fg="white", relief="flat", cursor="hand2",
                  command=self._all_nozzles_off, width=16).pack(side="left", padx=4, expand=True, fill="x")

        # Boom visual canvas
        self.boom_canvas = tk.Canvas(nozzle_frame, width=440, height=40,
                                     bg=BG, highlightthickness=0)
        self.boom_canvas.pack(pady=(8, 0))
        self._draw_boom_status()

        tk.Frame(self.root, bg=CARD, height=2).pack(fill="x", padx=12, pady=2)

        # --- Quick Controls + AI Mode ─────────────────────────────────
        quick_frame = tk.Frame(self.root, bg=BG)
        quick_frame.pack(fill="x", **pad)

        tk.Button(quick_frame, text="⏹ ACİL DUR", font=self.btn_font,
                  bg=RED, fg="white", relief="flat", cursor="hand2",
                  width=12, command=self._emergency_stop).pack(side="left", padx=4)

        tk.Button(quick_frame, text="🔄 SIFIRLA", font=self.btn_font,
                  bg=CARD, fg=TEXT, relief="flat", cursor="hand2",
                  width=12, command=self._reset_all).pack(side="left", padx=4)

        self.ai_btn = tk.Button(quick_frame, text="🤖 AI: KAPALI", font=self.btn_font,
                               bg=NOZZLE_OFF, fg=TEXT, relief="flat", cursor="hand2",
                               width=12, command=self._toggle_ai_mode)
        self.ai_btn.pack(side="right", padx=4)

        self.auto_btn = tk.Button(quick_frame, text="🚀 OTONOM", font=self.btn_font,
                                  bg=NOZZLE_OFF, fg=TEXT, relief="flat", cursor="hand2",
                                  width=12, command=self._toggle_autopilot)
        self.auto_btn.pack(side="right", padx=4)

        # --- Status Bar ───────────────────────────────────────────────
        status_bar = tk.Frame(self.root, bg=BG2, height=60)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)

        self.position_label = tk.Label(status_bar, text="Pozisyon: ---",
                                        font=self.small_font, fg=SUBTEXT, bg=BG2)
        self.position_label.pack(side="left", padx=12, pady=2)

        self.mark_label = tk.Label(status_bar, text="İşaret: 0",
                                    font=self.small_font, fg=SUBTEXT, bg=BG2)
        self.mark_label.pack(side="right", padx=12, pady=2)

        self.ai_status_label = tk.Label(status_bar, text="AI: ---",
                                         font=self.small_font, fg=SUBTEXT, bg=BG2)
        self.ai_status_label.pack(side="right", padx=8, pady=2)

        self.stats_label = tk.Label(status_bar, text="",
                                    font=self.small_font, fg=SUBTEXT, bg=BG2)
        self.stats_label.pack(side="left", padx=12, pady=2)

        # Initial draw
        self._draw_steering_wheel()

    # ── Steering Wheel ────────────────────────────────────────────────
    def _on_canvas_motion(self, event):
        cx, cy, r = self.canvas_center, self.canvas_center, self.canvas_radius
        dx = event.x - cx
        dy = event.y - cy
        distance = math.sqrt(dx ** 2 + dy ** 2)
        if distance <= r:
            angle_rad = math.atan2(-dy, dx)
            angle_normalized = math.atan2(math.sin(angle_rad - math.pi / 2),
                                          math.cos(angle_rad - math.pi / 2))
            steering_angle = max(-MAX_STEERING,
                                 min(MAX_STEERING,
                                     angle_normalized * MAX_STEERING / (math.pi / 2)))
            self.steer_var.set(steering_angle)

    def _on_canvas_click(self, event):
        self._on_canvas_motion(event)

    def _draw_steering_wheel(self):
        c = self.steer_canvas
        c.delete("all")
        cx, cy, r = self.canvas_center, self.canvas_center, self.canvas_radius

        # Outer ring
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      outline=SUBTEXT, width=3, fill=CARD)
        # Tick marks
        for i in range(0, 360, 45):
            a = math.radians(i)
            x1 = cx + r * 0.88 * math.cos(a)
            y1 = cy + r * 0.88 * math.sin(a)
            x2 = cx + r * 1.0 * math.cos(a)
            y2 = cy + r * 1.0 * math.sin(a)
            c.create_line(x1, y1, x2, y2, fill=SUBTEXT, width=2)

        # Center hub
        c.create_oval(cx - 18, cy - 18, cx + 18, cy + 18,
                      outline=SUBTEXT, width=2, fill=ACCENT)

        # Top marker
        c.create_line(cx, cy - r * 0.88, cx, cy - r * 1.08,
                      fill=TEXT, width=3)

        # Steering indicator needle
        sa = self.steer_var.get() + math.pi / 2
        ex = cx + r * 0.65 * math.cos(sa)
        ey = cy - r * 0.65 * math.sin(sa)
        c.create_line(cx, cy, ex, ey, fill=ACCENT, width=4)
        c.create_oval(ex - 4, ey - 4, ex + 4, ey + 4,
                      fill=ACCENT, outline=RED)

    # ── Boom Visual ───────────────────────────────────────────────────
    def _draw_boom_status(self):
        c = self.boom_canvas
        c.delete("all")
        w = 440
        # Main boom bar
        c.create_rectangle(30, 14, w - 30, 22, fill=DARK_METAL, outline=SUBTEXT, width=1)

        nozzle_x_positions = [80, 170, 260, 350]
        nozzle_names = ["N1", "N2", "N3", "N4"]
        for i in range(min(NUM_NOZZLES, len(nozzle_x_positions))):
            x = nozzle_x_positions[i]
            is_on = self.nozzle_vars[i].get() if i < len(self.nozzle_vars) else 0
            if is_on:
                color = GREEN
                # Spray lines
                for dx in [-10, 0, 10]:
                    c.create_line(x, 22, x + dx, 40, fill=BLUE, width=1, dash=(2, 2))
            else:
                color = RED
            c.create_oval(x - 6, 12, x + 6, 24, fill=color, outline=SUBTEXT, width=1)
            c.create_text(x, 6, text=nozzle_names[i],
                          font=("Segoe UI", 7, "bold"), fill=SUBTEXT)

    # ── Callbacks ─────────────────────────────────────────────────────
    def _on_speed_change(self, *_):
        val = self.speed_var.get()
        self.speed_display.config(text=f"{int(val)} km/h")

    def _on_steer_change(self, *_):
        val = self.steer_var.get()
        angle_deg = val * (180 / math.pi)
        self.steer_angle_label.config(text=f"{angle_deg:.2f}°")

        if val < -0.1:
            direction, color = "← SOL", BLUE
        elif val > 0.1:
            direction, color = "SAĞ →", YELLOW
        else:
            direction, color = "DÜZ", GREEN
        self.steer_direction_label.config(text=direction, fg=color)

        self._draw_steering_wheel()

    def _toggle_nozzle(self, idx):
        current = self.nozzle_vars[idx].get()
        self.nozzle_vars[idx].set(0 if current else 1)
        self._update_nozzle_btn(idx)
        self._draw_boom_status()

    def _update_nozzle_btn(self, idx):
        val = self.nozzle_vars[idx].get()
        btn = self.nozzle_btns[idx]
        nozzle_labels_on = ["N1\n(Sol Dış) ✓", "N2\n(Sol İç) ✓", "N3\n(Sağ İç) ✓", "N4\n(Sağ Dış) ✓"]
        nozzle_labels_off = ["N1\n(Sol Dış)", "N2\n(Sol İç)", "N3\n(Sağ İç)", "N4\n(Sağ Dış)"]
        if val:
            btn.config(bg=NOZZLE_ON, text=nozzle_labels_on[idx] if idx < len(nozzle_labels_on) else f"N{idx+1}\nAÇIK")
        else:
            btn.config(bg=NOZZLE_OFF, text=nozzle_labels_off[idx] if idx < len(nozzle_labels_off) else f"N{idx+1}\nKAPALI")

    def _all_nozzles_on(self):
        for i in range(NUM_NOZZLES):
            self.nozzle_vars[i].set(1)
            self._update_nozzle_btn(i)
        self._draw_boom_status()

    def _all_nozzles_off(self):
        for i in range(NUM_NOZZLES):
            self.nozzle_vars[i].set(0)
            self._update_nozzle_btn(i)
        self._draw_boom_status()

    def _emergency_stop(self):
        self.speed_var.set(0.0)
        self.steer_var.set(0.0)
        self._all_nozzles_off()

    def _reset_all(self):
        self.speed_var.set(0.0)
        self.steer_var.set(0.0)
        self._all_nozzles_off()

    def _toggle_ai_mode(self):
        """Toggle AI auto-spray mode and send command to supervisor."""
        self.ai_mode = not self.ai_mode
        if self.ai_mode:
            self.ai_btn.config(text="🤖 AI: AKTİF", bg=GREEN)
            self._send_raw("AI_ON\n")
        else:
            self.ai_btn.config(text="🤖 AI: KAPALI", bg=NOZZLE_OFF)
            self._send_raw("AI_OFF\n")

    def _send_raw(self, text):
        """Send raw text to the supervisor."""
        with self.sock_lock:
            if self.connected and self.sock:
                try:
                    self.sock.sendall(text.encode('utf-8'))
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

    def _toggle_autopilot(self):
        """Toggle autonomous driving mode."""
        self.autopilot_mode = not self.autopilot_mode
        if self.autopilot_mode:
            self.auto_btn.config(text="🚀 OTONOM: AKTİF", bg=YELLOW)
            self._send_raw("AUTOPILOT_ON\n")
        else:
            self.auto_btn.config(text="🚀 OTONOM", bg=NOZZLE_OFF)
            self._send_raw("AUTOPILOT_OFF\n")

    # ── Connection ────────────────────────────────────────────────────
    def _toggle_connection(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect_async()

    def _connect_async(self):
        """Connect in a background thread to avoid UI freeze."""
        def connect():
            with self.sock_lock:
                old_sock = self.sock
                self.sock = None
                self.connected = False

            if old_sock:
                try:
                    old_sock.close()
                except OSError:
                    pass
                time.sleep(0.3)

            try:
                new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                new_sock.settimeout(3)
                new_sock.connect((SOCKET_HOST, SOCKET_PORT))
                new_sock.settimeout(1.0)

                with self.sock_lock:
                    self.sock = new_sock
                    self.connected = True
                    self._sock_generation += 1
                    gen = self._sock_generation

                self.root.after(0, lambda: self._set_connected_ui())
                logger.info("Webots'a bağlandı (gen=%d)", gen)

                # Start receiver
                recv_thread = threading.Thread(target=self._receive_loop, args=(gen,), daemon=True)
                recv_thread.start()

            except Exception as e:
                logger.warning("Bağlantı hatası: %s", e)
                self.root.after(0, lambda: self.status_text.set(f"Bağlantı hatası: {e}"))

        threading.Thread(target=connect, daemon=True).start()

    def _set_connected_ui(self):
        self.status_text.set("Bağlandı!")
        self.conn_indicator.config(text="● BAĞLI", fg=GREEN)
        self.connect_btn.config(text="BAĞLANTIYI KES", bg=RED)

    def _disconnect(self):
        self.connected = False
        with self.sock_lock:
            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None
        self.conn_indicator.config(text="● BAĞLI DEĞİL", fg=RED)
        self.connect_btn.config(text="BAĞLAN", bg=GREEN)
        self.status_text.set("Bağlantı kesildi.")

    def _receive_loop(self, gen):
        """Receive status updates from the supervisor."""
        while True:
            with self.sock_lock:
                sock = self.sock
                current_gen = self._sock_generation
                is_connected = self.connected

            if sock is None or not is_connected or current_gen != gen:
                break

            try:
                data = sock.recv(1024).decode('utf-8')
                if not data:
                    break
                lines = data.strip().split('\n')
                if lines:
                    self._parse_status(lines[-1])
            except socket.timeout:
                continue
            except (ConnectionResetError, BrokenPipeError, OSError):
                break

        # Only disconnect UI if we're still the active generation
        with self.sock_lock:
            if self._sock_generation == gen:
                self.connected = False
                self.root.after(0, lambda: self._disconnect())

    def _parse_status(self, status_str):
        """Parse: POS:x,y,z|SPEED:v|STEER:s|NOZZLES:n1,n2,n3,n4|MARKS:n|AI_MODE:m|DETECTIONS:d"""
        try:
            parts = status_str.split('|')
            for part in parts:
                if part.startswith('POS:'):
                    coords = part[4:].split(',')
                    pos_text = f"Pozisyon: ({float(coords[0]):.1f}, {float(coords[1]):.1f}, {float(coords[2]):.1f})"
                    self.root.after(0, lambda t=pos_text: self.position_label.config(text=t))
                elif part.startswith('MARKS:'):
                    mark_count = part[6:]
                    mark_text = f"İşaret: {mark_count}"
                    self.root.after(0, lambda t=mark_text: self.mark_label.config(text=t))
                elif part.startswith('AI_MODE:'):
                    mode = part[8:]
                    detections = ''
                    for p in parts:
                        if p.startswith('DETECTIONS:'):
                            detections = p[11:]
                    ai_text = f"AI: {mode} | Tespit: {detections}"
                    self.root.after(0, lambda t=ai_text: self.ai_status_label.config(text=t))
                elif part.startswith('STATS:'):
                    stats_text = part[6:]
                    self.root.after(0, lambda t=stats_text: self.stats_label.config(text=t))
        except (ValueError, IndexError) as e:
            logger.debug("Status parse hatası: %s", e)

    # ── Sender ────────────────────────────────────────────────────────
    def _start_sender(self):
        """Send commands at configured rate."""
        self._send_command()
        interval_ms = max(50, 1000 // UI_SEND_RATE_HZ)
        self.root.after(interval_ms, self._start_sender)

    def _send_command(self):
        with self.sock_lock:
            if not self.connected or not self.sock:
                return
            try:
                speed = self.speed_var.get()
                steer = self.steer_var.get()
                n = [self.nozzle_vars[i].get() for i in range(NUM_NOZZLES)]
                cmd = f"{speed},{steer},{n[0]},{n[1]},{n[2]},{n[3]}\n"
                self.sock.sendall(cmd.encode("utf-8"))
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.connected = False
                self.root.after(0, self._disconnect)


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("500x700")
    app = TractorUI(root)
    root.mainloop()
