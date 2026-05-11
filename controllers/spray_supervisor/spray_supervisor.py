"""
Spray Supervisor Controller
----------------------------
A separate Robot with supervisor=TRUE that handles:
  - Socket server (port 5005) for UI communication
  - Spray visual toggling (transparency)
  - Ground mark placement
  - Tractor position tracking
  - Forwards driving commands to the Tractor via Emitter
  - AI-based weed detection and automatic nozzle control
"""
import sys
import os
import socket
import threading
import logging
import math
import time

# ── Add project root to path for config import ───────────────────────
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import (
    SOCKET_HOST, SOCKET_PORT,
    NUM_NOZZLES, NOZZLE_Y_OFFSETS, SPRAYER_X_OFFSET,
    SPRAY_OFF_TRANSPARENCY, SPRAY_ON_TRANSPARENCY,
    SPRAY_LIGHT_ON_INTENSITY, SPRAY_LIGHT_OFF_INTENSITY,
    MAX_MARKS, MARK_INTERVAL, MARK_HEIGHT, MARK_SIZE, MARK_COLOR, MARK_TRANSPARENCY,
    STATUS_SEND_INTERVAL_MS,
    AI_DETECTION_INTERVAL,
    LOG_FORMAT, LOG_LEVEL,
)

from controller import Supervisor

# ── Logging setup ─────────────────────────────────────────────────────
logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("SpraySupervisor")

# ── Initialize Supervisor ─────────────────────────────────────────────
supervisor = Supervisor()
timestep = int(supervisor.getBasicTimeStep())
logger.info("Spray Supervisor başlatıldı, timestep: %dms", timestep)

# ── Emitter for sending commands to Tractor ───────────────────────────
emitter = supervisor.getDevice("emitter")
logger.info("Emitter bulundu")

# ── Camera + AI Weed Detection ────────────────────────────────────────
from weed_detector import WeedDetector

camera_names = ["camera_1", "camera_2", "camera_3", "camera_4"]
cameras = [supervisor.getDevice(name) for name in camera_names]
weed_detector = WeedDetector(cameras, timestep)

# AI mode: True = automatic nozzle control, False = manual (UI) control
ai_mode = False
logger.info("AI Tespit Sistemi: %s", "HAZIR" if weed_detector.is_enabled else "DEVRE DIŞI")

# ── Statistics ────────────────────────────────────────────────────────
from statistics import SprayStatistics
stats = SprayStatistics(timestep)
logger.info("İstatistik modülü başlatıldı")

# ── Autopilot ────────────────────────────────────────────────────────
from autopilot import Autopilot

# Crop row Y positions (match world file)
ROW_Y_POSITIONS = [-20, -16, -12, -8, -4, 0, 4, 8, 12, 16]
autopilot = Autopilot(ROW_Y_POSITIONS, row_x_start=-18, row_x_end=18,
                      driving_speed=8.0, turning_speed=4.0)
logger.info("Autopilot hazır")

# ── Socket server setup ───────────────────────────────────────────────
server_socket = None
client_socket = None
socket_lock = threading.Lock()

current_speed = 0.0
current_steering = 0.0
nozzle_states = [0.0] * NUM_NOZZLES
prev_nozzle_states = [0.0] * NUM_NOZZLES

tank_level = 1000.0  # liters
TANK_MAX = 1000.0
FLOW_RATE = 10.0 # liters per second per nozzle at 1.0 intensity


def setup_socket():
    global server_socket
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((SOCKET_HOST, SOCKET_PORT))
        server_socket.listen(1)
        server_socket.settimeout(0.5)
        logger.info("Socket sunucusu başlatıldı (port %d)", SOCKET_PORT)
        return True
    except OSError as e:
        logger.error("Socket hatası: %s", e)
        return False


