import cv2
import numpy as np
import mss
import pyautogui
import time
import os
import argparse
import traceback
from sklearn.cluster import DBSCAN

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# ---------------- FIXED IMAGE PATHS ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

YOU_IMAGE = os.path.join(BASE_DIR, "you_indicator.png")
NEWGAME_IMAGE = os.path.join(BASE_DIR, "new_game2.png")
NEWGAME_FALLBACK = os.path.join(BASE_DIR, "new_game.png")

YOU_CONFIDENCE = 0.75
NEWGAME_CONFIDENCE = 0.6

NEW_GAME_X = 1093
NEW_GAME_Y = 838

# ---------------- STATES ----------------
STATE_WAITING = 0
STATE_REVEAL = 1
STATE_CLICK = 2

# Cyan range tuned for memory grid
LOWER_CYAN = np.array([70, 80, 120])
UPPER_CYAN = np.array([115, 255, 255])

# White range (Human Benchmark memory test flash)
LOWER_WHITE = np.array([0, 0, 195])
UPPER_WHITE = np.array([180, 55, 255])


# ---------------- SAFE IMAGE DETECTION ----------------
def safe_locate(image, confidence):
    if not os.path.exists(image):
        return None
    try:
        return pyautogui.locateOnScreen(image, confidence=confidence, grayscale=True)
    except Exception:
        return None


# ---------------- GRID DETECTION ----------------
def detect_squares(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 50, 150)

    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    squares = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 1000:
            continue

        approx = cv2.approxPolyDP(cnt, 0.04 * cv2.arcLength(cnt, True), True)

        if 4 <= len(approx) <= 8:
            x, y, w, h = cv2.boundingRect(approx)
            ratio = w / float(h)
            if 0.75 <= ratio <= 1.25:
                squares.append((x, y, w, h))

    return squares


