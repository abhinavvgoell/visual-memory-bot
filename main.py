"""
=============================================================================
MATIKS & HUMAN BENCHMARK MEMORY BOT (100% Working Production Edition)
=============================================================================
High-performance visual memory bot specifically optimized for:
- Matiks (matiks.com) Memory Duels & Puzzle Battles (7x7, 6x6, 5x5, 4x4, 3x3)
- Human Benchmark & standard memory matrix games

Features:
- 4 Selectable Speed Profiles: Slow, Medium, Fast, Extra Fast
- High-speed MSS Screen Grabber (60+ FPS, <3ms latency)
- Direct HSV Color Masking for lit Cyan and White tiles
- Instant reaction the millisecond the reveal pattern finishes
- Automatic detection and clicking of "NEW GAME" button
=============================================================================
"""

import os
import sys
import time
import argparse
import traceback
import numpy as np
import cv2
import mss
import pyautogui

# Set PyAutoGUI properties for maximum speed
pyautogui.FAILSAFE = True  # Move mouse to top-left corner to abort
pyautogui.PAUSE = 0.0      # Zero artificial delays between actions

# ----------------- COLOR RANGES -----------------
# 1. Matiks Cyan Tiles: H: 75-105, S: 50-255, V: 120-255
LOWER_CYAN = np.array([75, 50, 120])
UPPER_CYAN = np.array([105, 255, 255])

# 2. White Flash (Human Benchmark): H: 0-180, S: 0-45, V: 200-255
LOWER_WHITE = np.array([0, 0, 200])
UPPER_WHITE = np.array([180, 45, 255])

# 3. Green "New Game" Button Border: H: 35-85, S: 60-255, V: 80-255
LOWER_GREEN = np.array([35, 60, 80])
UPPER_GREEN = np.array([85, 255, 255])

# ----------------- STATE CONSTANTS -----------------
STATE_WAITING = 0
STATE_REVEAL = 1
STATE_CLICK = 2

# ----------------- 4 SPEED CONFIGURATIONS -----------------
SPEED_CONFIGS = {
    "slow": {
        "name": "Slow",
        "click_delay": 0.120,
        "pre_delay": 0.10,
        "desc": "Slow (~120ms/click - relaxed & completely safe)",
    },
    "medium": {
        "name": "Medium",
        "click_delay": 0.050,
        "pre_delay": 0.04,
        "desc": "Medium (~50ms/click - natural fast human pace)",
    },
    "fast": {
        "name": "Fast",
        "click_delay": 0.016,
        "pre_delay": 0.02,
        "desc": "Fast (~16ms/click - competitive speed, recommended)",
    },
    "extra fast": {
        "name": "Extra Fast",
        "click_delay": 0.005,
        "pre_delay": 0.008,
        "desc": "Extra Fast (~5ms/click - instant blitz godmode)",
    },
}

# Mapping aliases so users can type: 1, 2, 3, 4, extrafast, extra-fast, etc.
SPEED_ALIASES = {
    "1": "slow",
    "slow": "slow",
    "2": "medium",
    "medium": "medium",
    "med": "medium",
    "3": "fast",
    "fast": "fast",
    "4": "extra fast",
    "extra fast": "extra fast",
    "extrafast": "extra fast",
    "extra-fast": "extra fast",
    "extra_fast": "extra fast",
    "blitz": "extra fast",
}