def send_status(tractor_pos):
    """Send tractor status to UI."""
    with socket_lock:
        if client_socket is None:
            return
        try:
            n = nozzle_states
            ai_str = "AUTO" if ai_mode else "MANUAL"
            detections = weed_detector.total_detections if weed_detector.is_enabled else 0
            stats_str = stats.get_status_string()
            auto_str = autopilot.get_status_string() if autopilot.is_active else ""
            status = (f"POS:{tractor_pos[0]:.2f},{tractor_pos[1]:.2f},{tractor_pos[2]:.2f}"
                      f"|SPEED:{current_speed:.1f}"
                      f"|STEER:{current_steering:.3f}"
                      f"|NOZZLES:{n[0]:.2f},{n[1]:.2f},{n[2]:.2f},{n[3]:.2f}"
                      f"|MARKS:{mark_counter}"
                      f"|AI_MODE:{ai_str}"
                      f"|DETECTIONS:{detections}"
                      f"|STATS:{stats_str}"
                      f"|TANK:{tank_level:.1f}/{TANK_MAX:.1f}"
                      f"|AUTOPILOT:{auto_str}\n")
            client_socket.sendall(status.encode('utf-8'))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


def handle_client():
    """Handle incoming commands from the UI."""
    global client_socket, current_speed, current_steering, nozzle_states, ai_mode

    buffer = ""

    with socket_lock:
        sock = client_socket

    if sock is None:
        return

    try:
        while True:
            try:
                data = sock.recv(1024).decode('utf-8')
            except socket.timeout:
                continue
            except (ConnectionResetError, BrokenPipeError, OSError):
                break

            if not data:
                break

            buffer += data

            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                if not line:
                    continue

                parts = line.split(',')

                if len(parts) >= 6:
                    try:
                        current_speed = float(parts[0])
                        current_steering = float(parts[1])
                        if not ai_mode:
                            for i in range(NUM_NOZZLES):
                                nozzle_states[i] = float(parts[2 + i])
                        logger.debug("Hız: %.1f, Direksiyon: %.3f, Nozzle: %s",
                                     current_speed, current_steering, nozzle_states)
                    except ValueError:
                        logger.warning("Veri formatı hatalı: %s", parts)
                elif len(parts) == 2:
                    try:
                        current_speed = float(parts[0])
                        current_steering = float(parts[1])
                    except ValueError:
                        logger.warning("Veri formatı hatalı: %s", parts)
                # Handle AI mode toggle command
                elif line.strip().upper() == 'AI_ON':
                    ai_mode = True
                    logger.info("AI modu AKTİF")
                elif line.strip().upper() == 'AI_OFF':
                    ai_mode = False
                    logger.info("AI modu DEVRE DIŞI")
                elif line.strip().upper() == 'AUTOPILOT_ON':
                    # Traktörün mevcut pozisyonunu ve bakış yönünü al
                    if tractor_node:
                        t_pos = tractor_node.getPosition()
                        t_rot = tractor_node.getOrientation()
                        import math as _math
                        t_heading = _math.atan2(t_rot[3], t_rot[0])
                        autopilot.start(tractor_pos=t_pos, tractor_heading=t_heading)
                    else:
                        autopilot.start()
                    logger.info("Autopilot başlatıldı")
                elif line.strip().upper() == 'AUTOPILOT_OFF':
                    autopilot.stop()
                    logger.info("Autopilot durduruldu")

    except Exception as e:
        logger.error("Client hatası: %s", e)
    finally:
        logger.info("Client bağlantısı kesildi")
        with socket_lock:
            if client_socket is sock:
                client_socket = None
        try:
            sock.close()
        except OSError:
            pass


# ── Find Tractor node ─────────────────────────────────────────────────
tractor_node = supervisor.getFromDef("TRACTOR")

# Fallback: find tractor by searching scene tree for node named "vehicle"
if tractor_node is None:
    logger.info("DEF TRACTOR bulunamadı, isimle aranıyor...")
    root_temp = supervisor.getRoot()
    if root_temp:
        children_temp = root_temp.getField("children")
        if children_temp:
            for i in range(children_temp.getCount()):
                try:
                    node = children_temp.getMFNode(i)
                    if node:
                        type_name = node.getTypeName()
                        if type_name == "Tractor":
                            tractor_node = node
                            logger.info("Traktör isimle bulundu (index %d, type: %s)", i, type_name)
                            break
                except Exception as e:
                    logger.debug("Node %d erişim hatası: %s", i, e)

if tractor_node:
    logger.info("Traktör bulundu (type: %s)", tractor_node.getTypeName())
else:
    logger.warning("Traktör bulunamadı! Ground mark devre dışı.")


