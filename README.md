# 🕹️ Matiks & Visual Memory Bot (Retro Pixel Edition)

[![Build & Release](https://github.com/abhinavvgoell/visual-memory-bot/actions/workflows/build.yml/badge.svg)](https://github.com/abhinavvgoell/visual-memory-bot/actions/workflows/build.yml)
![Python](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-5C3EE8.svg?style=flat&logo=opencv&logoColor=white)
![Aesthetic](https://img.shields.io/badge/Aesthetic-8--Bit%20Pixel%20Arcade-00ffcc.svg?style=flat)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg?style=flat&logo=windows&logoColor=white)

An automated computer vision bot for **Matiks** (`matiks.com`) Memory Duels and standard Visual Memory games, featuring an authentic **8-bit arcade cyber HUD interface**, live speed calibration, dual button auto-restart, and instant global hotkey controls.

---

## ⚡ Key Features

- **🎮 Authentic 8-Bit Retro Pixel HUD**:
  - Always-on-top draggable floating arcade controller.
  - Custom pixel-beveled canvas buttons with tactile depression feedback.
  - Dynamically registers and renders bundled **Press Start 2P** arcade typography.
  - Recessed CRT scanline display with live telemetry (`ROUNDS WON`, `TILES CLEARED`, `REACTION MS`).

- **🏎️ Live 4-Speed Calibration**:
  - `[ 1: SLOW ]` (~120ms / click) — Relaxed, human pacing.
  - `[ 2: MED ]` (~50ms / click) — Sharp reflexes, natural rhythm.
  - `[ 3: FAST ]` (~16ms / click) — Highly competitive win-rate.
  - `[ 4: BLITZ ]` (~5ms / click) — Instant godmode speed.

- **🔄 Dual Auto-Restart Detection**:
  - Detects and automatically clicks **`▶ NEW MINDSNAP`** (red/coral button on aborted/finished screens).
  - Detects and automatically clicks **`NEW GAME`** (green button on defeat/victory summary screens).
  - Can be toggled on/off mid-game with the `[■] AUTO-RESTART` button.

- **🛡️ Failsafe & Instant Hotkeys**:
  - **`[F6]` Global Hotkey**: Press **F6** anywhere to instantly toggle between **ENGAGE** and **PAUSE**.
  - **4-Corner Emergency Abort**: Fling your cursor to any of the 4 screen corners to safely pause.
  - **Thread-Safe Re-engagement**: Armed guard system prevents lockups or false-positives when resuming.

---

## 🚀 Quick Start

### Option 1: Standalone Windows Executable (No Python Needed)
1. Head over to the **[GitHub Actions](https://github.com/abhinavvgoell/visual-memory-bot/actions)** tab or **Releases**.
2. Download `MatiksBot.exe` from the latest build.
3. Double-click `MatiksBot.exe` to launch the arcade HUD!

---

### Option 2: Run with Python

1. **Clone the repository**:
   ```powershell
   git clone https://github.com/abhinavvgoell/visual-memory-bot.git
   cd visual-memory-bot
   ```

2. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

3. **Launch the Bot**:
   ```powershell
   python main.py
   ```

---

## 🕹️ Controls & Usage

| Action | Control | Description |
|---|---|---|
| **Toggle Bot** | Click `▶ ENGAGE BOT` or press `F6` | Starts or halts the memory bot loop |
| **Emergency Pause** | Slide mouse to any screen corner | Pauses bot cleanly without crashing |
| **Calibrate Speed** | Click `SLOW`, `MED`, `FAST`, or `BLITZ` | Switches click delays on the fly |
| **Toggle Auto-Restart** | Click `[■] AUTO-RESTART` | Toggles auto-clicking of restart buttons |
| **Move Overlay** | Click & drag title bar | Reposition the HUD anywhere on your screen |

---

## 🖥️ Headless Terminal Mode (CLI)

Run the bot directly inside your command prompt without the GUI overlay:

```powershell
python main.py --cli
```

Custom speed and monitor parameters:
```powershell
# Set custom speed
python main.py --cli --speed extrafast

# Specify monitor (default is 1)
python main.py --cli --speed fast --monitor 1
```

---

## 📂 Repository Structure

```
├── .github/workflows/
│   └── build.yml        # Automated CI/CD: compiles Windows .exe & GitHub Releases
├── main.py              # Core computer vision engine & 8-bit retro Tkinter GUI
├── PressStart2P.ttf     # Dynamic 8-bit retro pixel arcade font
├── requirements.txt     # Python dependencies (OpenCV, MSS, PyAutoGUI, NumPy)
├── .gitignore           # Git ignore patterns
└── README.md            # Documentation
```

---

## 📜 License

MIT License. Free to use, modify, and build upon.