def cluster_squares(squares):
    if not squares:
        return []

    centers = np.array([[x + w // 2, y + h // 2] for (x, y, w, h) in squares])

    # Dynamically scale eps based on detected square sizes
    avg_w = np.mean([w for (_, _, w, _) in squares]) if len(squares) > 0 else 80
    dynamic_eps = max(80, int(avg_w * 2.2))

    try:
        clustering = DBSCAN(eps=dynamic_eps, min_samples=2).fit(centers)
        labels = clustering.labels_
    except Exception:
        return []

    clustered = []
    for label in set(labels):
        if label == -1:
            continue
        clustered.extend(centers[labels == label])

    # Deduplicate centers that are too close (inner/outer contour duplicates)
    min_dist = max(15, int(avg_w * 0.35))
    deduped = []
    for pt in (clustered if len(clustered) > 0 else centers):
        if not any(np.hypot(pt[0] - d[0], pt[1] - d[1]) < min_dist for d in deduped):
            deduped.append(pt)

    return deduped


def detect_active_cells(frame, centers):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    active = []
    h, w, _ = hsv.shape

    for (cx, cy) in centers:
        # Safe bounds
        x1, x2 = max(cx - 8, 0), min(cx + 8, w)
        y1, y2 = max(cy - 8, 0), min(cy + 8, h)

        sample = hsv[y1:y2, x1:x2]
        if sample.size == 0:
            continue

        mask_cyan = cv2.inRange(sample, LOWER_CYAN, UPPER_CYAN)
        mask_white = cv2.inRange(sample, LOWER_WHITE, UPPER_WHITE)
        mask = cv2.bitwise_or(mask_cyan, mask_white)

        ratio = np.count_nonzero(mask) / float(mask.size)

        if ratio > 0.22:
            active.append((cx, cy))

    return active


# ---------------- MAIN RUNNER ----------------
def run_bot(require_turn_indicator=True, speed_mode="fast"):
    state = STATE_WAITING
    stored_clicks = []
    last_action_time = 0
    new_game_timer = None
    click_cooldown_until = 0
    last_diag_time = 0

    # Timing configurations
    if speed_mode == "fastest":
        click_delay = 0.005
        move_duration = 0.0
        post_click_cooldown = 0.15
    elif speed_mode == "slow":
        click_delay = 0.8
        move_duration = 0.2
        post_click_cooldown = 0.5
    else:  # "fast" (Original diff.py timing)
        click_delay = 0.02
        move_duration = 0.01
        post_click_cooldown = 0.25

    print("=" * 60)
    print("  MEMORY BOT RUNNING")
    print(f"  Speed: [{speed_mode.upper()}] | Turn Indicator Check: [{require_turn_indicator}]")
    print(f"  YOU_IMAGE: {os.path.exists(YOU_IMAGE)} | NEWGAME_IMAGE: {os.path.exists(NEWGAME_IMAGE)}")
    print("  Press Ctrl + C in this terminal to stop.")
    print("=" * 60 + "\n")

    with mss.mss() as sct:
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

        while True:
            current_time = time.time()

            # Prevent double-trigger after clicking
            if current_time < click_cooldown_until:
                time.sleep(0.0025)
                continue

            # Check if it's the player's turn
            if require_turn_indicator:
                match_active = safe_locate(YOU_IMAGE, YOU_CONFIDENCE)
            else:
                match_active = True

            # ---------------- ACTIVE MATCH ----------------
            if match_active:
                screenshot = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

                squares = detect_squares(frame)
                centers = cluster_squares(squares)
                active_cells = detect_active_cells(frame, centers)

                # Periodic diagnostic status in terminal
                if current_time - last_diag_time > 3.0:
                    last_diag_time = current_time
                    if len(centers) > 0:
                        print(f"[STATUS] Match Active: {len(centers)} grid squares visible. Waiting for flash...")
                    else:
                        print("[STATUS] Match Active: Waiting for grid to appear on screen...")

                if state == STATE_WAITING:
                    if active_cells:
                        stored_clicks = active_cells.copy()
                        state = STATE_REVEAL
                        last_action_time = current_time
                        print(f"[FLASH] Detected {len(stored_clicks)} lit squares! Memorizing...")

                elif state == STATE_REVEAL:
                    if require_turn_indicator and not safe_locate(YOU_IMAGE, YOU_CONFIDENCE):
                        print("[ABORT] Turn ended during reveal.")
                        state = STATE_WAITING
                        stored_clicks = []
                        continue

                    if current_time - last_action_time > 0.025:
                        if not active_cells and stored_clicks:
                            state = STATE_CLICK
                            print(f"[CLICK] Flashed squares turned off. Clicking {len(stored_clicks)} squares...")

                    if current_time - last_action_time > 3.0:
                        print("[TIMEOUT] Reveal phase timed out, resetting.")
                        state = STATE_WAITING
                        stored_clicks = []

                elif state == STATE_CLICK:
                    if require_turn_indicator and not safe_locate(YOU_IMAGE, YOU_CONFIDENCE):
                        print("[ABORT] Turn ended before clicks started.")
                        state = STATE_WAITING
                        stored_clicks = []
                        continue

                    time.sleep(0.03)

                    for (cx, cy) in stored_clicks:
                        if require_turn_indicator and not safe_locate(YOU_IMAGE, YOU_CONFIDENCE):
                            print("[ABORT] Turn ended mid-click sequence.")
                            break

                        if move_duration > 0:
                            pyautogui.moveTo(cx, cy, duration=move_duration)
                            pyautogui.click()
                        else:
                            pyautogui.click(cx, cy)

                        time.sleep(click_delay)

                    print(f"[DONE] Clicked {len(stored_clicks)} squares. Round finished!")
                    stored_clicks = []
                    state = STATE_WAITING
                    click_cooldown_until = time.time() + post_click_cooldown

                new_game_timer = None

            # ---------------- NOT ACTIVE (GAME OVER / LOBBY) ----------------
            else:
                state = STATE_WAITING
                stored_clicks = []

                # Periodic diagnostic log
                if current_time - last_diag_time > 3.0:
                    last_diag_time = current_time
                    print("[WAITING] Searching for 'YOU' turn badge or 'NEW GAME' button...")

                newgame_visible = safe_locate(NEWGAME_IMAGE, NEWGAME_CONFIDENCE) or safe_locate(NEWGAME_FALLBACK, NEWGAME_CONFIDENCE)

                if newgame_visible:
                    if new_game_timer is None:
                        new_game_timer = time.time()
                        print("[NEW GAME] Button visible. Confirming in 2s...")

                    if time.time() - new_game_timer >= 2.0:
                        print(f"[NEW GAME] Clicking New Game at ({NEW_GAME_X}, {NEW_GAME_Y})...")
                        pyautogui.click(NEW_GAME_X, NEW_GAME_Y)
                        time.sleep(1.5)
                        new_game_timer = None
                else:
                    new_game_timer = None

            time.sleep(0.0025)


def main():
    parser = argparse.ArgumentParser(description="Memory Bot (Human Benchmark & 1v1 Battle)")
    parser.add_argument(
        "--speed",
        choices=["fast", "fastest", "slow"],
        default="fast",
        help="Click speed (fast, fastest, slow - default: fast)",
    )
    parser.add_argument(
        "--no-indicator",
        action="store_true",
        help="Play continuously without checking for you_indicator.png (for single player tests)",
    )
    args = parser.parse_args()

    try:
        run_bot(
            require_turn_indicator=not args.no_indicator,
            speed_mode=args.speed,
        )
    except KeyboardInterrupt:
        print("\n[STOP] Bot stopped cleanly by user (Ctrl+C).")
    except Exception as e:
        print("\nERROR:", e)
        traceback.print_exc()
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()