# ── Find Sprayer node inside Tractor's sensorSlot ─────────────────────
sprayer_node = None
if tractor_node:
    sensor_slot = tractor_node.getField("sensorSlot")
    if sensor_slot and sensor_slot.getCount() > 0:
        for idx in range(sensor_slot.getCount()):
            node = sensor_slot.getMFNode(idx)
            if node and node.getTypeName() == "Sprayer":
                sprayer_node = node
                logger.info("Sprayer bulundu (index %d)", idx)
                break
        if sprayer_node is None:
            logger.warning("Sprayer node'u sensorSlot içinde bulunamadı")
    else:
        logger.warning("sensorSlot boş veya erişilemedi")

# ── Find spray visual and light nodes inside Sprayer PROTO ────────────
spray_visual_transparency_fields = []
spray_light_intensity_fields = []


def find_spray_def(def_name):
    """Find a DEF node inside the Sprayer PROTO."""
    # Method 1: getFromProtoDef on Sprayer node
    if sprayer_node:
        try:
            node = sprayer_node.getFromProtoDef(def_name)
            if node:
                return node
        except (AttributeError, Exception):
            pass

    # Method 2: Global getFromDef
    try:
        node = supervisor.getFromDef(def_name)
        if node:
            return node
    except Exception:
        pass

    return None


for i in range(1, NUM_NOZZLES + 1):
    visual_node = find_spray_def(f"SPRAY_VISUAL_{i}")
    if visual_node:
        children_field = visual_node.getField("children")
        if children_field and children_field.getCount() > 0:
            shape_node = children_field.getMFNode(0)
            if shape_node:
                app_field = shape_node.getField("appearance")
                if app_field:
                    app_node = app_field.getSFNode()
                    if app_node:
                        transp_field = app_node.getField("transparency")
                        if transp_field:
                            spray_visual_transparency_fields.append(transp_field)
                            transp_field.setSFFloat(SPRAY_OFF_TRANSPARENCY)
                            logger.info("SPRAY_VISUAL_%d OK", i)
                        else:
                            spray_visual_transparency_fields.append(None)
                    else:
                        spray_visual_transparency_fields.append(None)
                else:
                    spray_visual_transparency_fields.append(None)
            else:
                spray_visual_transparency_fields.append(None)
        else:
            spray_visual_transparency_fields.append(None)
    else:
        spray_visual_transparency_fields.append(None)
        logger.warning("SPRAY_VISUAL_%d bulunamadı", i)

    light_node = find_spray_def(f"SPRAY_LIGHT_{i}")
    if light_node:
        intensity_field = light_node.getField("intensity")
        if intensity_field:
            spray_light_intensity_fields.append(intensity_field)
            intensity_field.setSFFloat(SPRAY_LIGHT_OFF_INTENSITY)
            logger.info("SPRAY_LIGHT_%d OK", i)
        else:
            spray_light_intensity_fields.append(None)
    else:
        spray_light_intensity_fields.append(None)
        logger.warning("SPRAY_LIGHT_%d bulunamadı", i)

found_visuals = len([f for f in spray_visual_transparency_fields if f])
found_lights = len([f for f in spray_light_intensity_fields if f])
logger.info("%d spray visual, %d light bulundu", found_visuals, found_lights)

# ── Root node for ground marks ────────────────────────────────────────
root_node = supervisor.getRoot()
root_children_field = None
if root_node:
    root_children_field = root_node.getField("children")
    if root_children_field:
        logger.info("Root children field bulundu (ground mark aktif)")
    else:
        logger.warning("Root children field bulunamadı")
else:
    logger.warning("Root node bulunamadı")

mark_counter = 0

# ── Helper functions ──────────────────────────────────────────────────

def get_nozzle_world_position(tractor_pos, tractor_rotation, nozzle_idx):
    """Calculate world position of a nozzle based on tractor pose."""
    rot_matrix = tractor_node.getOrientation()
    cos_a = rot_matrix[0]
    sin_a = rot_matrix[3]

    local_x = SPRAYER_X_OFFSET
    local_y = NOZZLE_Y_OFFSETS[nozzle_idx]

    world_x = tractor_pos[0] + local_x * cos_a - local_y * sin_a
    world_y = tractor_pos[1] + local_x * sin_a + local_y * cos_a

    return world_x, world_y


