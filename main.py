"""
=============================================================================
MATIKS & VISUAL MEMORY BOT - 8-BIT RETRO PIXEL EDITION
=============================================================================
A true retro arcade pixel-art interface (authentic 8-bit bevels, tactile
button presses, CRT phosphor terminal display, and dynamic font loading).

Features:
- Authentic 8-bit beveled pixel buttons with tactile click depression
- Dynamic Press Start 2P arcade font loading
- CRT Recessed Screen with live status and telemetry (Rounds, Tiles, Time)
- Live on-the-fly 4-Speed calibration (Slow, Medium, Fast, Blitz)
- Dual Restart Support: Auto-detects and clicks both:
    1) "NEW MINDSNAP" (Red/Coral button on Aborted/Finished screens)
    2) "NEW GAME" (Green button on Defeat/Victory screens)
- Always-on-top draggable retro arcade overlay
- Headless CLI option: python main.py --cli
=============================================================================
"""

import os
import sys
import time
import ctypes
import threading
import argparse
import traceback
import numpy as np
import cv2
import mss
import pyautogui
import tkinter as tk

# Disable PyAutoGUI artificial delays for pure speed
pyautogui.FAILSAFE = True  # Move mouse to top-left corner to abort
pyautogui.PAUSE = 0.0

# ----------------- BASE PATHS & FONT REGISTRATION -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_FILE = os.path.join(BASE_DIR, "PressStart2P.ttf")

# Register 8-bit pixel font dynamically at runtime in Windows GDI
HAS_PIXEL_FONT = False
if os.path.exists(FONT_FILE) and sys.platform == "win32":
    try:
        res = ctypes.windll.gdi32.AddFontResourceExW(FONT_FILE, 0x10, 0)
        HAS_PIXEL_FONT = (res > 0)
    except Exception:
        HAS_PIXEL_FONT = False

PIXEL_FONT_NAME = "Press Start 2P" if HAS_PIXEL_FONT else "Consolas"

# ----------------- COLOR CONSTANTS (HSV) -----------------
# 1. Lit Tiles (Cyan & White)
LOWER_CYAN = np.array([75, 50, 120])
UPPER_CYAN = np.array([105, 255, 255])

LOWER_WHITE = np.array([0, 0, 200])
UPPER_WHITE = np.array([180, 45, 255])

# 2. Green "NEW GAME" button border
LOWER_GREEN = np.array([35, 60, 80])
UPPER_GREEN = np.array([85, 255, 255])

# 3. Red / Coral "NEW MINDSNAP" button
LOWER_RED1 = np.array([0, 90, 110])
UPPER_RED1 = np.array([12, 255, 255])
LOWER_RED2 = np.array([170, 90, 110])
UPPER_RED2 = np.array([180, 255, 255])

# ----------------- 4 SPEED CONFIGS -----------------
SPEED_PROFILES = {
    "slow": {
        "name": "Slow",
        "tag": "1: SLOW",
        "click_delay": 0.120,
        "pre_delay": 0.10,
        "desc": "~120ms/click (relaxed & human)",
    },
    "medium": {
        "name": "Medium",
        "tag": "2: MED",
        "click_delay": 0.050,
        "pre_delay": 0.04,
        "desc": "~50ms/click (fast human pace)",
    },
    "fast": {
        "name": "Fast",
        "tag": "3: FAST",
        "click_delay": 0.016,
        "pre_delay": 0.02,
        "desc": "~16ms/click (competitive win)",
    },
    "extra fast": {
        "name": "Extra Fast",
        "tag": "4: BLITZ",
        "click_delay": 0.005,
        "pre_delay": 0.008,
        "desc": "~5ms/click (instant godmode)",
    },
}

SPEED_ALIASES = {
    "1": "slow",
    "slow": "slow",
    "2": "medium",
    "medium": "medium",
    "3": "fast",
    "fast": "fast",
    "4": "extra fast",
    "extra fast": "extra fast",
    "extrafast": "extra fast",
    "extra-fast": "extra fast",
    "blitz": "extra fast",
}


