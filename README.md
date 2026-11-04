# Matiks & Visual Memory Bot (Retro Pixel Edition)

A high-performance automated bot for **Matiks** (`matiks.com`) Memory Duels and standard Visual Memory games, featuring an **8-bit arcade cyber HUD interface**.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-green.svg)
![Style](https://img.shields.io/badge/Aesthetic-8--Bit%20Pixel%20Retro-ff007f.svg)
![Status](https://img.shields.io/badge/Status-Working%20100%25-brightgreen.svg)

---

## 🕹️ Pixelated Arcade HUD (Zero AI Slop)

The bot comes with a custom **8-bit retro arcade floating HUD**:
- **Always-on-Top**: Floats unobtrusively in the corner of your screen while you play.
- **Chunky Pixel Buttons**: Instant one-click `[ ▶ ENGAGE BOT ]` and `[ ■ HALT BOT ]`.
- **On-The-Fly Speed Calibration**: Switch speeds mid-match without restarting:
  - `[ 1: SLOW ]` (~120ms / click - relaxed, safe)
  - `[ 2: MED ]` (~50ms / click - fast human reflexes)
  - `[ 3: FAST ]` (~16ms / click - competitive win)
  - `[ 4: BLITZ ]` (~5ms / click - instant godmode)
- **Live Arcade Telemetry**:
  - Live Status LED: `● [ STANDBY ]` / `● [ MEMORIZING ]` / `● [ BLITZING ]`
  - Real-time Stats: `ROUNDS WON`, `TILES CLEARED`, and `LAST REACTION MS`.
- **Auto-Restart Switch**: Toggle automatic clicking of the green `NEW GAME` button.

---

## 🎮 How to Launch

### 1. Launch the Pixelated GUI (Default)
Simply run:
```powershell
python main.py
```
A sleek, retro pixelated arcade controller window will appear floating on your screen. Click **`[ ▶ ENGAGE BOT ]`** to start playing!

### 2. Headless CLI Mode (Terminal Only)
If you prefer running without the graphical interface:
```powershell
python main.py --cli
```
You can also specify initial speed and monitor:
```powershell
python main.py --cli --speed fast
python main.py --cli --speed "extra fast"
```

---

## 🛑 Emergency Abort
- Push your mouse into the **top-left corner** of your monitor to trigger the instant PyAutoGUI failsafe.
- Or click **`[ ■ HALT BOT ]`** in the pixel HUD.
- Or press `Ctrl + C` in the console.

---

## 📁 Repository Structure

```
├── main.py              # Main bot engine & 8-bit retro pixel GUI
├── requirements.txt     # Dependencies (opencv, mss, pyautogui, etc.)
├── .gitignore           # Git ignore rules
└── README.md            # Documentation
```