def place_ground_mark(x, y):
    """Place a colored mark on the ground using Supervisor API."""
    global mark_counter
    if root_children_field is None or mark_counter >= MAX_MARKS:
        return

    mark_counter += 1
    r, g, b = MARK_COLOR
    sx, sy, sz = MARK_SIZE
    mark_string = (
        f'Pose {{'
        f'  translation {x:.3f} {y:.3f} {MARK_HEIGHT} '
        f'  children ['
        f'    Shape {{'
        f'      appearance PBRAppearance {{'
        f'        baseColor {r} {g} {b} '
        f'        metalness 0 '
        f'        roughness 1 '
        f'        transparency {MARK_TRANSPARENCY} '
        f'      }}'
        f'      geometry Box {{'
        f'        size {sx} {sy} {sz} '
        f'      }}'
        f'    }}'
        f'  ]'
        f'}}'
    )
    try:
        root_children_field.importMFNodeFromString(-1, mark_string)
    except Exception as e:
        logger.warning("Mark oluşturma hatası: %s", e)


def update_spray_visuals():
    """Toggle spray cone visuals and lights based on nozzle states (variable rate)."""
    for i in range(NUM_NOZZLES):
        intensity = nozzle_states[i] # 0.0 to 1.0 (float)
        
        if intensity != prev_nozzle_states[i]:
            if i < len(spray_visual_transparency_fields) and spray_visual_transparency_fields[i]:
                try:
                    # Variable transparency
                    t = SPRAY_OFF_TRANSPARENCY - intensity * (SPRAY_OFF_TRANSPARENCY - SPRAY_ON_TRANSPARENCY)
                    spray_visual_transparency_fields[i].setSFFloat(t)
                except Exception:
                    pass

            if i < len(spray_light_intensity_fields) and spray_light_intensity_fields[i]:
                try:
                    # Variable intensity
                    light_val = SPRAY_LIGHT_OFF_INTENSITY + intensity * (SPRAY_LIGHT_ON_INTENSITY - SPRAY_LIGHT_OFF_INTENSITY)
                    spray_light_intensity_fields[i].setSFFloat(light_val)
                except Exception:
                    pass

            state_str = f"AÇIK ({intensity:.2f})" if intensity > 0 else "KAPALI"
            if abs(intensity - prev_nozzle_states[i]) > 0.1: # Only log major changes
                logger.info("Nozzle %d: %s", i + 1, state_str)

            prev_nozzle_states[i] = intensity


def send_driving_command():
    """Send speed and steering to the Tractor via Emitter."""
    message = f"{current_speed},{current_steering}"
    emitter.send(message.encode('utf-8'))


# ── Main setup ────────────────────────────────────────────────────────
if not setup_socket():
    logger.warning("Socket olmadan devam ediliyor...")

logger.info("=" * 55)
logger.info("Spray Supervisor Kontrolcüsü")
logger.info("=" * 55)
logger.info("UI bağlantısı bekleniyor (port %d)...", SOCKET_PORT)
logger.info("Komut formatı: speed,steering,n1,n2,n3,n4")
logger.info("AI modu: 'AI_ON' / 'AI_OFF' komutu ile değiştirilebilir")
logger.info("Sprey açıkken yerde işaret bırakılacak")
logger.info("=" * 55)

# ── Get own node for position teleport (camera follows tractor) ───────
own_node = supervisor.getSelf()
own_translation_field = None
own_rotation_field = None
if own_node:
    own_translation_field = own_node.getField("translation")
    own_rotation_field = own_node.getField("rotation")
    logger.info("Supervisor self-node bulundu (kamera takip aktif)")
else:
    logger.warning("Supervisor self-node bulunamadı")

# ── Simulation loop ──────────────────────────────────────────────────
step_count = 0