# =============================================================================
# BOT CORE ENGINE
# =============================================================================
class BotEngine:
    def __init__(self, speed_key="fast", monitor_index=1, on_status=None, on_round_win=None, on_failsafe=None):
        self.speed_key = speed_key
        self.speed_cfg = SPEED_PROFILES[self.speed_key]
        self.monitor_index = monitor_index
        self.auto_new_game = True

        self.on_status = on_status
        self.on_round_win = on_round_win
        self.on_failsafe = on_failsafe

        self.is_running = False
        self.thread = None

        self.stored_clicks = {}
        self.state = 0  # 0: WAITING, 1: REVEAL, 2: CLICK
        self.last_action_time = 0.0
        self.click_cooldown_until = 0.0
        self.new_game_timer = None
        self.detected_button_type = None
        self.total_rounds = 0
        self.total_tiles = 0

    def set_speed(self, speed_key):
        clean = SPEED_ALIASES.get(str(speed_key).lower().strip(), "fast")
        self.speed_key = clean
        self.speed_cfg = SPEED_PROFILES[clean]

    def set_auto_new_game(self, enabled):
        self.auto_new_game = enabled

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.state = 0
        self.stored_clicks = {}
        self.new_game_timer = None
        self.detected_button_type = None
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        self.state = 0
        self.stored_clicks = {}
        self.new_game_timer = None
        self.detected_button_type = None
        if self.on_status:
            self.on_status("STANDBY", "#ffe600")

    def _loop(self):
        if self.on_status:
            self.on_status("SEARCHING", "#00ffcc")

        try:
            with mss.mss() as sct:
                monitor = sct.monitors[self.monitor_index] if len(sct.monitors) > self.monitor_index else sct.monitors[0]
                mon_left = monitor["left"]
                mon_top = monitor["top"]

                while self.is_running:
                    now = time.time()

                    if now < self.click_cooldown_until:
                        time.sleep(0.002)
                        continue

                    shot = np.array(sct.grab(monitor))
                    frame = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
                    active_tiles = self._detect_active_tiles(frame)

                    # --- STATE MACHINE ---
                    if self.state == 0:  # WAITING
                        if len(active_tiles) > 0:
                            self.stored_clicks = {pt: now for pt in active_tiles}
                            self.state = 1
                            self.last_action_time = now
                            if self.on_status:
                                self.on_status(f"MEMORIZING [{len(self.stored_clicks)}]", "#ff007f")

                    elif self.state == 1:  # REVEAL
                        if len(active_tiles) > 0:
                            for pt in active_tiles:
                                self.stored_clicks[pt] = now
                            self.last_action_time = now
                        elif len(active_tiles) == 0 and len(self.stored_clicks) > 0:
                            if now - self.last_action_time >= 0.02:
                                self.state = 2
                                if self.on_status:
                                    self.on_status(f"BLITZING [{len(self.stored_clicks)}]", "#39ff14")

                        if now - self.last_action_time > 4.0:
                            self.state = 0
                            self.stored_clicks = {}
                            if self.on_status:
                                self.on_status("SEARCHING", "#00ffcc")

                    elif self.state == 2:  # CLICK
                        points = list(self.stored_clicks.keys())
                        n_tiles = len(points)
                        self.total_rounds += 1
                        self.total_tiles += n_tiles

                        if self.speed_cfg["pre_delay"] > 0:
                            time.sleep(self.speed_cfg["pre_delay"])

                        t0 = time.perf_counter()
                        for cx, cy in points:
                            if not self.is_running:
                                break
                            pyautogui.click(mon_left + cx, mon_top + cy)
                            if self.speed_cfg["click_delay"] > 0:
                                time.sleep(self.speed_cfg["click_delay"])
                        dur_ms = (time.perf_counter() - t0) * 1000.0

                        if self.on_round_win:
                            self.on_round_win(self.total_rounds, self.total_tiles, dur_ms)

                        self.stored_clicks = {}
                        self.state = 0
                        self.click_cooldown_until = time.time() + 0.30
                        if self.on_status:
                            self.on_status(f"WON #{self.total_rounds:02d} ({dur_ms:.0f}ms)", "#39ff14")

                    # --- AUTO-RESTART: "NEW MINDSNAP" / "NEW GAME" DETECTION ---
                    if self.auto_new_game and self.state == 0 and len(active_tiles) == 0:
                        restart_btn = self._detect_restart_button(frame)
                        if restart_btn:
                            btn_x, btn_y, btn_name = restart_btn
                            if self.new_game_timer is None:
                                self.new_game_timer = now
                                self.detected_button_type = btn_name
                                if self.on_status:
                                    self.on_status(f"{btn_name} IN 1.2s", "#ffe600")

                            if now - self.new_game_timer >= 1.2:
                                gx, gy = mon_left + btn_x, mon_top + btn_y
                                pyautogui.click(gx, gy)
                                time.sleep(1.5)
                                self.new_game_timer = None
                                self.detected_button_type = None
                                if self.on_status:
                                    self.on_status("SEARCHING", "#00ffcc")
                        else:
                            self.new_game_timer = None
                            self.detected_button_type = None

                    time.sleep(0.003)

        except pyautogui.FailSafeException:
            # Clean emergency abort when mouse slides to corner
            self.is_running = False
            self.state = 0
            self.stored_clicks = {}
            self.new_game_timer = None
            self.detected_button_type = None
            if self.on_status:
                self.on_status("ABORTED (CORNER)", "#ffaa00")
            if self.on_failsafe:
                self.on_failsafe()
        except Exception as e:
            self.is_running = False
            self.state = 0
            self.stored_clicks = {}
            self.new_game_timer = None
            if self.on_status:
                self.on_status("ERROR", "#ff0055")
            print(f"[BOT LOOP ERROR]: {e}")
            traceback.print_exc()
        finally:
            self.is_running = False

    def _detect_active_tiles(self, frame):
        h, w = frame.shape[:2]
        y1, y2 = int(h * 0.18), int(h * 0.95)
        x1, x2 = int(w * 0.20), int(w * 0.80)
        roi = frame[y1:y2, x1:x2]

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask_c = cv2.inRange(hsv, LOWER_CYAN, UPPER_CYAN)
        mask_w = cv2.inRange(hsv, LOWER_WHITE, UPPER_WHITE)
        mask = cv2.bitwise_or(mask_c, mask_w)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        tiles = []
        for cnt in contours:
            if cv2.contourArea(cnt) > 600:
                bx, by, bw, bh = cv2.boundingRect(cnt)
                aspect = bw / float(bh) if bh > 0 else 0
                if 0.70 <= aspect <= 1.40:
                    tiles.append((x1 + bx + bw // 2, y1 + by + bh // 2))
        return tiles

    def _detect_restart_button(self, frame):
        """
        Detects both:
        1. Red / Coral '▶ NEW MINDSNAP' button (on Aborted/Result screen)
        2. Green 'NEW GAME' button (on Defeat/Victory summary screen)
        Returns (center_x, center_y, button_label) or None.
        """
        h, w = frame.shape[:2]
        # Restart buttons always reside in the lower half of the screen
        roi = frame[int(h * 0.40):, :]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Mask 1: Green button
        mask_green = cv2.inRange(hsv, LOWER_GREEN, UPPER_GREEN)

        # Mask 2: Red/Coral button (NEW MINDSNAP)
        m1 = cv2.inRange(hsv, LOWER_RED1, UPPER_RED1)
        m2 = cv2.inRange(hsv, LOWER_RED2, UPPER_RED2)
        mask_red = cv2.bitwise_or(m1, m2)

        combined_mask = cv2.bitwise_or(mask_green, mask_red)
        contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 350:  # Valid button size
                bx, by, bw, bh = cv2.boundingRect(cnt)
                ratio = bw / float(bh) if bh > 0 else 0
                # Must be a wide rectangular button
                if 2.0 <= ratio <= 9.0 and bw > 60:
                    cx = bx + bw // 2
                    cy = int(h * 0.40) + by + bh // 2

                    # Identify button type based on color dominance
                    red_pixels = np.count_nonzero(mask_red[by:by+bh, bx:bx+bw])
                    btn_type = "NEW MINDSNAP" if red_pixels > (area * 0.35) else "NEW GAME"

                    candidates.append((cx, cy, area, btn_type))

        if candidates:
            # Pick largest candidate by area
            candidates.sort(key=lambda c: c[2], reverse=True)
            best = candidates[0]
            return (best[0], best[1], best[3])

        return None


# =============================================================================
# AUTHENTIC 8-BIT RETRO PIXEL CANVAS BUTTON
# =============================================================================
class PixelButton(tk.Canvas):
    def __init__(
        self, parent, text, command=None, width=150, height=36,
        bg_color="#181c2b", fg_color="#ffffff",
        border_light="#3e4868", border_dark="#080910",
        highlight_color=None, font_size=8, **kwargs
    ):
        super().__init__(
            parent, width=width, height=height, bg=parent["bg"],
            highlightthickness=0, bd=0, cursor="hand2", **kwargs
        )
        self.text = text
        self.command = command
        self.w = width
        self.h = height
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.border_light = border_light
        self.border_dark = border_dark
        self.highlight_color = highlight_color
        self.font_size = font_size

        self.is_pressed = False
        self.is_active = False

        self.draw()
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def set_colors(self, bg_color, fg_color, border_light, border_dark):
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.border_light = border_light
        self.border_dark = border_dark
        self.draw()

    def set_active(self, active):
        self.is_active = active
        self.draw()

    def set_text(self, text):
        self.text = text
        self.draw()

    def draw(self):
        self.delete("all")
        offset = 2 if self.is_pressed else 0

        # Outer Stepped 8-Bit Pixel Silhouette
        self.create_rectangle(2, 0, self.w - 2, self.h, fill="#000000", width=0)
        self.create_rectangle(0, 2, self.w, self.h - 2, fill="#000000", width=0)

        border_top = self.highlight_color if self.is_active and self.highlight_color else (
            self.border_dark if self.is_pressed else self.border_light
        )
        border_bot = self.highlight_color if self.is_active and self.highlight_color else (
            self.border_light if self.is_pressed else self.border_dark
        )

        face_bg = self.bg_color
        self.create_rectangle(2, 2, self.w - 2, self.h - 2, fill=face_bg, width=0)

        # 3D Pixel Bevel Lines
        self.create_line(2, 2, self.w - 2, 2, fill=border_top, width=2)
        self.create_line(2, 2, 2, self.h - 2, fill=border_top, width=2)
        self.create_line(self.w - 3, 3, self.w - 3, self.h - 2, fill=border_bot, width=2)
        self.create_line(3, self.h - 3, self.w - 2, self.h - 3, fill=border_bot, width=2)

        font_spec = (PIXEL_FONT_NAME, self.font_size, "bold") if not HAS_PIXEL_FONT else (PIXEL_FONT_NAME, self.font_size)
        self.create_text(
            self.w // 2 + offset, self.h // 2 + offset,
            text=self.text, fill=self.fg_color, font=font_spec
        )

    def _on_press(self, event):
        self.is_pressed = True
        self.draw()

    def _on_release(self, event):
        self.is_pressed = False
        self.draw()
        if self.command:
            self.command()

    def _on_enter(self, event):
        if not self.is_active:
            self.draw()

    def _on_leave(self, event):
        self.is_pressed = False
        self.draw()


# =============================================================================
# RETRO PIXEL UI (Authentic 8-Bit Arcade Cyber Aesthetic)
# =============================================================================
class PixelRetroUI:
    BG_MAIN = "#0a0b12"
    BG_PANEL = "#121524"
    BG_CRT = "#050d0a"
    C_CYAN = "#00ffcc"
    C_GREEN = "#00ff66"
    C_PINK = "#ff0055"
    C_YELLOW = "#ffe600"
    C_WHITE = "#ffffff"
    C_MUTED = "#4e5773"

    def __init__(self, bot):
        self.bot = bot
        self.root = tk.Tk()
        self.root.title("MATIKS // BOT_OS")
        self.root.geometry("400x530")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG_MAIN)
        self.root.attributes("-topmost", True)

        self._drag_x = 0
        self._drag_y = 0

        self.bot.on_status = self.update_status_threadsafe
        self.bot.on_round_win = self.update_stats_threadsafe
        self.bot.on_failsafe = self.handle_failsafe_threadsafe

        self.speed_buttons = {}
        self._build_ui()

    def _build_ui(self):
        # 1. RETRO TITLE BAR
        title_canvas = tk.Canvas(self.root, width=380, height=36, bg=self.BG_MAIN, highlightthickness=0, bd=0)
        title_canvas.pack(fill=tk.X, padx=10, pady=(10, 6))

        title_canvas.create_rectangle(2, 0, 378, 36, fill="#000", width=0)
        title_canvas.create_rectangle(0, 2, 380, 34, fill="#000", width=0)
        title_canvas.create_rectangle(2, 2, 378, 34, fill=self.BG_PANEL, width=0)
        title_canvas.create_line(2, 2, 378, 2, fill=self.C_CYAN, width=2)
        title_canvas.create_line(2, 2, 2, 34, fill=self.C_CYAN, width=2)

        font_hdr = (PIXEL_FONT_NAME, 9) if HAS_PIXEL_FONT else (PIXEL_FONT_NAME, 10, "bold")
        title_canvas.create_text(190, 18, text="■■ MATIKS // BOT_OS ■■", fill=self.C_CYAN, font=font_hdr)

        title_canvas.bind("<ButtonPress-1>", self._start_drag)
        title_canvas.bind("<B1-Motion>", self._on_drag)

        # 2. RECESSED CRT SCREEN
        crt_canvas = tk.Canvas(self.root, width=380, height=130, bg=self.BG_MAIN, highlightthickness=0, bd=0)
        crt_canvas.pack(fill=tk.X, padx=10, pady=4)

        crt_canvas.create_rectangle(2, 0, 378, 130, fill="#000000", width=0)
        crt_canvas.create_rectangle(0, 2, 380, 128, fill="#000000", width=0)
        crt_canvas.create_rectangle(2, 2, 378, 128, fill=self.BG_CRT, width=0)
        crt_canvas.create_line(2, 2, 378, 2, fill="#020504", width=2)
        crt_canvas.create_line(2, 2, 2, 128, fill="#020504", width=2)
        crt_canvas.create_line(377, 3, 377, 128, fill="#182c22", width=2)
        crt_canvas.create_line(3, 127, 378, 127, fill="#182c22", width=2)

        for y_line in range(6, 126, 4):
            crt_canvas.create_line(4, y_line, 376, y_line, fill="#030806", width=1)

        font_sys = (PIXEL_FONT_NAME, 7) if HAS_PIXEL_FONT else (PIXEL_FONT_NAME, 8, "bold")
        font_status = (PIXEL_FONT_NAME, 10) if HAS_PIXEL_FONT else (PIXEL_FONT_NAME, 12, "bold")
        font_stats = (PIXEL_FONT_NAME, 8) if HAS_PIXEL_FONT else (PIXEL_FONT_NAME, 9, "bold")

        crt_canvas.create_text(16, 20, text=">> SYS_READY // TELEMETRY", fill=self.C_MUTED, font=font_sys, anchor="w")

        self.crt_status_id = crt_canvas.create_text(
            16, 52, text="● [ STANDBY ]", fill=self.C_YELLOW, font=font_status, anchor="w"
        )
        self.crt_rounds_id = crt_canvas.create_text(
            16, 88, text="ROUNDS: 000    TILES: 000", fill=self.C_WHITE, font=font_stats, anchor="w"
        )
        self.crt_speed_id = crt_canvas.create_text(
            16, 108, text="LAST TIME: --.- MS", fill=self.C_GREEN, font=font_stats, anchor="w"
        )
        self.crt_canvas = crt_canvas

        # 3. SPEED CALIBRATION BOX
        cal_box = tk.Frame(self.root, bg=self.BG_MAIN)
        cal_box.pack(fill=tk.X, padx=10, pady=6)

        font_sub = (PIXEL_FONT_NAME, 7) if HAS_PIXEL_FONT else (PIXEL_FONT_NAME, 8, "bold")
        tk.Label(cal_box, text=">> CALIBRATE SPEED <<", font=font_sub, fg=self.C_CYAN, bg=self.BG_MAIN).pack(anchor="w", padx=2, pady=(0, 4))

        btn_grid = tk.Frame(cal_box, bg=self.BG_MAIN)
        btn_grid.pack(fill=tk.X)

        for idx, (skey, scfg) in enumerate(SPEED_PROFILES.items()):
            row = idx // 2
            col = idx % 2
            btn = PixelButton(
                btn_grid,
                text=scfg["tag"],
                width=182,
                height=36,
                bg_color="#141828",
                fg_color=self.C_WHITE,
                border_light="#2e385c",
                border_dark="#080912",
                highlight_color=self.C_CYAN,
                font_size=7 if HAS_PIXEL_FONT else 8,
                command=lambda k=skey: self.select_speed(k),
            )
            btn.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")
            btn_grid.columnconfigure(col, weight=1)
            self.speed_buttons[skey] = btn

        self.lbl_speed_desc = tk.Label(
            cal_box,
            text=f"> {SPEED_PROFILES[self.bot.speed_key]['desc']}",
            font=font_sub,
            fg=self.C_YELLOW,
            bg=self.BG_MAIN,
            pady=4,
        )
        self.lbl_speed_desc.pack(anchor="w", padx=2)

        self._refresh_speed_buttons()

        # 4. AUTO-RESTART TOGGLE
        toggle_box = tk.Frame(self.root, bg=self.BG_MAIN)
        toggle_box.pack(fill=tk.X, padx=10, pady=(0, 6))

        self.btn_toggle_ng = PixelButton(
            toggle_box,
            text="[■] AUTO-RESTART: ON",
            width=375,
            height=30,
            bg_color="#0e1b18",
            fg_color=self.C_GREEN,
            border_light="#1b4d3e",
            border_dark="#050a08",
            font_size=7 if HAS_PIXEL_FONT else 8,
            command=self.toggle_new_game,
        )
        self.btn_toggle_ng.pack(fill=tk.X)

        # 5. MASTER ENGAGE / HALT BUTTON
        action_box = tk.Frame(self.root, bg=self.BG_MAIN)
        action_box.pack(fill=tk.X, padx=10, pady=(4, 6))

        self.btn_master = PixelButton(
            action_box,
            text="▶ ENGAGE BOT",
            width=375,
            height=54,
            bg_color="#00a843",
            fg_color="#000000",
            border_light=self.C_GREEN,
            border_dark="#004d1f",
            font_size=10 if HAS_PIXEL_FONT else 11,
            command=self.toggle_bot,
        )
        self.btn_master.pack(fill=tk.X)

        # 6. Bottom Failsafe
        tk.Label(
            self.root,
            text="EMERGENCY ABORT: SLIDE MOUSE TO CORNER",
            font=("Consolas", 7, "bold"),
            fg=self.C_MUTED,
            bg=self.BG_MAIN,
            pady=4,
        ).pack(side=tk.BOTTOM)

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        deltax = event.x - self._drag_x
        deltay = event.y - self._drag_y
        new_x = self.root.winfo_x() + deltax
        new_y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{new_x}+{new_y}")

    def select_speed(self, skey):
        self.bot.set_speed(skey)
        self.lbl_speed_desc.configure(text=f"> {SPEED_PROFILES[skey]['desc']}")
        self._refresh_speed_buttons()

    def _refresh_speed_buttons(self):
        for skey, btn in self.speed_buttons.items():
            if skey == self.bot.speed_key:
                btn.set_colors(
                    bg_color="#003830",
                    fg_color=self.C_CYAN,
                    border_light=self.C_CYAN,
                    border_dark="#00241f",
                )
                btn.set_active(True)
            else:
                btn.set_colors(
                    bg_color="#141828",
                    fg_color="#a8b2d1",
                    border_light="#2e385c",
                    border_dark="#080912",
                )
                btn.set_active(False)

    def toggle_new_game(self):
        new_val = not self.bot.auto_new_game
        self.bot.set_auto_new_game(new_val)
        if new_val:
            self.btn_toggle_ng.set_text("[■] AUTO-RESTART: ON")
            self.btn_toggle_ng.set_colors("#0e1b18", self.C_GREEN, "#1b4d3e", "#050a08")
        else:
            self.btn_toggle_ng.set_text("[ ] AUTO-RESTART: OFF")
            self.btn_toggle_ng.set_colors("#181820", self.C_MUTED, "#2e2e38", "#08080c")

    def toggle_bot(self):
        if not self.bot.is_running:
            self.bot.start()
            self.btn_master.set_text("■ HALT BOT")
            self.btn_master.set_colors(
                bg_color="#c20038",
                fg_color=self.C_WHITE,
                border_light=self.C_PINK,
                border_dark="#500017",
            )
        else:
            self.bot.stop()
            self.btn_master.set_text("▶ ENGAGE BOT")
            self.btn_master.set_colors(
                bg_color="#00a843",
                fg_color="#000000",
                border_light=self.C_GREEN,
                border_dark="#004d1f",
            )

    def update_status_threadsafe(self, text, color):
        def _update():
            self.crt_canvas.itemconfig(self.crt_status_id, text=f"● [ {text} ]", fill=color)
        self.root.after(0, _update)

    def update_stats_threadsafe(self, rounds, tiles, last_ms):
        def _update():
            self.crt_canvas.itemconfig(self.crt_rounds_id, text=f"ROUNDS: {rounds:03d}    TILES: {tiles:03d}")
            self.crt_canvas.itemconfig(self.crt_speed_id, text=f"LAST TIME: {last_ms:.1f} MS")
        self.root.after(0, _update)

    def handle_failsafe_threadsafe(self):
        def _update():
            self.btn_master.set_text("▶ ENGAGE BOT")
            self.btn_master.set_colors(
                bg_color="#00a843",
                fg_color="#000000",
                border_light=self.C_GREEN,
                border_dark="#004d1f",
            )
        self.root.after(0, _update)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.bot.stop()


# =============================================================================
# CLI HEADLESS MODE
# =============================================================================
def run_cli_mode(speed, monitor):
    bot = BotEngine(speed_key=speed, monitor_index=monitor)
    print("=" * 65)
    print("  MATIKS MEMORY BOT [CLI HEADLESS MODE]")
    print(f"  Speed: [{bot.speed_cfg['tag']}] - {bot.speed_cfg['desc']}")
    print("  Controls: Move mouse to top-left corner or press Ctrl+C to stop.")
    print("=" * 65)

    def cli_status(text, color):
        print(f"[*] STATUS: {text}")

    def cli_win(rounds, tiles, ms):
        print(f"[+] ROUND {rounds:02d} WON! ({tiles} tiles in {ms:.1f}ms)")

    bot.on_status = cli_status
    bot.on_round_win = cli_win
    bot.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP] Bot stopped cleanly by user.")
    finally:
        bot.stop()


# =============================================================================
# ENTRY POINT
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Matiks Memory Bot (Retro Pixel Edition)")
    parser.add_argument("--cli", action="store_true", help="Run in headless terminal mode without UI")
    parser.add_argument("--speed", type=str, default="fast", help="Speed: slow, medium, fast, extra fast")
    parser.add_argument("--monitor", type=int, default=1, help="Monitor index (default: 1)")
    args = parser.parse_args()

    clean_speed = SPEED_ALIASES.get(str(args.speed).lower().strip(), "fast")

    if args.cli:
        run_cli_mode(speed=clean_speed, monitor=args.monitor)
    else:
        bot = BotEngine(speed_key=clean_speed, monitor_index=args.monitor)
        app = PixelRetroUI(bot)
        app.run()


if __name__ == "__main__":
    main()
