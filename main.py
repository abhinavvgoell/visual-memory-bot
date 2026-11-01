"""
=============================================================================
VISUAL MEMORY BOT - MAIN
=============================================================================
High-performance computer vision bot for Human Benchmark Visual Memory.
Captures screen frames using MSS, detects memory tiles and active patterns 
using OpenCV & scikit-learn, and executes optimal click sequences.

Features:
- Sub-millisecond OpenCV in-memory template matching with ROI caching
- Multi-monitor coordinate translation
- Spatial tile deduplication (prevents double-clicking inner/outer edges)
- 4 Switchable Speed Profiles: Fastest, Fast (Default), Balanced, Slow
- Automatic 'New Game' button detection and click
- Built-in watchdog freeze recovery
=============================================================================
"""

import os
import sys
import time
import argparse
import numpy as np
import cv2
import mss
import pyautogui
from sklearn.cluster import DBSCAN

# Disable pyautogui internal pauses for maximum speed and fine-grained control
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# ----------------- PATHS & ASSETS -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

YOU_IMAGE_PATH = os.path.join(BASE_DIR, "you_indicator.png")
NEW_GAME_IMAGE_PATH = os.path.join(BASE_DIR, "new_game.png")
NEW_GAME2_IMAGE_PATH = os.path.join(BASE_DIR, "new_game2.png")

# Preset fallback coordinates for 'New Game' button
FALLBACK_NEW_GAME_X = 1093
FALLBACK_NEW_GAME_Y = 838

# Color thresholds for active (lit) tiles in HSV
LOWER_CYAN = np.array([70, 80, 120])
UPPER_CYAN = np.array([115, 255, 255])

# State Machine Definitions
STATE_WAITING = 0
STATE_REVEAL = 1
STATE_CLICK = 2

# ----------------- SPEED PROFILES -----------------
SPEED_PROFILES = {
    "fastest": {
        "label": "Fastest (Sub-millisecond blitz)",
        "reveal_settle_delay": 0.015,
        "pre_click_delay": 0.01,
        "inter_click_delay": 0.005,
        "mouse_duration": 0.0,
        "cooldown_after_click": 0.15,
        "check_you_during_clicks": False,
    },
    "fast": {
        "label": "Fast (High speed, reliable - Recommended)",
        "reveal_settle_delay": 0.025,
        "pre_click_delay": 0.02,
        "inter_click_delay": 0.018,
        "mouse_duration": 0.005,
        "cooldown_after_click": 0.25,
        "check_you_during_clicks": True,
    },
    "balanced": {
        "label": "Balanced (Human-like pacing)",
        "reveal_settle_delay": 0.06,
        "pre_click_delay": 0.04,
        "inter_click_delay": 0.06,
        "mouse_duration": 0.03,
        "cooldown_after_click": 0.35,
        "check_you_during_clicks": True,
    },
    "slow": {
        "label": "Slow (Safe mode - ~1 click per second)",
        "reveal_settle_delay": 0.2,
        "pre_click_delay": 0.3,
        "inter_click_delay": 0.8,
        "mouse_duration": 0.2,
        "cooldown_after_click": 0.5,
        "check_you_during_clicks": True,
    },
}