while supervisor.step(timestep) != -1:
    step_count += 1

    # ── Accept new client connections ──
    with socket_lock:
        is_disconnected = (client_socket is None)

    if is_disconnected and server_socket:
        try:
            new_client, addr = server_socket.accept()
            new_client.settimeout(0.1)
            with socket_lock:
                client_socket = new_client
            logger.info("UI bağlandı: %s", addr)
            client_thread = threading.Thread(target=handle_client, daemon=True)
            client_thread.start()
        except socket.timeout:
            pass
        except OSError as e:
            logger.warning("Accept hatası: %s", e)

    # ── Teleport supervisor to tractor position (camera follows) ──
    if tractor_node and own_translation_field:
        tractor_pos = tractor_node.getPosition()
        tractor_rot_field = tractor_node.getField("rotation")
        own_translation_field.setSFVec3f(list(tractor_pos))
        if own_rotation_field and tractor_rot_field:
            try:
                rot = tractor_rot_field.getSFRotation()
                own_rotation_field.setSFRotation(rot)
            except Exception:
                pass

    # ── AI Weed Detection ──
    if ai_mode and weed_detector.is_enabled and step_count % AI_DETECTION_INTERVAL == 0:
        if tank_level > 0.0:
            ai_nozzles = weed_detector.detect()
            nozzle_changed = False
            for i in range(NUM_NOZZLES):
                if abs(nozzle_states[i] - ai_nozzles[i]) > 0.01:
                    nozzle_changed = True
                nozzle_states[i] = ai_nozzles[i]
            
            # Nozzle değiştiğinde telemetriyi BEKLEMEDEN hemen gönder!
            # Bu sayede VRS paneli, Sunum Modu ile aynı anda tepki verir.
            if nozzle_changed and tractor_node:
                tractor_pos = tractor_node.getPosition()
                send_status(tractor_pos)
            
            if any(v > 0 for v in ai_nozzles) and step_count % 50 == 0:
                logger.info("AI tespit: Nozzle durumu = %s", [f"{v:.2f}" for v in ai_nozzles])
        else:
            nozzle_states = [0.0] * NUM_NOZZLES

    # ── Tank Logic ──
    if tank_level <= 0.0:
        if current_speed != 0.0 or any(v > 0 for v in nozzle_states) or autopilot.is_active:
            current_speed = 0.0
            autopilot.stop()
            nozzle_states = [0.0] * NUM_NOZZLES
            # Send warning only once or periodically
            if step_count % (STATUS_SEND_INTERVAL_MS * 10 // timestep) == 0:
                logger.warning("TANK BOŞ! Sistem durduruldu.")
    else:
        # Reduce tank based on current nozzle intensities
        dt = timestep / 1000.0
        consumption = sum(nozzle_states) * FLOW_RATE * dt
        tank_level = max(0.0, tank_level - consumption)

    # ── Autopilot ──
    if autopilot.is_active and tractor_node:
        tractor_pos = tractor_node.getPosition()
        tractor_rot = tractor_node.getOrientation()
        auto_speed, auto_steering = autopilot.compute(tractor_pos, tractor_rot, dt=(timestep / 1000.0))
        current_speed = auto_speed
        current_steering = auto_steering

    # ── Send driving command to Tractor every step ──
    send_driving_command()

    # ── Update spray visuals ──
    update_spray_visuals()

    # ── Place ground marks ──
    if tractor_node and step_count % MARK_INTERVAL == 0:
        tractor_pos = tractor_node.getPosition()
        tractor_rot = tractor_node.getOrientation()

        any_nozzle_on = False
        for i in range(NUM_NOZZLES):
            if nozzle_states[i]:
                any_nozzle_on = True
                wx, wy = get_nozzle_world_position(tractor_pos, tractor_rot, i)
                place_ground_mark(wx, wy)

        if any_nozzle_on and mark_counter % 50 == 0:
            logger.info("Toplam yer işareti: %d", mark_counter)

    # ── Update statistics ──
    t_pos = tractor_node.getPosition() if tractor_node else None
    stats.update(nozzle_states, ai_mode, t_pos, mark_counter)

    # ── Send status update every ~500ms ──
    if step_count % max(1, STATUS_SEND_INTERVAL_MS // timestep) == 0 and tractor_node:
        tractor_pos = tractor_node.getPosition()
        send_status(tractor_pos)

# ── Simulation ended – export CSV ─────────────────────────────────────
logger.info("Simülasyon sonlandı. İstatistikler kaydediliyor...")
stats.export_csv()
logger.info("Final istatistik: %s", stats.get_status_string())
