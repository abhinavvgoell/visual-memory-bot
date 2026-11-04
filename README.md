# Matiks & Visual Memory Bot

A high-performance, automated computer-vision bot specifically optimized for **Matiks** (`matiks.com`) Memory Duels and standard Visual Memory games.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-green.svg)
![Status](https://img.shields.io/badge/Status-Working%20100%25-brightgreen.svg)

---

## ⚡ Features

1. **Direct HSV Color Masking**: Instantly identifies cyan/teal lit tiles (Matiks) and pure white flashes (Human Benchmark) without relying on brittle edge contours.
2. **4 Selectable Speed Modes**: Choose between **Slow**, **Medium**, **Fast**, and **Extra Fast** via interactive startup prompt or command-line flag.
3. **Sub-Millisecond Screen Capture**: Uses `mss` for high FPS capture with virtually zero CPU overhead.
4. **Instant Reaction**: Memorizes all tile coordinates during the flash phase, and initiates clicks the exact millisecond the pattern unlits.
5. **Auto "NEW GAME" Detection**: Automatically locates the green "NEW GAME" button upon match completion and restarts.
6. **Failsafe Controls**: Move your mouse to the top-left corner of the screen at any moment or press `Ctrl + C` in the terminal to immediately abort.

---

## 🚀 Speed Profiles

| Profile | Click Delay | Behavior | Best Used For |
|---|---|---|---|
| **Slow** | ~120 ms | Calm, relaxed, fully human-like | Testing & 100% safe casual play |
| **Medium** | ~50 ms | Fast human reflexes | Daily duels, natural look |
| **Fast** (Default) | ~16 ms | Competitive high-speed | Consistently winning ranked matches |
| **Extra Fast** | ~5 ms | Instant blitz godmode | Sub-second puzzle clearing |

---

## 🎮 How to Run

### Interactive Menu
Run without arguments to choose your speed from the console:
```powershell
python main.py
```
```text
============================================================
  CHOOSE SPEED:
    1) Slow         (~120ms / click  - relaxed & safe)
    2) Medium       (~50ms  / click  - natural fast human)
    3) Fast         (~16ms  / click  - competitive, recommended)
    4) Extra Fast   (~5ms   / click  - instant blitz godmode)
============================================================
Enter choice [1-4] or press Enter for Fast (default):
```

### Direct Command-Line Flags
Launch straight into your preferred mode:
```powershell
# Slow mode
python main.py --speed slow

# Medium mode
python main.py --speed medium

# Fast mode (Default)
python main.py --speed fast

# Extra Fast mode
python main.py --speed "extra fast"
# (or: python main.py --speed extrafast)
```

---

## 📁 Project Structure

```
├── main.py              # Main memory bot with 4 speed profiles
├── requirements.txt     # Python dependencies
├── .gitignore           # Git ignore rules
└── README.md            # Documentation
```
