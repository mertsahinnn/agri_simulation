import asyncio
import socket
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import json
import struct

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DashboardBackend")

app = FastAPI(title="Agri-Simulation Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serves the "ai/dataset" images to the browser directly
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
ai_dir = os.path.join(project_root, "ai")
app.mount("/ai", StaticFiles(directory=ai_dir), name="ai")

# ── Webots TCP Socket Settings ──
WEBOTS_HOST = "localhost"
WEBOTS_PORT = 5005
VIDEO_STREAM_PORT = 5006

# ── Video Streaming State ──
latest_frames = {i: None for i in range(4)}

async def handle_video_client(reader, writer):
    logger.info("Video stream source connected.")
    try:
        while True:
            header = await reader.readexactly(8)
            camera_id, length = struct.unpack('>II', header)
            frame_data = await reader.readexactly(length)
            latest_frames[camera_id] = frame_data
    except asyncio.IncompleteReadError:
        logger.warning("Video stream source disconnected.")
    except Exception as e:
        logger.error(f"Video stream error: {e}")
    finally:
        writer.close()

async def start_video_server():
    server = await asyncio.start_server(handle_video_client, '127.0.0.1', VIDEO_STREAM_PORT)
    logger.info(f"Video TCP Server listening on port {VIDEO_STREAM_PORT}")
    async with server:
        await server.serve_forever()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.webots_reader = None
        self.webots_writer = None
        self.webots_connected = False
        self.latest_telemetry = None

    async def broadcast_loop(self):
        while True:
            if self.latest_telemetry and len(self.active_connections) > 0:
                msg = self.latest_telemetry
                self.latest_telemetry = None
                await self.broadcast(json.dumps({"type": "telemetry", "data": msg}))
            await asyncio.sleep(0.02)  # 50 FPS — VRS nozzle gecikmesini minimuma indirir

    async def connect_client(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total clients: {len(self.active_connections)}")

    def disconnect_client(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")

    async def connect_to_webots(self):
        while True:
            try:
                logger.info(f"Attempting to connect to Webots at {WEBOTS_HOST}:{WEBOTS_PORT}...")
                self.webots_reader, self.webots_writer = await asyncio.open_connection(
                    WEBOTS_HOST, WEBOTS_PORT
                )
                self.webots_connected = True
                logger.info("Successfully connected to Webots Supervisor.")
                
                # Start reading from Webots
                while True:
                    data = await self.webots_reader.readline()
                    if not data:
                        logger.warning("Webots connection closed.")
                        break
                        
                    msg = data.decode('utf-8').strip()
                    if msg:
                        # Sadece en güncel telemetriyi kaydet (Eskileri çöpe at, UI gecikmesini engelle)
                        self.latest_telemetry = msg
                        
            except ConnectionRefusedError:
                logger.warning("Webots is not running or socket is not open. Retrying in 2 seconds...")
            except Exception as e:
                logger.error(f"Webots connection error: {e}")
                
            self.webots_connected = False
            if self.webots_writer:
                self.webots_writer.close()
            await asyncio.sleep(2)

    async def send_to_webots(self, command: str):
        if self.webots_connected and self.webots_writer:
            try:
                self.webots_writer.write((command + "\n").encode('utf-8'))
                await self.webots_writer.drain()
            except Exception as e:
                logger.error(f"Error sending command to Webots: {e}")

manager = ConnectionManager()

@app.on_event("startup")
async def startup_event():
    # Start the background task to bridge Webots and WebSockets
    asyncio.create_task(manager.connect_to_webots())
    asyncio.create_task(manager.broadcast_loop())
    asyncio.create_task(start_video_server())

async def frame_generator(camera_id: int):
    last_frame = None
    while True:
        frame_data = latest_frames.get(camera_id)
        if frame_data and frame_data != last_frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            last_frame = frame_data
        await asyncio.sleep(0.05)

@app.get("/stream/{camera_id}")
async def video_stream(camera_id: int):
    return StreamingResponse(frame_generator(camera_id), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect_client(websocket)
    try:
        while True:
            # Wait for any commands from the web UI (e.g., manual driving, toggles)
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                if payload.get("type") == "command":
                    cmd = payload.get("command", "")
                    # cmd could be "speed,steering,n1,n2,n3,n4", or "AI_ON", "AI_OFF", "AUTOPILOT_ON", etc.
                    await manager.send_to_webots(cmd)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect_client(websocket)

if __name__ == "__main__":
    import uvicorn
    # Make sure to run with: uvicorn dashboard_backend:app --host 0.0.0.0 --port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
