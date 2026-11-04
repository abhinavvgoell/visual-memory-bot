"""
=============================================================================
VISUAL MEMORY BOT - MAIN (Production Edition)
=============================================================================
High-performance computer vision bot for Visual Memory games 
(Human Benchmark, Memory Matrix, Lumosity, 1v1 Memory Battles).

Key Architecture & Fixes:
1. Multi-Resolution & DPI Adaptive: Works seamlessly on 1080p, 1440p, 4K.
   Dynamically scales grid clustering (DBSCAN) based on measured tile sizes.
2. Multi-Color Detection: Detects both Pure White flash (Human Benchmark) 
   and Cyan/Blue flash (Memory Battle / Lumosity).
3. Robust Turn Detection: Multi-scale template matching with fallback so the 
   bot never locks up if turn indicators change resolution or ELO.
4. Fast MSS Frame Capture + OpenCV In-Memory Processing (~2ms loop).
5. Accurate Monitor Offset Coordinates: Accurately clicks targets across 
   multi-monitor setups.
6. Zero-Delay Startup: Begins scanning immediately without blocking inputs.
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

# Color thresholds in HSV
# 1) Cyan / Blue flash
LOWER_CYAN = np.array([65, 50, 70])
UPPER_CYAN = np.array([135, 255, 255])
# 2) White flash (Human Benchmark style)
LOWER_WHITE = np.array([0, 0, 195])
UPPER_WHITE = np.array([180, 55, 255])

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
    },
    "fast": {
        "label": "Fast (High speed, reliable - Recommended)",
        "reveal_settle_delay": 0.025,
        "pre_click_delay": 0.02,
        "inter_click_delay": 0.018,
        "mouse_duration": 0.005,
        "cooldown_after_click": 0.25,
    },
    "balanced": {
        "label": "Balanced (Human-like pacing)",
        "reveal_settle_delay": 0.06,
        "pre_click_delay": 0.04,
        "inter_click_delay": 0.06,
        "mouse_duration": 0.03,
        "cooldown_after_click": 0.35,
    },
    "slow": {
        "label": "Slow (Safe mode - ~1 click per second)",
        "reveal_settle_delay": 0.2,
        "pre_click_delay": 0.3,
        "inter_click_delay": 0.8,
        "mouse_duration": 0.2,
        "cooldown_after_click": 0.5,
    },
}


class MemoryBot:
    def __init__(self, mode="fast", monitor_index=1, strict_turn=False):
        self.profile = SPEED_PROFILES.get(mode, SPEED_PROFILES["fast"])
        self.mode_name = mode
        self.monitor_index = monitor_index
        self.strict_turn = strict_turn

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
        self.last_you_loc = None
        self.last_grid_log_time = 0.0

    def _load_template(self, path):
        if not os.path.exists(path):
            return None
        return cv2.imread(path, cv2.IMREAD_GRAYSCALE)

    def match_template(self, gray_frame, template, threshold=0.60):
        """
        In-memory template matching with multi-scale support 
        (handles 1080p, 1440p, 4K scale differences).
        """
        if template is None or gray_frame is None:
            return None

        th, tw = template.shape[:2]
        fh, fw = gray_frame.shape[:2]

        if fh < th or fw < tw:
            return None

        # Test at 1.0x, 1.25x, 1.33x (common 1440p scale), and 0.8x
        scales = [1.0, 1.33, 1.25, 0.8] if fw > 1920 else [1.0, 0.8, 1.25]
        for scale in scales:
            if scale == 1.0:
                scaled_tpl = template
            else:
                new_w = int(tw * scale)
                new_h = int(th * scale)
                if new_w >= fw or new_h >= fh or new_w <= 10 or new_h <= 10:
                    continue
                scaled_tpl = cv2.resize(template, (new_w, new_h))

            stw, sth = scaled_tpl.shape[1], scaled_tpl.shape[0]
            res = cv2.matchTemplate(gray_frame, scaled_tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val >= threshold:
                return (max_loc[0], max_loc[1], stw, sth)

        return None

    def is_you_active(self, gray_frame):
        """
        Check if 'YOU' indicator is present on screen.
        If strict_turn is False and indicator is not found on screen,
        allows the bot to play if memory tiles are present.
        """
        if self.template_you is None or not self.strict_turn:
            return True

        match = self.match_template(gray_frame, self.template_you, threshold=0.55)
        return match is not None

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
        """
        Adaptive square detection that scales across all screen resolutions.
        Finds square contours and calculates median tile size.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blur, 40, 140)

        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        squares = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Area must be large enough to be a game tile (> 800px on 1080p/1440p)
            if area < 800:
                continue

            approx = cv2.approxPolyDP(cnt, 0.04 * cv2.arcLength(cnt, True), True)
            if 4 <= len(approx) <= 8:
                x, y, w, h = cv2.boundingRect(approx)
                if h == 0:
                    continue
                ratio = w / float(h)
                # Must be reasonably square
                if 0.75 <= ratio <= 1.30:
                    squares.append((x, y, w, h))

        return squares

    def cluster_and_deduplicate_squares(self, squares):
        """
        Dynamically groups squares using measured tile size to compute eps.
        Works across 1080p, 1440p, 4K resolutions without hardcoded limits.
        """
        if len(squares) < 3:
            return [], 0

        widths = [w for (_, _, w, _) in squares]
        median_size = int(np.median(widths))

        raw_centers = np.array([[x + w // 2, y + h // 2] for (x, y, w, h) in squares])

        # Dynamic eps based on tile size (adjacent tiles are ~1.2x to 1.8x tile size apart)
        dynamic_eps = max(180, int(median_size * 2.2))

        try:
            clustering = DBSCAN(eps=dynamic_eps, min_samples=2).fit(raw_centers)
            labels = clustering.labels_
        except Exception:
            return [], median_size

        clustered = []
        for label in set(labels):
            if label == -1:
                continue
            clustered.extend(raw_centers[labels == label])

        if not clustered:
            # Fallback: if all were -1 due to loose spacing, use raw_centers directly
            clustered = list(raw_centers)

        # Spatial deduplication: collapse centers closer than 40% of tile size
        min_dist = max(18, int(median_size * 0.4))
        deduped = []
        for pt in clustered:
            is_dup = False
            for d in deduped:
                if np.hypot(pt[0] - d[0], pt[1] - d[1]) < min_dist:
                    is_dup = True
                    break
            if not is_dup:
                deduped.append(pt)

        return deduped, median_size

    def detect_active_cells(self, frame, centers, tile_size):
        """
        Sample centers in HSV color space to find active tiles.
        Supports BOTH Cyan/Blue flash and Pure White flash (Human Benchmark).
        """
        if not centers:
            return []

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, w, _ = hsv.shape
        active = []

        # Adaptive sample radius (half of tile's inner area)
        sample_radius = max(8, int(tile_size * 0.22)) if tile_size > 0 else 10

        for (cx, cy) in centers:
            x1, x2 = max(cx - sample_radius, 0), min(cx + sample_radius, w)
            y1, y2 = max(cy - sample_radius, 0), min(cy + sample_radius, h)

            sample = hsv[y1:y2, x1:x2]
            if sample.size == 0:
                continue

            # Check Cyan/Blue flash
            mask_cyan = cv2.inRange(sample, LOWER_CYAN, UPPER_CYAN)
            # Check Pure White flash
            mask_white = cv2.inRange(sample, LOWER_WHITE, UPPER_WHITE)

            combined_mask = cv2.bitwise_or(mask_cyan, mask_white)
            ratio = np.count_nonzero(combined_mask) / float(combined_mask.size)

            if ratio > 0.22:
                active.append((cx, cy))

        return active

    def run(self):
        print("=" * 65)
        print("  VISUAL MEMORY BOT - RUNNING")
        print(f"  Speed Profile: [{self.profile['label']}]")
        print("  Press Ctrl + C in this terminal to stop.")
        print("=" * 65)

        with mss.mss() as sct:
            # Select target monitor safely
            if len(sct.monitors) > self.monitor_index:
                monitor = sct.monitors[self.monitor_index]
            else:
                monitor = sct.monitors[0]

            mon_left = monitor["left"]
            mon_top = monitor["top"]
            print(f"[INIT] Captured Display: {monitor['width']}x{monitor['height']} (Offset: +{mon_left}, +{mon_top})")
            print("[STATUS] Scanning screen for memory game board...\n")

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
                # 1. SOLVE PUZZLE
                # =====================================================
                if match_active:
                    squares = self.detect_squares(frame)
                    centers, tile_size = self.cluster_and_deduplicate_squares(squares)

                    # Periodic diagnostic log if board is detected
                    if len(centers) >= 4 and current_time - self.last_grid_log_time > 4.0:
                        grid_side = int(round(len(centers) ** 0.5))
                        print(f"[BOARD] Found {len(centers)} tiles (~{grid_side}x{grid_side} grid, tile size: {tile_size}px). Ready for flash!")
                        self.last_grid_log_time = current_time

                    active_cells = self.detect_active_cells(frame, centers, tile_size)

                    if self.state == STATE_WAITING:
                        if active_cells:
                            self.stored_clicks = active_cells.copy()
                            self.state = STATE_REVEAL
                            self.last_action_time = current_time
                            print(f"[FLASH] Detected {len(self.stored_clicks)} lit tile(s)! Memorizing...")

                    elif self.state == STATE_REVEAL:
                        # When active tiles turn back off, pattern reveal has concluded -> click!
                        if current_time - self.last_action_time > self.profile["reveal_settle_delay"]:
                            if not active_cells and self.stored_clicks:
                                self.state = STATE_CLICK
                                print(f"[CLICK] Clicking sequence of {len(self.stored_clicks)} tile(s)...")

                        # Watchdog timeout: reset if pattern doesn't clear within 3.5s
                        if current_time - self.last_action_time > 3.5:
                            print("[WARN] Reveal phase timeout - resetting state.")
                            self.state = STATE_WAITING
                            self.stored_clicks = []

                    elif self.state == STATE_CLICK:
                        if self.profile["pre_click_delay"] > 0:
                            time.sleep(self.profile["pre_click_delay"])

                        # Execute clicks with monitor coordinate correction
                        for (cx, cy) in self.stored_clicks:
                            abs_x = mon_left + cx
                            abs_y = mon_top + cy

                            if self.profile["mouse_duration"] > 0:
                                pyautogui.moveTo(abs_x, abs_y, duration=self.profile["mouse_duration"])
                                pyautogui.click()
                            else:
                                pyautogui.click(abs_x, abs_y)

                            if self.profile["inter_click_delay"] > 0:
                                time.sleep(self.profile["inter_click_delay"])

                        print(f"[DONE] Clicked {len(self.stored_clicks)} tiles. Waiting for next round...")
                        self.stored_clicks = []
                        self.state = STATE_WAITING
                        self.click_cooldown_until = time.time() + self.profile["cooldown_after_click"]

                    self.new_game_timer = None

                # =====================================================
                # 2. CHECK 'NEW GAME' BUTTON
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
    parser = argparse.ArgumentParser(description="Visual Memory Bot")
    parser.add_argument(
        "--mode",
        choices=["fastest", "fast", "balanced", "slow"],
        default="fast",
        help="Speed mode (default: fast)",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=1,
        help="Monitor index to capture (default: 1)",
    )
    parser.add_argument(
        "--strict-turn",
        action="store_true",
        help="Only click when you_indicator.png is actively matched on screen",
    )
    args = parser.parse_args()

    bot = MemoryBot(
        mode=args.mode,
        monitor_index=args.monitor,
        strict_turn=args.strict_turn,
    )

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