class MemoryBot:
    def __init__(self, mode="fast", monitor_index=1):
        self.profile = SPEED_PROFILES.get(mode, SPEED_PROFILES["fast"])
        self.mode_name = mode
        self.monitor_index = monitor_index

        # Pre-load image templates in grayscale
        self.template_you = self._load_template(YOU_IMAGE_PATH)
        self.template_new_game = self._load_template(NEW_GAME_IMAGE_PATH)
        self.template_new_game2 = self._load_template(NEW_GAME2_IMAGE_PATH)

        # State tracking
        self.state = STATE_WAITING
        self.stored_clicks = []
        self.last_action_time = 0.0
        self.click_cooldown_until = 0.0
        self.new_game_timer = None
        self.last_you_loc = None  # Cache for fast ROI re-checking

    def _load_template(self, path):
        if not os.path.exists(path):
            return None
        return cv2.imread(path, cv2.IMREAD_GRAYSCALE)

    def match_template(self, gray_frame, template, threshold=0.75, cached_pos=None):
        """
        Fast in-memory template matching using OpenCV.
        Checks a localized ROI first if cached_pos is provided.
        """
        if template is None or gray_frame is None:
            return None

        th, tw = template.shape[:2]
        fh, fw = gray_frame.shape[:2]

        if fh < th or fw < tw:
            return None

        # Check cached region first if available (speeds up repeated searches)
        if cached_pos:
            cx, cy = cached_pos
            x1 = max(0, cx - 60)
            y1 = max(0, cy - 60)
            x2 = min(fw, cx + tw + 60)
            y2 = min(fh, cy + th + 60)
            if (x2 - x1) >= tw and (y2 - y1) >= th:
                roi = gray_frame[y1:y2, x1:x2]
                res = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val >= threshold:
                    return (x1 + max_loc[0], y1 + max_loc[1], tw, th)

        # Full frame scan
        res = cv2.matchTemplate(gray_frame, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val >= threshold:
            return (max_loc[0], max_loc[1], tw, th)

        return None

    def is_you_active(self, gray_frame):
        """Check if 'YOU' indicator is present on screen."""
        if self.template_you is None:
            return True

        match = self.match_template(gray_frame, self.template_you, threshold=0.72, cached_pos=self.last_you_loc)
        if match:
            self.last_you_loc = (match[0], match[1])
            return True
        else:
            self.last_you_loc = None
            return False

    def find_new_game_button(self, gray_frame):
        """Detect New Game button position using templates."""
        for tpl in [self.template_new_game, self.template_new_game2]:
            if tpl is None:
                continue
            match = self.match_template(gray_frame, tpl, threshold=0.55)
            if match:
                x, y, w, h = match
                return (x + w // 2, y + h // 2)
        return None

    def detect_squares(self, frame):
        """Detect square tiles on screen via Canny edge detection."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blur, 50, 150)

        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        squares = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 1500:
                continue

            approx = cv2.approxPolyDP(cnt, 0.04 * cv2.arcLength(cnt, True), True)
            if 4 <= len(approx) <= 8:
                x, y, w, h = cv2.boundingRect(approx)
                ratio = w / float(h) if h > 0 else 0
                if 0.78 <= ratio <= 1.25:
                    squares.append((x, y, w, h))

        return squares

    def cluster_and_deduplicate_squares(self, squares, min_dist=20):
        """
        Groups squares and eliminates duplicate centers caused by inner/outer
        contour boundaries.
        """
        if not squares:
            return []

        raw_centers = np.array([[x + w // 2, y + h // 2] for (x, y, w, h) in squares])

        # DBSCAN clustering to filter out noise
        try:
            clustering = DBSCAN(eps=90, min_samples=2).fit(raw_centers)
            labels = clustering.labels_
        except Exception:
            return []

        clustered = []
        for label in set(labels):
            if label == -1:
                continue
            clustered.extend(raw_centers[labels == label])

        if not clustered:
            return []

        # Spatial deduplication: collapse centers within min_dist
        deduped = []
        for pt in clustered:
            is_dup = False
            for d in deduped:
                if np.hypot(pt[0] - d[0], pt[1] - d[1]) < min_dist:
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(pt)

        return deduped

    def detect_active_cells(self, frame, centers):
        """Sample centers in HSV color space to find active Cyan/Blue tiles."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, w, _ = hsv.shape
        active = []

        for (cx, cy) in centers:
            x1, x2 = max(cx - 8, 0), min(cx + 8, w)
            y1, y2 = max(cy - 8, 0), min(cy + 8, h)

            sample = hsv[y1:y2, x1:x2]
            if sample.size == 0:
                continue

            mask = cv2.inRange(sample, LOWER_CYAN, UPPER_CYAN)
            ratio = np.count_nonzero(mask) / float(mask.size)

            if ratio > 0.25:
                active.append((cx, cy))

        return active

    def run(self):
        print("=" * 60)
        print(f"Visual Memory Bot Started - Mode: [{self.profile['label']}]")
        print("Press Ctrl + C in this terminal to stop at any time.")
        print("=" * 60)

        with mss.mss() as sct:
            # Select target monitor safely
            if len(sct.monitors) > self.monitor_index:
                monitor = sct.monitors[self.monitor_index]
            else:
                monitor = sct.monitors[0]

            mon_left = monitor["left"]
            mon_top = monitor["top"]

            while True:
                current_time = time.time()

                # Enforce post-click cooldown
                if current_time < self.click_cooldown_until:
                    time.sleep(0.002)
                    continue

                # Capture frame using mss
                screenshot = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                match_active = self.is_you_active(gray_frame)

                # =====================================================
                # 1. MATCH ACTIVE -> SOLVE PUZZLE
                # =====================================================
                if match_active:
                    squares = self.detect_squares(frame)
                    centers = self.cluster_and_deduplicate_squares(squares)
                    active_cells = self.detect_active_cells(frame, centers)

                    if self.state == STATE_WAITING:
                        if active_cells:
                            self.stored_clicks = active_cells.copy()
                            self.state = STATE_REVEAL
                            self.last_action_time = current_time
                            print(f"[REVEAL] Detected {len(self.stored_clicks)} active tile(s)...")

                    elif self.state == STATE_REVEAL:
                        # Safety: Turn ended abruptly
                        if not self.is_you_active(gray_frame):
                            self.state = STATE_WAITING
                            self.stored_clicks = []
                            continue

                        # When active tiles turn off, reveal is complete -> proceed to click
                        if current_time - self.last_action_time > self.profile["reveal_settle_delay"]:
                            if not active_cells and self.stored_clicks:
                                self.state = STATE_CLICK
                                print(f"[CLICK] Clicking {len(self.stored_clicks)} tile(s)...")

                        # Watchdog timeout: reset if pattern doesn't clear within 3s
                        if current_time - self.last_action_time > 3.0:
                            print("[WARN] Reveal phase timeout - resetting state.")
                            self.state = STATE_WAITING
                            self.stored_clicks = []

                    elif self.state == STATE_CLICK:
                        # Pre-click safety check
                        if not self.is_you_active(gray_frame):
                            self.state = STATE_WAITING
                            self.stored_clicks = []
                            continue

                        if self.profile["pre_click_delay"] > 0:
                            time.sleep(self.profile["pre_click_delay"])

                        # Execute clicks with monitor coordinate correction
                        for (cx, cy) in self.stored_clicks:
                            if self.profile["check_you_during_clicks"]:
                                current_shot = np.array(sct.grab(monitor))
                                cur_gray = cv2.cvtColor(current_shot, cv2.COLOR_BGRA2GRAY)
                                if not self.is_you_active(cur_gray):
                                    print("[STOP] Turn ended mid-sequence.")
                                    break

                            abs_x = mon_left + cx
                            abs_y = mon_top + cy

                            if self.profile["mouse_duration"] > 0:
                                pyautogui.moveTo(abs_x, abs_y, duration=self.profile["mouse_duration"])
                                pyautogui.click()
                            else:
                                pyautogui.click(abs_x, abs_y)

                            if self.profile["inter_click_delay"] > 0:
                                time.sleep(self.profile["inter_click_delay"])

                        self.stored_clicks = []
                        self.state = STATE_WAITING
                        self.click_cooldown_until = time.time() + self.profile["cooldown_after_click"]
                        print("[DONE] Sequence completed. Waiting for next round...")

                    self.new_game_timer = None

                # =====================================================
                # 2. MATCH INACTIVE -> CHECK 'NEW GAME'
                # =====================================================
                else:
                    self.state = STATE_WAITING
                    self.stored_clicks = []

                    ng_pos = self.find_new_game_button(gray_frame)

                    if ng_pos:
                        if self.new_game_timer is None:
                            self.new_game_timer = current_time

                        if current_time - self.new_game_timer >= 1.5:
                            click_x = mon_left + ng_pos[0]
                            click_y = mon_top + ng_pos[1]
                            print(f"[NEW GAME] Detected button at ({click_x}, {click_y}). Clicking...")
                            pyautogui.click(click_x, click_y)
                            time.sleep(1.2)
                            self.new_game_timer = None
                    else:
                        self.new_game_timer = None

                time.sleep(0.002)


def main():
    parser = argparse.ArgumentParser(description="Visual Memory Bot (Human Benchmark)")
    parser.add_argument(
        "--mode",
        choices=["fastest", "fast", "balanced", "slow"],
        default=None,
        help="Speed mode (fastest, fast, balanced, slow)",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=1,
        help="Monitor index to capture (default: 1)",
    )
    args = parser.parse_args()

    mode = args.mode
    if not mode:
        print("\nSelect Speed Mode:")
        print("  1) Fast     - Recommended (High speed, reliable)")
        print("  2) Fastest  - Blitz (Sub-millisecond)")
        print("  3) Balanced - Human-like pacing")
        print("  4) Slow     - 1 click per second")
        
        choice = input("Enter option [1-4] (default: 1): ").strip()
        mapping = {"1": "fast", "2": "fastest", "3": "balanced", "4": "slow"}
        mode = mapping.get(choice, "fast")

    bot = MemoryBot(mode=mode, monitor_index=args.monitor)
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n[STOP] Bot stopped cleanly by user (Ctrl+C).")
    except Exception as e:
        print(f"\n[ERROR] An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
