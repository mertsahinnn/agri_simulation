import tkinter as tk
from tkinter import ttk
import socket
import threading
import math
import time

class TractorUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Webots Tractor + Sprayer Control")
        self.root.geometry("650x950")
        self.root.configure(bg="#f0f0f0")
        
        self.socket = None
        self.socket_lock = threading.Lock()
        self.connected = False
        self.nozzle_states = [0, 0, 0, 0]
        self._socket_generation = 0  # Tracks which socket is current
        
        # === MAIN TITLE ===
        title_frame = tk.Frame(root, bg="#2c3e50", height=60)
        title_frame.pack(fill=tk.X)
        
        title_label = tk.Label(title_frame, text="🚜 TRACTOR + SPRAYER CONTROL", 
                               font=("Arial", 16, "bold"), bg="#2c3e50", fg="white")
        title_label.pack(pady=15)
        
        # === MAIN CONTENT ===
        main_frame = tk.Frame(root, bg="#f0f0f0")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # === TOP: STEERING AND SPEED SIDE BY SIDE ===
        top_frame = tk.Frame(main_frame, bg="#f0f0f0")
        top_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # LEFT: STEERING WHEEL
        left_frame = tk.Frame(top_frame, bg="white", relief=tk.RAISED, bd=2)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        steering_title = tk.Label(left_frame, text="STEERING", 
                                  font=("Arial", 12, "bold"), bg="white", fg="#2c3e50")
        steering_title.pack(pady=10)
        
        self.canvas = tk.Canvas(left_frame, width=250, height=250, bg="white", 
                               relief=tk.FLAT, bd=0, cursor="hand2")
        self.canvas.pack(pady=10)
        
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        
        self.steering_var = tk.DoubleVar(value=0)
        self.steering_angle_label = tk.Label(left_frame, text="0.00°", 
                                            font=("Arial", 16, "bold"), bg="white", fg="#e74c3c")
        self.steering_angle_label.pack(pady=5)
        
        self.steering_direction_label = tk.Label(left_frame, text="STRAIGHT", 
                                                font=("Arial", 11, "bold"), bg="white", fg="#27ae60")
        self.steering_direction_label.pack(pady=(0, 10))
        
        # RIGHT: SPEED CONTROL
        right_frame = tk.Frame(top_frame, bg="white", relief=tk.RAISED, bd=2)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        speed_title = tk.Label(right_frame, text="SPEED", 
                              font=("Arial", 12, "bold"), bg="white", fg="#2c3e50")
        speed_title.pack(pady=10)
        
        speedometer_frame = tk.Frame(right_frame, bg="white")
        speedometer_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        max_label = tk.Label(speedometer_frame, text="20 km/h", 
                            font=("Arial", 10, "bold"), bg="white", fg="#27ae60")
        max_label.pack(side=tk.TOP)
        
        self.speed_var = tk.DoubleVar(value=0)
        self.speed_slider = ttk.Scale(speedometer_frame, from_=20, to=-20, orient=tk.VERTICAL,
                                      variable=self.speed_var, command=self.update_values)
        self.speed_slider.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        min_label = tk.Label(speedometer_frame, text="-20 km/h", 
                            font=("Arial", 10, "bold"), bg="white", fg="#e74c3c")
        min_label.pack(side=tk.BOTTOM)
        
        self.speed_label = tk.Label(right_frame, text="0 km/h", 
                                   font=("Arial", 14, "bold"), bg="white", fg="#3498db")
        self.speed_label.pack(pady=10)
        
        # === NOZZLE CONTROLS ===
        nozzle_frame = tk.Frame(main_frame, bg="white", relief=tk.RAISED, bd=2)
        nozzle_frame.pack(fill=tk.X, pady=10)
        
        nozzle_title = tk.Label(nozzle_frame, text="💧 SPRAY NOZZLES", 
                               font=("Arial", 12, "bold"), bg="white", fg="#2c3e50")
        nozzle_title.pack(pady=(10, 5))
        
        nozzle_btn_frame = tk.Frame(nozzle_frame, bg="white")
        nozzle_btn_frame.pack(fill=tk.X, padx=15, pady=5)
        
        self.nozzle_buttons = []
        nozzle_labels = ["N1\n(Sol Dış)", "N2\n(Sol İç)", "N3\n(Sağ İç)", "N4\n(Sağ Dış)"]
        
        for i in range(4):
            btn = tk.Button(nozzle_btn_frame, text=nozzle_labels[i], 
                           font=("Arial", 10, "bold"),
                           bg="#bdc3c7", fg="#2c3e50",
                           width=10, height=3,
                           relief=tk.RAISED, bd=2, cursor="hand2",
                           command=lambda idx=i: self.toggle_nozzle(idx))
            btn.pack(side=tk.LEFT, padx=8, pady=5, expand=True)
            self.nozzle_buttons.append(btn)
        
        all_btn_frame = tk.Frame(nozzle_frame, bg="white")
        all_btn_frame.pack(fill=tk.X, padx=15, pady=(5, 10))
        
        all_on_btn = tk.Button(all_btn_frame, text="✅ TÜM NOZZLE AÇ", 
                              command=self.all_nozzles_on, bg="#27ae60", fg="white",
                              font=("Arial", 10, "bold"), relief=tk.RAISED, bd=2,
                              padx=15, pady=6, cursor="hand2")
        all_on_btn.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        
        all_off_btn = tk.Button(all_btn_frame, text="❌ TÜM NOZZLE KAPAT", 
                               command=self.all_nozzles_off, bg="#e74c3c", fg="white",
                               font=("Arial", 10, "bold"), relief=tk.RAISED, bd=2,
                               padx=15, pady=6, cursor="hand2")
        all_off_btn.pack(side=tk.RIGHT, padx=5, expand=True, fill=tk.X)
        
        boom_frame = tk.Frame(nozzle_frame, bg="white")
        boom_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        self.boom_canvas = tk.Canvas(boom_frame, width=580, height=50, bg="white",
                                     relief=tk.FLAT, bd=0)
        self.boom_canvas.pack()
        self.draw_boom_status()
        
        # === STATUS ===
        status_frame = tk.Frame(main_frame, bg="#ecf0f1", relief=tk.SUNKEN, bd=2)
        status_frame.pack(fill=tk.X, pady=10)
        
        self.status_label = tk.Label(status_frame, text="Bağlı Değil", 
                                    font=("Arial", 11, "bold"), bg="#ecf0f1", fg="#e74c3c")
        self.status_label.pack(pady=4)
        
        self.position_label = tk.Label(status_frame, text="Pozisyon: ---", 
                                      font=("Arial", 9), bg="#ecf0f1", fg="#7f8c8d")
        self.position_label.pack(pady=(0, 4))
        
        self.mark_label = tk.Label(status_frame, text="İşaret sayısı: 0", 
                                  font=("Arial", 9), bg="#ecf0f1", fg="#7f8c8d")
        self.mark_label.pack(pady=(0, 6))
        
        # === CONTROL BUTTONS ===
        button_frame = tk.Frame(main_frame, bg="white", relief=tk.RAISED, bd=2)
        button_frame.pack(fill=tk.X, pady=5)
        
        button_label = tk.Label(button_frame, text="CONTROLS", 
                               font=("Arial", 11, "bold"), bg="white", fg="#2c3e50")
        button_label.pack(pady=(8, 5))
        
        buttons_container = tk.Frame(button_frame, bg="white")
        buttons_container.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        reset_btn = tk.Button(buttons_container, text="🔄 RESET", 
                             command=self.reset_values, bg="#3498db", fg="white",
                             font=("Arial", 10, "bold"), relief=tk.RAISED, bd=2, 
                             padx=20, pady=8, cursor="hand2")
        reset_btn.pack(side=tk.LEFT, padx=5)
        
        connect_btn = tk.Button(buttons_container, text="🔌 RECONNECT", 
                               command=self.reconnect, bg="#27ae60", fg="white",
                               font=("Arial", 10, "bold"), relief=tk.RAISED, bd=2, 
                               padx=20, pady=8, cursor="hand2")
        connect_btn.pack(side=tk.RIGHT, padx=5)
        
        # Canvas parametreleri
        self.canvas_center_x = 125
        self.canvas_center_y = 125
        self.canvas_radius = 90
        
        # Initial draw
        self.draw_steering_wheel()
        
        # Start recv thread (runs forever, waits for valid socket)
        recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        recv_thread.start()
        
        # Connect to Webots
        self.connect_to_controller()
    
    # ── Nozzle controls ───────────────────────────────────────────────
    
    def toggle_nozzle(self, idx):
        self.nozzle_states[idx] = 1 - self.nozzle_states[idx]
        self.update_nozzle_buttons()
        self.draw_boom_status()
        self.send_command()
    
    def all_nozzles_on(self):
        self.nozzle_states = [1, 1, 1, 1]
        self.update_nozzle_buttons()
        self.draw_boom_status()
        self.send_command()
    
    def all_nozzles_off(self):
        self.nozzle_states = [0, 0, 0, 0]
        self.update_nozzle_buttons()
        self.draw_boom_status()
        self.send_command()
    
    def update_nozzle_buttons(self):
        for i, btn in enumerate(self.nozzle_buttons):
            if self.nozzle_states[i]:
                btn.config(bg="#27ae60", fg="white", relief=tk.SUNKEN)
            else:
                btn.config(bg="#bdc3c7", fg="#2c3e50", relief=tk.RAISED)
    
    def draw_boom_status(self):
        self.boom_canvas.delete("all")
        w = 580
        self.boom_canvas.create_rectangle(40, 20, w - 40, 30, 
                                          fill="#7f8c8d", outline="#5d6d7e", width=2)
        nozzle_x_positions = [100, 220, 340, 460]
        nozzle_names = ["N1", "N2", "N3", "N4"]
        for i, x in enumerate(nozzle_x_positions):
            if self.nozzle_states[i]:
                color = "#27ae60"
                self.boom_canvas.create_line(x, 30, x - 15, 50, fill="#3498db", width=1, dash=(2, 2))
                self.boom_canvas.create_line(x, 30, x, 50, fill="#3498db", width=1, dash=(2, 2))
                self.boom_canvas.create_line(x, 30, x + 15, 50, fill="#3498db", width=1, dash=(2, 2))
            else:
                color = "#e74c3c"
            self.boom_canvas.create_oval(x - 8, 17, x + 8, 33, fill=color, outline="#2c3e50", width=2)
            self.boom_canvas.create_text(x, 8, text=nozzle_names[i], 
                                         font=("Arial", 8, "bold"), fill="#2c3e50")
    
    # ── Socket communication ──────────────────────────────────────────
    
    def send_command(self):
        """Send current state to Webots controller."""
        with self.socket_lock:
            if self.socket is None or not self.connected:
                return
            try:
                speed = self.speed_var.get()
                steering = self.steering_var.get()
                n = self.nozzle_states
                message = f"{speed},{steering},{n[0]},{n[1]},{n[2]},{n[3]}\n"
                self.socket.sendall(message.encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                print(f"Send error: {e}")
                self.connected = False
                # Don't reconnect here — let _recv_loop handle it
    
    def connect_to_controller(self):
        """Connect to Webots controller in background thread."""
        def connect():
            # Close old socket
            with self.socket_lock:
                old_sock = self.socket
                self.socket = None
                self.connected = False
            
            if old_sock:
                try:
                    old_sock.close()
                except:
                    pass
                time.sleep(0.3)  # Let old recv settle
            
            try:
                new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                new_sock.settimeout(3)
                new_sock.connect(('localhost', 5005))
                new_sock.settimeout(1.0)  # recv timeout
                
                with self.socket_lock:
                    self.socket = new_sock
                    self.connected = True
                    self._socket_generation += 1
                    gen = self._socket_generation
                
                self.root.after(0, lambda: self.status_label.config(
                    text="✅ Webots'a Bağlandı", fg="#27ae60"))
                print(f"Connected to Webots (gen={gen})")
                    
            except Exception as e:
                print(f"Connection failed: {e}")
                self.root.after(0, lambda: self.status_label.config(
                    text="❌ Bağlantı Başarısız - 3s sonra tekrar...", fg="#e74c3c"))
                self.root.after(3000, lambda: threading.Thread(target=connect, daemon=True).start())
        
        threading.Thread(target=connect, daemon=True).start()
    
    def _recv_loop(self):
        """Background: receive status updates. Runs forever."""
        while True:
            # Grab current socket and generation
            with self.socket_lock:
                sock = self.socket
                gen = self._socket_generation
                is_connected = self.connected
            
            if sock is None or not is_connected:
                time.sleep(0.5)
                continue
            
            try:
                data = sock.recv(1024).decode('utf-8')
                if not data:
                    # Connection closed by server
                    with self.socket_lock:
                        # Only mark disconnected if this is STILL the current socket
                        if self._socket_generation == gen:
                            self.connected = False
                            print(f"Server closed connection (gen={gen})")
                            self.root.after(0, lambda: self.status_label.config(
                                text="❌ Bağlantı kesildi", fg="#e74c3c"))
                            self.root.after(3000, self.reconnect)
                    time.sleep(2)
                    continue
                
                # Parse last complete line
                lines = data.strip().split('\n')
                if lines:
                    self.parse_status(lines[-1])
                    
            except socket.timeout:
                pass  # Normal — no data available
            except (ConnectionResetError, BrokenPipeError, OSError):
                with self.socket_lock:
                    # Only mark disconnected if this is STILL the current socket
                    if self._socket_generation == gen:
                        self.connected = False
                        print(f"Connection error (gen={gen})")
                        self.root.after(0, lambda: self.status_label.config(
                            text="❌ Bağlantı kesildi", fg="#e74c3c"))
                        self.root.after(3000, self.reconnect)
                time.sleep(2)
    
    def parse_status(self, status_str):
        """Parse: POS:x,y,z|SPEED:v|STEER:s|NOZZLES:n1,n2,n3,n4|MARKS:n"""
        try:
            parts = status_str.split('|')
            for part in parts:
                if part.startswith('POS:'):
                    coords = part[4:].split(',')
                    pos_text = f"Pozisyon: ({float(coords[0]):.1f}, {float(coords[1]):.1f}, {float(coords[2]):.1f})"
                    self.root.after(0, lambda t=pos_text: self.position_label.config(text=t))
                elif part.startswith('MARKS:'):
                    mark_count = part[6:]
                    mark_text = f"İşaret sayısı: {mark_count}"
                    self.root.after(0, lambda t=mark_text: self.mark_label.config(text=t))
        except:
            pass
    
    def reconnect(self):
        self.connect_to_controller()
    
    # ── Steering / Speed ──────────────────────────────────────────────
    
    def on_canvas_motion(self, event):
        dx = event.x - self.canvas_center_x
        dy = event.y - self.canvas_center_y
        distance = math.sqrt(dx**2 + dy**2)
        if distance <= self.canvas_radius:
            angle_rad = math.atan2(-dy, dx)
            angle_normalized = math.atan2(math.sin(angle_rad - math.pi/2), 
                                         math.cos(angle_rad - math.pi/2))
            steering_angle = max(-0.6, min(0.6, angle_normalized * 0.6 / (math.pi/2)))
            self.steering_var.set(steering_angle)
            self.update_values()
    
    def on_canvas_click(self, event):
        self.on_canvas_motion(event)
    
    def draw_steering_wheel(self):
        self.canvas.delete("all")
        cx, cy, r = self.canvas_center_x, self.canvas_center_y, self.canvas_radius
        
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                               outline="#2c3e50", width=4, fill="#ecf0f1")
        for i in range(0, 360, 45):
            a = math.radians(i)
            x1 = cx + r * 0.95 * math.cos(a)
            y1 = cy + r * 0.95 * math.sin(a)
            x2 = cx + r * 1.05 * math.cos(a)
            y2 = cy + r * 1.05 * math.sin(a)
            self.canvas.create_line(x1, y1, x2, y2, fill="#34495e", width=2)
        
        self.canvas.create_oval(cx - 25, cy - 25, cx + 25, cy + 25,
                               outline="#2c3e50", width=3, fill="#3498db")
        self.canvas.create_line(cx, cy - r * 0.85, cx, cy - r * 1.0,
                               fill="#2c3e50", width=4)
        
        sa = self.steering_var.get() + math.pi/2
        ex = cx + r * 0.65 * math.cos(sa)
        ey = cy - r * 0.65 * math.sin(sa)
        self.canvas.create_line(cx, cy, ex, ey, fill="#e74c3c", width=5)
        self.canvas.create_oval(ex - 5, ey - 5, ex + 5, ey + 5,
                               fill="#e74c3c", outline="#c0392b")
    
    def update_values(self, *args):
        speed = self.speed_var.get()
        steering = self.steering_var.get()
        
        self.speed_label.config(text=f"{int(speed)} km/h")
        
        angle_degrees = steering * (180 / math.pi)
        self.steering_angle_label.config(text=f"{angle_degrees:.2f}°")
        
        if steering < -0.1:
            direction, color = "← SOL", "#3498db"
        elif steering > 0.1:
            direction, color = "SAĞ →", "#e67e22"
        else:
            direction, color = "DÜZ", "#27ae60"
        self.steering_direction_label.config(text=direction, fg=color)
        
        self.draw_steering_wheel()
        self.send_command()
    
    def reset_values(self):
        self.speed_var.set(0)
        self.steering_var.set(0)
        self.nozzle_states = [0, 0, 0, 0]
        self.update_nozzle_buttons()
        self.draw_boom_status()
        self.send_command()

if __name__ == "__main__":
    root = tk.Tk()
    ui = TractorUI(root)
    root.mainloop()