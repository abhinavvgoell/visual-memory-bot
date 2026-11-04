"""
=============================================================================
MATIKS & VISUAL MEMORY BOT - RETRO PIXEL EDITION (v2.4)
=============================================================================
Features:
- Pixelated, 8-bit arcade cyber HUD interface (zero AI slop, pure retro vibes)
- Live on-the-fly speed switching (Slow, Medium, Fast, Extra Fast / Blitz)
- Background daemon worker thread with thread-safe UI updates
- Master [ ENGAGE ] / [ HALT ] chunky pixel buttons
- Auto-restart toggle for automatic "NEW GAME" clicking
- Real-time telemetry: Round Counter, Tiles Cleared, Last Speed ms
- Always-on-top floating overlay so you can play without switching windows
- CLI headless fallback support: python main.py --cli
=============================================================================
"""

import os
import sys
import time
import threading
import argparse
import traceback
import numpy as np
import cv2
import mss
import pyautogui
import tkinter as tk
from tkinter import font as tkfont

# Set PyAutoGUI properties for maximum speed
pyautogui.FAILSAFE = True  # Move mouse to top-left corner to emergency abort
pyautogui.PAUSE = 0.0      # Zero artificial delay between clicks

# ----------------- COLOR MASKS (HSV) -----------------
LOWER_CYAN = np.array([75, 50, 120])
UPPER_CYAN = np.array([105, 255, 255])

LOWER_WHITE = np.array([0, 0, 200])
UPPER_WHITE = np.array([180, 45, 255])

LOWER_GREEN = np.array([35, 60, 80])
UPPER_GREEN = np.array([85, 255, 255])