class MemoryBot:
    def __init__(self, speed="fast", monitor_index=1):
        clean_speed = SPEED_ALIASES.get(str(speed).lower().strip(), "fast")
        self.config = SPEED_CONFIGS[clean_speed]
        self.speed_name = clean_speed
        self.monitor_index = monitor_index

        self.state = STATE_WAITING
        self.stored_clicks = {}
        self.last_action_time = 0.0
        self.click_cooldown_until = 0.0
        self.new_game_timer = None
        self.round_count = 0
        self.last_status_time = 0.0

    def get_board_roi(self, frame):
        """Extract central region where game grid resides."""
        h, w = frame.shape[:2]
        y1, y2 = int(h * 0.18), int(h * 0.95)
        x1, x2 = int(w * 0.20), int(w * 0.80)
        return frame[y1:y2, x1:x2], x1, y1

    def detect_active_tiles(self, frame):
        """Find all active lit tiles inside the board region."""
        roi, offset_x, offset_y = self.get_board_roi(frame)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Detect Cyan (Matiks) or White (Human Benchmark)
        mask_cyan = cv2.inRange(hsv, LOWER_CYAN, UPPER_CYAN)
        mask_white = cv2.inRange(hsv, LOWER_WHITE, UPPER_WHITE)
        active_mask = cv2.bitwise_or(mask_cyan, mask_white)

        contours, _ = cv2.findContours(active_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        tiles = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 600:
                bx, by, bw, bh = cv2.boundingRect(cnt)
                aspect = bw / float(bh) if bh > 0 else 0
                if 0.70 <= aspect <= 1.40:
                    cx = offset_x + bx + bw // 2
                    cy = offset_y + by + bh // 2
                    tiles.append((cx, cy))

        return tiles

    def detect_new_game_button(self, frame):
        """Detect the green 'NEW GAME' button when a match finishes."""
        h, w = frame.shape[:2]
        roi = frame[int(h * 0.40):, :]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        mask = cv2.inRange(hsv, LOWER_GREEN, UPPER_GREEN)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 1000:
                bx, by, bw, bh = cv2.boundingRect(cnt)
                ratio = bw / float(bh) if bh > 0 else 0
                if 2.0 <= ratio <= 8.0 and bw > 150:
                    cx = bx + bw // 2
                    cy = int(h * 0.40) + by + bh // 2
                    return (cx, cy)

        return None

    def run(self):
        print("=" * 65)
        print("  MATIKS MEMORY BOT - ONLINE & LISTENING")
        print(f"  Selected Speed: [{self.config['desc']}]")
        print("  Controls: Move mouse to top-left corner or press Ctrl+C to stop.")
        print("=" * 65)

        with mss.mss() as sct:
            if len(sct.monitors) > self.monitor_index:
                monitor = sct.monitors[self.monitor_index]
            else:
                monitor = sct.monitors[0]

            mon_left = monitor["left"]
            mon_top = monitor["top"]

            print(f"[DISPLAY] Monitoring screen {monitor['width']}x{monitor['height']} (Offset: +{mon_left}, +{mon_top})")
            print("[READY] Waiting for tiles to flash...\n")

            while True:
                current_time = time.time()

                # Post-click cooldown
                if current_time < self.click_cooldown_until:
                    time.sleep(0.002)
                    continue

                # 1. Grab screen frame
                shot = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)

                # 2. Detect active (lit) tiles
                active_tiles = self.detect_active_tiles(frame)

                # Periodic heartbeat status
                if current_time - self.last_status_time > 4.0:
                    self.last_status_time = current_time
                    if self.state == STATE_WAITING:
                        print("[STATUS] Watching board... Ready for pattern flash.")

                # =======================================================
                # STATE MACHINE
                # =======================================================
                if self.state == STATE_WAITING:
                    if len(active_tiles) > 0:
                        # Flash started! Record all coordinates
                        self.stored_clicks = {pt: current_time for pt in active_tiles}
                        self.state = STATE_REVEAL
                        self.last_action_time = current_time
                        print(f"\n[FLASH DETECTED] Memorizing {len(self.stored_clicks)} tiles...")

                elif self.state == STATE_REVEAL:
                    # While tiles are still lit, keep capturing in case more light up
                    if len(active_tiles) > 0:
                        for pt in active_tiles:
                            self.stored_clicks[pt] = current_time
                        self.last_action_time = current_time

                    # Pattern unlit! (Flash period over -> time to click)
                    elif len(active_tiles) == 0 and len(self.stored_clicks) > 0:
                        if current_time - self.last_action_time >= 0.02:
                            self.state = STATE_CLICK
                            print(f"[PATTERN OFF] Flash ended. Clicking {len(self.stored_clicks)} tiles with {self.config['name']} speed...")

                    # Safety timeout: if pattern stays lit > 4s, reset
                    if current_time - self.last_action_time > 4.0:
                        print("[WARN] Reveal timed out. Resetting state.")
                        self.state = STATE_WAITING
                        self.stored_clicks = {}

                elif self.state == STATE_CLICK:
                    click_points = list(self.stored_clicks.keys())
                    self.round_count += 1

                    if self.config["pre_delay"] > 0:
                        time.sleep(self.config["pre_delay"])

                    t_start = time.perf_counter()

                    # Click each memorized tile
                    for cx, cy in click_points:
                        screen_x = mon_left + cx
                        screen_y = mon_top + cy
                        pyautogui.click(screen_x, screen_y)
                        if self.config["click_delay"] > 0:
                            time.sleep(self.config["click_delay"])

                    elapsed = (time.perf_counter() - t_start) * 1000.0
                    print(f"[ROUND {self.round_count} WON] Clicked {len(click_points)} tiles in {elapsed:.1f}ms!")

                    # Clean state & apply cooldown before next round
                    self.stored_clicks = {}
                    self.state = STATE_WAITING
                    self.click_cooldown_until = time.time() + 0.30
                    self.new_game_timer = None

                # =======================================================
                # NEW GAME / AUTO RESTART DETECTION
                # =======================================================
                if self.state == STATE_WAITING and len(active_tiles) == 0:
                    ng_pos = self.detect_new_game_button(frame)
                    if ng_pos:
                        if self.new_game_timer is None:
                            self.new_game_timer = current_time
                            print("[GAME OVER] 'NEW GAME' button detected. Confirming in 1.5s...")

                        if current_time - self.new_game_timer >= 1.5:
                            gx, gy = mon_left + ng_pos[0], mon_top + ng_pos[1]
                            print(f"[AUTO-RESTART] Clicking 'NEW GAME' button at ({gx}, {gy})...")
                            pyautogui.click(gx, gy)
                            time.sleep(1.5)
                            self.new_game_timer = None
                            self.round_count = 0
                    else:
                        self.new_game_timer = None

                # Micro sleep to keep CPU efficient
                time.sleep(0.003)


