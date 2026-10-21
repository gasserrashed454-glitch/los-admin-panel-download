# -*- coding: utf-8 -*-
"""
LOS ADMIN BROADCAST CONSOLE
Apple-inspired dark sidebar overlay for Roblox.

HOTKEY : F8  (toggle sidebar in/out)
CLICK  : any broadcast row  ->  copies the command + auto-pastes into Roblox chat
EDIT   : config.json  (add/remove categories & messages, change hotkey)
"""

import json
import os
import sys
import threading
import time
import tkinter as tk

try:
    import keyboard  # global hotkey + key simulation
except Exception:
    keyboard = None

# ------------------------------------------------------------------ palette
BG        = "#121212"
PANEL     = "#0E0E0E"
CARD      = "#1A1A1A"
HOVER     = "#2C2C2C"
CAT_BG    = "#1E1E1E"
LINE      = "#2A2A2A"
FG        = "#FFFFFF"
MUTED     = "#8A8A8A"
DIM       = "#5E5E5E"

PANEL_W   = 340
TAB_W     = 22
TAB_H     = 130
ROW_H     = 36
CMD_PREFIX = "message broadcast @all "

FONT       = "Segoe UI"
FONT_BOLD  = "Segoe UI Semibold"


# ------------------------------------------------------------------ helpers
def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def load_config():
    path = resource_path("config.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"hotkey": "f8", "prefix": "", "auto_paste": True,
                "categories": [{"name": "MAIN BROADCASTS",
                                "items": ["message broadcast @all hello"]}]}


def animate(widget, setter, frm, to, duration=200, steps=14):
    """Cubic ease-out tween driven by tk's event loop (no thread hopping)."""
    def ease(t):
        return 1 - (1 - t) ** 3

    def step(i=0):
        t = i / float(steps)
        setter(int(round(frm + (to - frm) * ease(t))))
        if i < steps:
            widget.after(max(1, duration // steps), lambda: step(i + 1))

    step()


def display_text(cmd):
    """Short, clean label for the row (full command still fires on click)."""
    t = cmd
    if t.startswith(CMD_PREFIX):
        t = t[len(CMD_PREFIX):]
    return t if len(t) <= 90 else t[:87] + "..."


# ------------------------------------------------------------------ accordion
class Category(object):
    def __init__(self, parent, name, items, on_fire):
        self.on_fire = on_fire
        self.expanded = False
        self.full_h = len(items) * ROW_H + 8

        self.wrap = tk.Frame(parent, bg=BG)
        self.wrap.pack(fill="x", padx=10, pady=(0, 8))

        self.header = tk.Frame(self.wrap, bg=CAT_BG, height=44, cursor="hand2")
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        self.title = tk.Label(self.header, text=name, bg=CAT_BG, fg=FG,
                              font=(FONT_BOLD, 10), anchor="w")
        self.title.place(x=15, rely=0.5, anchor="w")

        self.chev = tk.Label(self.header, text="+", bg=CAT_BG, fg=MUTED,
                             font=(FONT, 14))
        self.chev.place(relx=1.0, x=-15, rely=0.5, anchor="e")

        for w in (self.header, self.title, self.chev):
            w.bind("<Button-1>", lambda e: self.toggle())
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))

        self.body = tk.Frame(self.wrap, bg=BG, height=0)
        self.body.pack(fill="x")
        self.body.pack_propagate(False)

        for cmd in items:
            self._make_row(cmd)

    def _hover(self, on):
        bg = HOVER if on else CAT_BG
        self.header.configure(bg=bg)
        self.title.configure(bg=bg)
        self.chev.configure(bg=bg)

    def _make_row(self, cmd):
        row = tk.Frame(self.body, bg=CARD, height=ROW_H - 4, cursor="hand2")
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)

        lbl = tk.Label(row, text=display_text(cmd), bg=CARD, fg=MUTED,
                       font=(FONT, 7), anchor="w", justify="left")
        lbl.place(x=13, rely=0.5, anchor="w")

        def enter(_e):
            row.configure(bg=HOVER)
            lbl.configure(bg=HOVER, fg=FG)

        def leave(_e):
            row.configure(bg=CARD)
            lbl.configure(bg=CARD, fg=MUTED)

        for w in (row, lbl):
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            w.bind("<Button-1>", lambda e, c=cmd: self.on_fire(c))

    def toggle(self):
        target = self.full_h if not self.expanded else 0
        animate(self.body, lambda v: self.body.configure(height=v),
                self.body.winfo_height(), target, 180, 12)
        self.expanded = not self.expanded
        self.chev.configure(text="-" if self.expanded else "+")