# ----------------- 4 SPEED PROFILES -----------------
SPEED_PROFILES = {
    "slow": {
        "label": "1: SLOW",
        "click_delay": 0.120,
        "pre_delay": 0.10,
        "desc": "~120ms/click (relaxed & human)",
    },
    "medium": {
        "label": "2: MED",
        "click_delay": 0.050,
        "pre_delay": 0.04,
        "desc": "~50ms/click (fast human pace)",
    },
    "fast": {
        "label": "3: FAST",
        "click_delay": 0.016,
        "pre_delay": 0.02,
        "desc": "~16ms/click (competitive win)",
    },
    "extra fast": {
        "label": "4: BLITZ",
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
    def __init__(self, speed_key="fast", monitor_index=1, on_status=None, on_round_win=None):
        self.speed_key = speed_key
        self.speed_cfg = SPEED_PROFILES[self.speed_key]
        self.monitor_index = monitor_index
        self.auto_new_game = True

        self.on_status = on_status
        self.on_round_win = on_round_win

        self.is_running = False
        self.thread = None

        self.stored_clicks = {}
        self.state = 0  # 0: WAITING, 1: REVEAL, 2: CLICK
        self.last_action_time = 0.0
        self.click_cooldown_until = 0.0
        self.new_game_timer = None
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
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.on_status:
            self.on_status("STANDBY", "#ffe600")

    def _loop(self):
        if self.on_status:
            self.on_status("SEARCHING", "#00ffcc")

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
                            self.on_status("WATCHING", "#00ffcc")

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

                # --- AUTO NEW GAME CHECK ---
                if self.auto_new_game and self.state == 0 and len(active_tiles) == 0:
                    ng_pos = self._detect_new_game(frame)
                    if ng_pos:
                        if self.new_game_timer is None:
                            self.new_game_timer = now
                            if self.on_status:
                                self.on_status("NEW GAME IN 1.5s", "#ffe600")

                        if now - self.new_game_timer >= 1.5:
                            gx, gy = mon_left + ng_pos[0], mon_top + ng_pos[1]
                            pyautogui.click(gx, gy)
                            time.sleep(1.5)
                            self.new_game_timer = None
                            if self.on_status:
                                self.on_status("WATCHING", "#00ffcc")
                    else:
                        self.new_game_timer = None

                time.sleep(0.003)

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

    def _detect_new_game(self, frame):
        h, w = frame.shape[:2]
        roi = frame[int(h * 0.40):, :]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, LOWER_GREEN, UPPER_GREEN)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            if cv2.contourArea(cnt) > 1000:
                bx, by, bw, bh = cv2.boundingRect(cnt)
                ratio = bw / float(bh) if bh > 0 else 0
                if 2.0 <= ratio <= 8.0 and bw > 150:
                    return (bx + bw // 2, int(h * 0.40) + by + bh // 2)
        return None


# =============================================================================
# RETRO PIXEL UI (Pure 8-bit Arcade Cyber Aesthetic)
# =============================================================================
class PixelUI:
    # 8-bit Cyberpunk Arcade Color Palette
    C_BG = "#08090f"         # Deep black-blue CRT base
    C_PANEL = "#101321"      # Arcade cabinet inner frame
    C_BORDER = "#1f2744"     # Dark pixel grid line
    C_CYAN = "#00ffcc"       # Cyber cyan
    C_GREEN = "#39ff14"      # Arcade phosphor neon green
    C_PINK = "#ff0055"       # Cyber hot pink
    C_YELLOW = "#ffe600"     # Arcade warning yellow
    C_WHITE = "#e8eaf6"      # Crisp pixel white
    C_MUTED = "#525c7a"      # Dim pixel text

    def __init__(self, bot):
        self.bot = bot
        self.root = tk.Tk()
        self.root.title("MATIKS // BOT_OS")
        self.root.geometry("380x480")
        self.root.resizable(False, False)
        self.root.configure(bg=self.C_BG)

        # Always-on-top so it floats above the browser without getting hidden
        self.root.attributes("-topmost", True)

        # Monospace Pixel Font setup
        self.fn_pixel = ("Consolas", 9, "bold")
        self.fn_title = ("Consolas", 12, "bold")
        self.fn_large = ("Consolas", 14, "bold")
        self.fn_hud = ("Consolas", 10, "bold")

        # Hook bot callbacks
        self.bot.on_status = self.update_status_threadsafe
        self.bot.on_round_win = self.update_stats_threadsafe

        self.speed_buttons = {}
        self._build_ui()

    def _build_ui(self):
        # 1. Top Retro Header Box
        header = tk.Frame(self.root, bg=self.C_PANEL, highlightthickness=2, highlightbackground=self.C_CYAN)
        header.pack(fill=tk.X, padx=10, pady=(10, 6))

        title = tk.Label(
            header,
            text="[■■] MATIKS // BOT_OS v2.4",
            font=self.fn_title,
            fg=self.C_CYAN,
            bg=self.C_PANEL,
            padx=10,
            pady=6,
        )
        title.pack(side=tk.LEFT)

        tag = tk.Label(
            header,
            text="8-BIT",
            font=self.fn_pixel,
            fg=self.C_YELLOW,
            bg=self.C_PANEL,
            padx=10,
        )
        tag.pack(side=tk.RIGHT)

        # 2. Status HUD Panel
        hud_frame = tk.Frame(self.root, bg=self.C_PANEL, highlightthickness=2, highlightbackground=self.C_BORDER)
        hud_frame.pack(fill=tk.X, padx=10, pady=4)

        tk.Label(hud_frame, text="CORE STATUS:", font=self.fn_pixel, fg=self.C_MUTED, bg=self.C_PANEL).pack(anchor="w", padx=10, pady=(8, 0))

        self.lbl_status = tk.Label(
            hud_frame,
            text="● [ STANDBY ]",
            font=self.fn_large,
            fg=self.C_YELLOW,
            bg=self.C_PANEL,
            pady=4,
        )
        self.lbl_status.pack(anchor="w", padx=10)

        # Telemetry Grid inside HUD
        stats_box = tk.Frame(hud_frame, bg=self.C_PANEL)
        stats_box.pack(fill=tk.X, padx=10, pady=(0, 8))

        self.lbl_rounds = tk.Label(stats_box, text="ROUNDS : 000", font=self.fn_hud, fg=self.C_WHITE, bg=self.C_PANEL)
        self.lbl_rounds.pack(side=tk.LEFT)

        self.lbl_tiles = tk.Label(stats_box, text="TILES : 000", font=self.fn_hud, fg=self.C_WHITE, bg=self.C_PANEL)
        self.lbl_tiles.pack(side=tk.LEFT, padx=12)

        self.lbl_last_ms = tk.Label(stats_box, text="LAST : --ms", font=self.fn_hud, fg=self.C_CYAN, bg=self.C_PANEL)
        self.lbl_last_ms.pack(side=tk.RIGHT)

        # 3. Speed Selector (Chunky Pixel Switches)
        speed_frame = tk.Frame(self.root, bg=self.C_PANEL, highlightthickness=2, highlightbackground=self.C_BORDER)
        speed_frame.pack(fill=tk.X, padx=10, pady=6)

        tk.Label(
            speed_frame,
            text="SPEED CALIBRATION:",
            font=self.fn_pixel,
            fg=self.C_MUTED,
            bg=self.C_PANEL,
        ).pack(anchor="w", padx=10, pady=(6, 4))

        grid_btns = tk.Frame(speed_frame, bg=self.C_PANEL)
        grid_btns.pack(fill=tk.X, padx=8, pady=(0, 6))

        for idx, (skey, scfg) in enumerate(SPEED_PROFILES.items()):
            row = idx // 2
            col = idx % 2
            btn = tk.Button(
                grid_btns,
                text=f"[{scfg['label']}]",
                font=self.fn_pixel,
                relief=tk.FLAT,
                bd=0,
                padx=8,
                pady=6,
                activebackground=self.C_CYAN,
                activeforeground=self.C_BG,
                command=lambda k=skey: self.select_speed(k),
            )
            btn.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
            grid_btns.columnconfigure(col, weight=1)
            self.speed_buttons[skey] = btn

        self.lbl_speed_desc = tk.Label(
            speed_frame,
            text=SPEED_PROFILES[self.bot.speed_key]["desc"],
            font=self.fn_pixel,
            fg=self.C_CYAN,
            bg=self.C_PANEL,
            pady=4,
        )
        self.lbl_speed_desc.pack(anchor="w", padx=10)

        # Highlight current speed
        self._refresh_speed_buttons()

        # 4. Auto New Game Toggle Switch
        toggle_frame = tk.Frame(self.root, bg=self.C_BG)
        toggle_frame.pack(fill=tk.X, padx=12, pady=4)

        self.var_auto_ng = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(
            toggle_frame,
            text="[X] AUTO-RESTART (NEW GAME)",
            variable=self.var_auto_ng,
            font=self.fn_pixel,
            fg=self.C_WHITE,
            bg=self.C_BG,
            selectcolor=self.C_PANEL,
            activebackground=self.C_BG,
            activeforeground=self.C_CYAN,
            command=self.toggle_new_game,
        )
        chk.pack(anchor="w")

        # 5. Chunky Pixel Master Action Button
        action_box = tk.Frame(self.root, bg=self.C_BG)
        action_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 10))

        self.btn_master = tk.Button(
            action_box,
            text="[ ▶ ENGAGE BOT ]",
            font=self.fn_large,
            fg=self.C_BG,
            bg=self.C_GREEN,
            activebackground=self.C_WHITE,
            activeforeground=self.C_BG,
            relief=tk.FLAT,
            bd=0,
            command=self.toggle_bot,
        )
        self.btn_master.pack(fill=tk.BOTH, expand=True)

        # 6. Bottom hint footer
        footer = tk.Label(
            self.root,
            text="ABORT: MOVE MOUSE TO CORNER  |  ALWAYS ON TOP",
            font=("Consolas", 8),
            fg=self.C_MUTED,
            bg=self.C_BG,
            pady=2,
        )
        footer.pack(side=tk.BOTTOM)

    def select_speed(self, skey):
        self.bot.set_speed(skey)
        self.lbl_speed_desc.configure(text=SPEED_PROFILES[skey]["desc"])
        self._refresh_speed_buttons()

    def _refresh_speed_buttons(self):
        for skey, btn in self.speed_buttons.items():
            if skey == self.bot.speed_key:
                # Active pixel button: Neon Cyan highlight
                btn.configure(
                    bg=self.C_CYAN,
                    fg=self.C_BG,
                    highlightthickness=2,
                    highlightbackground=self.C_WHITE,
                )
            else:
                # Inactive button: Muted dark
                btn.configure(
                    bg=self.C_BG,
                    fg=self.C_WHITE,
                    highlightthickness=1,
                    highlightbackground=self.C_BORDER,
                )

    def toggle_new_game(self):
        self.bot.set_auto_new_game(self.var_auto_ng.get())

    def toggle_bot(self):
        if not self.bot.is_running:
            self.bot.start()
            self.btn_master.configure(
                text="[ ■ HALT BOT ]",
                bg=self.C_PINK,
                fg=self.C_WHITE,
            )
        else:
            self.bot.stop()
            self.btn_master.configure(
                text="[ ▶ ENGAGE BOT ]",
                bg=self.C_GREEN,
                fg=self.C_BG,
            )

    def update_status_threadsafe(self, text, color):
        def _update():
            self.lbl_status.configure(text=f"● [ {text} ]", fg=color)
        self.root.after(0, _update)

    def update_stats_threadsafe(self, rounds, tiles, last_ms):
        def _update():
            self.lbl_rounds.configure(text=f"ROUNDS : {rounds:03d}")
            self.lbl_tiles.configure(text=f"TILES : {tiles:03d}")
            self.lbl_last_ms.configure(text=f"LAST : {last_ms:.0f}ms")
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
    print(f"  Speed: [{bot.speed_cfg['label']}] - {bot.speed_cfg['desc']}")
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
        # Default: Launch the Retro Pixelated Arcade GUI!
        bot = BotEngine(speed_key=clean_speed, monitor_index=args.monitor)
        app = PixelUI(bot)
        app.run()


if __name__ == "__main__":
    main()