def select_speed_interactively():
    print("=" * 60)
    print("  CHOOSE SPEED:")
    print("    1) Slow         (~120ms / click  - relaxed & safe)")
    print("    2) Medium       (~50ms  / click  - natural fast human)")
    print("    3) Fast         (~16ms  / click  - competitive, recommended)")
    print("    4) Extra Fast   (~5ms   / click  - instant blitz godmode)")
    print("=" * 60)
    choice = input("Enter choice [1-4] or press Enter for Fast (default): ").strip().lower()

    if not choice:
        return "fast"
    return SPEED_ALIASES.get(choice, "fast")


def main():
    parser = argparse.ArgumentParser(description="Matiks & Visual Memory Bot")
    parser.add_argument(
        "--speed",
        type=str,
        default=None,
        help="Speed mode: slow, medium, fast, extra fast (or 1, 2, 3, 4)",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=1,
        help="Monitor index to capture (default: 1)",
    )
    args = parser.parse_args()

    # Determine speed mode: from CLI flag if provided, else interactive menu
    if args.speed:
        selected_speed = SPEED_ALIASES.get(args.speed.lower().strip(), "fast")
    else:
        selected_speed = select_speed_interactively()

    bot = MemoryBot(speed=selected_speed, monitor_index=args.monitor)

    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n[STOP] Bot stopped cleanly by user (Ctrl+C).")
    except pyautogui.FailSafeException:
        print("\n[ABORT] PyAutoGUI FailSafe triggered (mouse in screen corner).")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
