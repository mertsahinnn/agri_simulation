"""
Tractor Keyboard Controller (Legacy)
--------------------------------------
Direct socket-based tractor controller. Retained for backward compatibility.
Uses thread-safe socket access and proper logging.
"""
import sys
import os
import math
import socket
import threading
import logging

# ── Add project root to path for config import ───────────────────────
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import (
    SOCKET_HOST, SOCKET_PORT, MAX_SPEED, MAX_STEERING,
    LOG_FORMAT, LOG_LEVEL,
)

# ── Logging setup ─────────────────────────────────────────────────────
logging.basicConfig(format=LOG_FORMAT, level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("TractorKeyboard")

# ── Webots Driver ─────────────────────────────────────────────────────
try:
    from vehicle import Driver
except ImportError:
    webots_path = os.environ.get('WEBOTS_HOME', 'C:\\Program Files\\Webots')
    sys.path.append(os.path.join(webots_path, 'lib', 'controller', 'python'))
    try:
        from vehicle import Driver
    except ImportError:
        logger.critical("Webots modülleri bulunamadı! WEBOTS_HOME: %s", webots_path)
        sys.exit(1)

try:
    driver = Driver()
    timestep = int(driver.getBasicTimeStep())
    logger.info("Driver oluşturuldu, timestep: %dms", timestep)
except Exception as e:
    logger.critical("Driver oluşturulamadı: %s", e)
    sys.exit(1)

# ── State ─────────────────────────────────────────────────────────────
current_speed = 0.0
current_steering = 0.0

# ── Socket sunucusu ───────────────────────────────────────────────────
server_socket = None
client_socket = None
socket_lock = threading.Lock()


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


def handle_client():
    global current_speed, current_steering
    with socket_lock:
        sock = client_socket

    if sock is None:
        return

    try:
        while True:
            with socket_lock:
                if client_socket is not sock:
                    break

            try:
                data = sock.recv(1024).decode('utf-8')
            except (socket.timeout, ConnectionResetError, BrokenPipeError, OSError):
                break

            if not data:
                break

            messages = data.strip().split('\n')
            last_message = messages[-1] if messages else data

            parts = last_message.split(',')
            logger.debug("Veri alındı: %s", last_message)
            if len(parts) == 2:
                try:
                    current_speed = float(parts[0])
                    current_steering = float(parts[1])
                    logger.debug("Hız: %.2f m/s, Direksiyon: %.3f rad",
                                 current_speed, current_steering)
                except ValueError:
                    logger.warning("Veri formatı hatalı: %s", parts)
    except Exception as e:
        logger.error("Client hatası: %s", e)
    finally:
        logger.info("Client bağlantısı kesildi")
        with socket_lock:
            # only clear if it's the same socket
            pass
        try:
            sock.close()
        except OSError:
            pass


# ── Socket'i başlat ──────────────────────────────────────────────────
if not setup_socket():
    logger.warning("Socket olmadan devam ediliyor...")

logger.info("Webots traktör kontrolcüsü çalışıyor...")
logger.info("UI bağlantısı bekleniyor (port %d)...", SOCKET_PORT)

# ── Simulation loop ──────────────────────────────────────────────────
step_count = 0
while driver.step() != -1:
    step_count += 1

    if step_count % 500 == 0:
        logger.debug("Çalışıyor... Adım: %d, Hız: %.1f, Direksiyon: %.2f",
                      step_count, current_speed, current_steering)

    # Yeni bağlantı kontrol et
    if server_socket:
        try:
            with socket_lock:
                is_disconnected = (client_socket is None)

            if is_disconnected:
                new_client, addr = server_socket.accept()
                with socket_lock:
                    client_socket = new_client
                logger.info("UI bağlandı: %s", addr)
                client_thread = threading.Thread(target=handle_client, daemon=True)
                client_thread.start()
        except socket.timeout:
            pass
        except OSError as e:
            logger.warning("Bağlantı hatası: %s", e)
            with socket_lock:
                client_socket = None

    # Driver kontrolü
    driver.setCruisingSpeed(current_speed)
    driver.setSteeringAngle(current_steering)

logger.info("Kontrolcü sonlandırıldı")