# ------------------------------------------------------------------ overlay
class Overlay(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.prefix = cfg.get("prefix", "")
        self._queue = []
        self.panel_x = -PANEL_W
        self.is_open = False

        self.root = tk.Tk()
        self.root.title("LOS Admin Panel")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.97)
        except Exception:
            pass
        self.root.configure(bg=BG)

        self.screen_h = self.root.winfo_screenheight()
        self.root.geometry("%dx%d+%d+0" % (PANEL_W, self.screen_h, self.panel_x))

        self.auto_paste = tk.BooleanVar(value=bool(cfg.get("auto_paste", True)))
        self.auto_broadcast = tk.BooleanVar(value=False)
        self.anti_afk = tk.BooleanVar(value=False)
        self.auto_broadcast_interval = 5
        self.main_broadcasts = []
        for category in cfg.get("categories", []):
            if category.get("name", "").strip().upper() == "MAIN BROADCASTS":
                self.main_broadcasts = list(category.get("items", []))
                break
        self._broadcast_index = 0
        self._afk_direction = "w"

        # ---- edge tab (stays glued to the panel edge, always visible)
        self.tab = tk.Toplevel(self.root)
        self.tab.overrideredirect(True)
        self.tab.attributes("-topmost", True)
        self.tab.configure(bg=LINE)
        self.tab_label = tk.Label(self.tab, text="\u203a", bg=CAT_BG, fg=FG,
                                  font=(FONT_BOLD, 14), cursor="hand2")
        self.tab_label.pack(fill="both", expand=True, padx=1, pady=1)
        self.tab_label.bind("<Button-1>", lambda e: self.toggle_panel())
        self.tab_label.bind("<Enter>", lambda e: self.tab_label.configure(bg=HOVER))
        self.tab_label.bind("<Leave>", lambda e: self.tab_label.configure(bg=CAT_BG))
        self._place_tab(self.panel_x)

        # ---- header
        head = tk.Frame(self.root, bg=PANEL, height=66)
        head.pack(fill="x")
        head.pack_propagate(False)

        tk.Label(head, text="LOS", bg=PANEL, fg=FG,
                 font=(FONT_BOLD, 17)).place(x=18, y=9)
        tk.Label(head, text="ADMIN BROADCAST CONSOLE", bg=PANEL, fg=DIM,
                 font=(FONT, 7)).place(x=19, y=38)

        close = tk.Label(head, text="\u2715", bg=PANEL, fg=DIM,
                         font=(FONT, 11), cursor="hand2")
        close.place(relx=1.0, x=-16, y=20, anchor="ne")
        close.bind("<Button-1>", lambda e: self.quit())
        close.bind("<Enter>", lambda e: close.configure(fg=FG))
        close.bind("<Leave>", lambda e: close.configure(fg=DIM))

        tk.Frame(self.root, bg=LINE, height=1).pack(fill="x")

        # ---- footer (packed before the scroll area)
        foot = tk.Frame(self.root, bg=PANEL, height=84)
        foot.pack(side="bottom", fill="x")
        foot.pack_propagate(False)

        tk.Frame(foot, bg=LINE, height=1).pack(fill="x")
        self.status = tk.Label(foot, text="READY  â€¢  F8 TO TOGGLE", bg=PANEL, fg=DIM,
                               font=(FONT, 7), anchor="w")
        self.status.pack(fill="x", padx=14, pady=(6, 0))

        cb = tk.Checkbutton(
            foot, text="auto-paste into Roblox  (F2 \u2192 Ctrl+V \u2192 Enter)",
            variable=self.auto_paste, bg=PANEL, fg=MUTED,
            activebackground=PANEL, activeforeground=FG, selectcolor=PANEL,
            font=(FONT, 7), bd=0, highlightthickness=0, cursor="hand2",
            anchor="w")
        cb.pack(fill="x", padx=10)

        controls = tk.Frame(foot, bg=PANEL)
        controls.pack(fill="x", padx=10, pady=(2, 4))
        self.auto_broadcast_button = tk.Checkbutton(
            controls, text="auto broadcast  (every 5 sec)",
            variable=self.auto_broadcast, command=self._toggle_auto_broadcast,
            bg=PANEL, fg=MUTED, activebackground=PANEL,
            activeforeground=FG, selectcolor=PANEL,
            font=(FONT, 7), bd=0, highlightthickness=0, cursor="hand2",
            anchor="w"
        )
        self.auto_broadcast_button.pack(side="left", fill="x", expand=True)
        self.anti_afk_button = tk.Checkbutton(
            controls, text="anti-AFK",
            variable=self.anti_afk, command=self._toggle_anti_afk,
            bg=PANEL, fg=MUTED, activebackground=PANEL,
            activeforeground=FG, selectcolor=PANEL,
            font=(FONT, 7), bd=0, highlightthickness=0, cursor="hand2",
            anchor="e"
        )
        self.anti_afk_button.pack(side="right")

        # ---- scrollable body
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=BG)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", self._wheel)
        self.canvas.bind("<Button-5>", self._wheel)

        tk.Frame(self.inner, bg=BG, height=10).pack(fill="x")
        for cat in cfg.get("categories", []):
            Category(self.inner, cat.get("name", "CATEGORY"), cat.get("items", []), self.fire)
        tk.Frame(self.inner, bg=BG, height=10).pack(fill="x")

        # ---- hotkey
        if keyboard is not None:
            try:
                keyboard.add_hotkey(cfg.get("hotkey", "f8"),
                                    lambda: self._queue.append(self.toggle_panel))
            except Exception:
                self.set_status("HOTKEY FAILED - RUN AS ADMIN")
        else:
            self.set_status("KEYBOARD MODULE MISSING")

    # -------------------------------------------------- plumbing
    def _wheel(self, event):
        delta = 0
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")

    def _place_tab(self, x):
        self.tab.geometry("%dx%d+%d+%d" % (TAB_W, TAB_H, x + PANEL_W,
                                           (self.screen_h - TAB_H) // 2))

    def set_status(self, text):
        try:
            self.status.configure(text=text)
        except Exception:
            pass

    def _poll(self):
        while self._queue:
            fn = self._queue.pop(0)
            try:
                fn()
            except Exception:
                pass
        self.root.after(40, self._poll)

    def _toggle_auto_broadcast(self):
        if self.auto_broadcast.get():
            if not self.main_broadcasts:
                self.auto_broadcast.set(False)
                self.set_status("NO MAIN BROADCASTS CONFIGURED")
                return
            self._broadcast_index = 0
            self.set_status("AUTO BROADCAST ON  \u2022  EVERY 5 SEC")
            self._auto_broadcast_tick()
        else:
            self.set_status("AUTO BROADCAST OFF")

    def _auto_broadcast_tick(self):
        if not self.auto_broadcast.get():
            return
        cmd = self.main_broadcasts[self._broadcast_index]
        self._broadcast_index = (self._broadcast_index + 1) % len(self.main_broadcasts)
        self.fire(cmd)
        self.root.after(self.auto_broadcast_interval * 1000,
                        self._auto_broadcast_tick)

    def _toggle_anti_afk(self):
        if self.anti_afk.get():
            if keyboard is None:
                self.anti_afk.set(False)
                self.set_status("ANTI-AFK UNAVAILABLE - INSTALL KEYBOARD")
                return
            self.set_status("ANTI-AFK ON  \u2022  MOVING EVERY 5 SEC")
            self._anti_afk_tick()
        else:
            self.set_status("ANTI-AFK OFF")

    def _anti_afk_tick(self):
        if not self.anti_afk.get():
            return
        if keyboard is not None:
            direction = self._afk_direction
            self._afk_direction = "s" if direction == "w" else "w"
            try:
                keyboard.press(direction)
                self.root.after(180, lambda: keyboard.release(direction))
            except Exception:
                self.set_status("ANTI-AFK FAILED - RUN AS ADMIN")
                self.anti_afk.set(False)
                return
        self.root.after(5000, self._anti_afk_tick)

    # -------------------------------------------------- panel slide
    def toggle_panel(self):
        target = 0 if not self.is_open else -PANEL_W

        def setter(x):
            self.panel_x = x
            self.root.geometry("%dx%d+%d+0" % (PANEL_W, self.screen_h, x))
            self._place_tab(x)

        animate(self.root, setter, self.panel_x, target, 220, 16)
        self.is_open = not self.is_open
        self.tab_label.configure(text="\u2039" if self.is_open else "\u203a")

    # -------------------------------------------------- broadcast fire
    def fire(self, cmd):
        full = self.prefix + cmd

        self.root.clipboard_clear()
        self.root.clipboard_append(full)
        self.root.update_idletasks()

        if self.auto_paste.get() and keyboard is not None:
            self.set_status("PASTING INTO ROBLOX...")
            threading.Thread(target=self._paste, args=(full,), daemon=True).start()
        else:
            self.set_status("COPIED TO CLIPBOARD")

    def _paste(self, _text):
        try:
            time.sleep(0.05)
            keyboard.send("f2")        # open Roblox chat
            time.sleep(0.32)
            keyboard.send("ctrl+v")    # paste command (emoji-safe)
            time.sleep(0.16)
            keyboard.send("enter")     # send
            self._queue.append(lambda: self.set_status("SENT  \u2713"))
        except Exception:
            self._queue.append(lambda: self.set_status("PASTE FAILED - RUN AS ADMIN"))

    # -------------------------------------------------- lifecycle
    def run(self):
        self.root.after(40, self._poll)
        if self.cfg.get("open_on_start", False):
            self.root.after(300, self.toggle_panel)
        self.root.mainloop()

    def quit(self):
        self.auto_broadcast.set(False)
        self.anti_afk.set(False)
        try:
            if keyboard is not None:
                keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    Overlay(load_config()).run()
