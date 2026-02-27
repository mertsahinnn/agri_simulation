# 🚜 Agricultural Spraying Simulation

AI-powered precision spraying simulation built with **Webots R2025a**. A tractor-mounted 4-nozzle boom sprayer uses computer vision to distinguish weeds from crops, reducing pesticide waste.

## Project Structure

```
agri_simulation/
├── config.py                     # Central configuration
├── controllers/
│   ├── spray_supervisor/         # Supervisor: socket server, spray visuals, ground marks
│   ├── tractor_sprayer_controller/  # Tractor driver + UI
│   └── tractor_keyboard_controller/ # Legacy keyboard controller
├── protos/
│   ├── Sprayer.proto             # 4-nozzle boom sprayer model
│   └── SandyGround.proto        # Ground appearance
├── ui/                           # Standalone UI (legacy)
└── worlds/
    └── agri_robot.wbt            # Main simulation world
```

## How to Run

1. **Open** `worlds/agri_robot.wbt` in Webots R2025a
2. **Start** the simulation — controllers load automatically
3. **Launch UI** (optional): `python controllers/tractor_sprayer_controller/tractor_ui.py`
4. Click **BAĞLAN** (Connect) in the UI to control the tractor

## Architecture

- **Spray Supervisor** (`spray_supervisor.py`): Runs as a Webots Supervisor robot. Hosts a TCP socket server (port 5005), receives commands from the UI, forwards driving commands to the tractor via Emitter/Receiver, and manages spray visual effects + ground marks.
- **Tractor Driver** (`tractor_sprayer_controller.py`): Receives speed/steering commands from the Supervisor via Receiver and applies them using the Driver API.
- **UI** (`tractor_ui.py`): Tkinter-based dark-themed control panel with speed, steering, and nozzle controls.

## Requirements

- Webots R2025a
- Python 3.10+
