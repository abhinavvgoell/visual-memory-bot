# Visual Memory Bot (Human Benchmark)

A high-performance, automated computer-vision bot for the Visual Memory Test (Human Benchmark) built with OpenCV, MSS, and PyAutoGUI.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-green.svg)
![License](https://img.shields.io/badge/License-MIT-purple.svg)

---

## ⚡ Features & Fixes

1. **Sub-millisecond In-Memory Template Matching**:
   - Uses OpenCV template matching directly on `mss` frame captures with localized ROI caching.
   - Eliminates screenshot bottlenecks and achieves ~2ms response times.
2. **Multi-Monitor Coordinate Calibration**:
   - Automatically maps monitor left/top offsets so clicks hit the exact square across any monitor arrangement.
3. **Spatial Center Deduplication**:
   - Fixes duplicate clicks caused by nested contour edges (inner vs outer boundaries) using spatial distance filtering.
4. **Unified Speed Profiles**:
   - 4 built-in profiles (`fastest`, `fast`, `balanced`, `slow`) selectable via CLI argument or interactive prompt.
5. **Freeze Recovery Watchdog**:
   - Detects round stalls or premature resets and clears state automatically without locking up.
6. **Automatic 'New Game' Handling**:
   - Automatically detects game over and clicks "New Game" to restart runs.

---

## 🚀 Installation & Setup

```bash
# Clone the repository
git clone https://github.com/abhinavvgoell/visual-memory-bot.git
cd visual-memory-bot

# Install dependencies
pip install -r requirements.txt
```

---

## 🎮 Usage

### Interactive Menu
```bash
python main.py
```
*(Prompts for speed mode, default is `Fast`)*

### Direct Command-Line Flags
```bash
# Fast mode (Recommended - high speed & reliable):
python main.py --mode fast

# Fastest blitz mode (Sub-millisecond clicks):
python main.py --mode fastest

# Balanced mode (Human-like natural pacing):
python main.py --mode balanced

# Safe / Slow mode (1 click per second):
python main.py --mode slow

# Specify monitor (default is 1):
python main.py --mode fast --monitor 1
```

*Press **Ctrl + C** in the terminal to stop the bot at any time.*

---

## 📁 Project Structure

```
├── main.py              # Main bot application
├── you_indicator.png    # Player turn indicator template
├── new_game.png         # 'New Game' button template
├── new_game2.png        # Alternate 'New Game' template
├── requirements.txt     # Python dependencies
├── .gitignore           # Git ignore rules
└── README.md            # Documentation
```
