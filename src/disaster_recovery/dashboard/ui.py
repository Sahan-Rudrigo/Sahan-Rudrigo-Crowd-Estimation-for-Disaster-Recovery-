# """
# dashboard/ui.py

# Live dashboard UI for the door counter system.
# Reads state.json every second — no connection to tracking code needed.

# Run in a separate terminal while your tracking system is running:
#     python dashboard/ui.py

# Features:
#   - Global summary (total IN / OUT / currently inside across all doors)
#   - Per-door cards for Door 1, Door 2, Door 3
#   - Set initial count per door (e.g. if 10 people were already inside)
#   - Reset counts per door
#   - Live "last event" timer
#   - Auto-refreshes every second
# """

# import tkinter as tk
# from tkinter import ttk, simpledialog, messagebox
# import json
# import os
# import time
# import threading

# STATE_FILE = "dashboard/state.json"
# REFRESH_MS = 1000   # poll every 1 second

# DOOR_IDS   = ["door1", "door2", "door3"]
# DOOR_NAMES = ["Door 1 — Main entrance", "Door 2", "Door 3"]

# # Colours
# C_GREEN  = "#3B6D11"
# C_BLUE   = "#185FA5"
# C_TEAL   = "#0F6E56"
# C_BG     = "#F5F5F3"
# C_CARD   = "#FFFFFF"
# C_ACTIVE = "#1D9E75"
# C_MUTED  = "#888780"
# C_RED    = "#A32D2D"
# C_TEXT   = "#1A1A18"
# C_SUB    = "#5F5E5A"


# def read_state() -> dict:
#     if not os.path.exists(STATE_FILE):
#         return {"doors": {}, "global_in": 0, "global_out": 0,
#                 "global_inside": 0, "timestamp": 0}
#     try:
#         with open(STATE_FILE, "r") as f:
#             return json.load(f)
#     except Exception:
#         return {"doors": {}, "global_in": 0, "global_out": 0,
#                 "global_inside": 0, "timestamp": 0}


# def write_state(state: dict):
#     os.makedirs("dashboard", exist_ok=True)
#     with open(STATE_FILE, "w") as f:
#         json.dump(state, f, indent=2)


# def time_ago(ts: float) -> str:
#     if ts == 0:
#         return "no events yet"
#     diff = time.time() - ts
#     if diff < 60:
#         return f"{int(diff)}s ago"
#     elif diff < 3600:
#         return f"{int(diff/60)}m ago"
#     else:
#         return f"{int(diff/3600)}h ago"


# class DoorCard(tk.Frame):
#     def __init__(self, parent, door_id: str, door_name: str, **kwargs):
#         super().__init__(parent, bg=C_CARD, relief="flat",
#                          highlightthickness=1,
#                          highlightbackground="#D3D1C7", **kwargs)
#         self.door_id   = door_id
#         self.door_name = door_name
#         self._initial  = 0   # user-set initial count for this door
#         self._build()

#     def _build(self):
#         # ── Header row ────────────────────────────────────────────────────────
#         hdr = tk.Frame(self, bg=C_CARD)
#         hdr.pack(fill="x", padx=14, pady=(12, 0))

#         self.dot = tk.Label(hdr, text="●", font=("Helvetica", 10),
#                             fg=C_MUTED, bg=C_CARD)
#         self.dot.pack(side="left")

#         self.title_lbl = tk.Label(hdr, text=self.door_name,
#                                   font=("Helvetica", 13, "bold"),
#                                   fg=C_TEXT, bg=C_CARD)
#         self.title_lbl.pack(side="left", padx=(4, 0))

#         self.status_lbl = tk.Label(hdr, text="not configured",
#                                    font=("Helvetica", 10),
#                                    fg=C_MUTED, bg=C_CARD)
#         self.status_lbl.pack(side="right")

#         # ── Stats row ─────────────────────────────────────────────────────────
#         stats = tk.Frame(self, bg=C_CARD)
#         stats.pack(fill="x", padx=14, pady=10)

#         self.in_var  = tk.StringVar(value="—")
#         self.out_var = tk.StringVar(value="—")
#         self.net_var = tk.StringVar(value="—")

#         for label_text, var, colour, col in [
#             ("In",          self.in_var,  C_GREEN, 0),
#             ("Out",         self.out_var, C_BLUE,  1),
#             ("Inside now",  self.net_var, C_TEAL,  2),
#         ]:
#             cell = tk.Frame(stats, bg="#F1EFE8", padx=10, pady=6)
#             cell.grid(row=0, column=col, padx=(0, 6) if col < 2 else 0,
#                       sticky="ew")
#             stats.columnconfigure(col, weight=1)
#             tk.Label(cell, text=label_text, font=("Helvetica", 10),
#                      fg=C_SUB, bg="#F1EFE8").pack(anchor="w")
#             tk.Label(cell, textvariable=var, font=("Helvetica", 22, "bold"),
#                      fg=colour, bg="#F1EFE8").pack(anchor="w")

#         # ── Footer row ────────────────────────────────────────────────────────
#         ftr = tk.Frame(self, bg=C_CARD)
#         ftr.pack(fill="x", padx=14, pady=(0, 12))

#         tk.Button(ftr, text="Set initial count",
#                   font=("Helvetica", 10), relief="flat",
#                   bg="#F1EFE8", fg=C_TEXT, padx=8, pady=3,
#                   cursor="hand2",
#                   command=self._set_initial).pack(side="left", padx=(0, 6))

#         tk.Button(ftr, text="Reset",
#                   font=("Helvetica", 10), relief="flat",
#                   bg="#FCEBEB", fg=C_RED, padx=8, pady=3,
#                   cursor="hand2",
#                   command=self._reset).pack(side="left")

#         self.time_lbl = tk.Label(ftr, text="", font=("Helvetica", 10),
#                                  fg=C_MUTED, bg=C_CARD)
#         self.time_lbl.pack(side="right")

#         # ── Inactive placeholder ──────────────────────────────────────────────
#         self.inactive_lbl = tk.Label(self,
#                                      text="No cameras assigned to this door",
#                                      font=("Helvetica", 11), fg=C_MUTED, bg=C_CARD)

#     def refresh(self, door_data: dict | None):
#         """Update all displayed values from door_data dict (or None if inactive)."""
#         if door_data is None or not door_data.get("active", False):
#             # Inactive state
#             self.dot.config(fg=C_MUTED)
#             self.status_lbl.config(text="not configured")
#             self.in_var.set("—")
#             self.out_var.set("—")
#             self.net_var.set("—")
#             self.time_lbl.config(text="")
#             self.inactive_lbl.pack(pady=(0, 12))
#             self.configure(highlightbackground="#D3D1C7")
#             return

#         self.inactive_lbl.pack_forget()
#         self.dot.config(fg=C_ACTIVE)
#         self.status_lbl.config(text="running")
#         self.configure(highlightbackground=C_ACTIVE)

#         net = door_data.get("initial_count", self._initial) + \
#               door_data.get("total_in", 0) - door_data.get("total_out", 0)

#         self.in_var.set(str(door_data.get("total_in", 0)))
#         self.out_var.set(str(door_data.get("total_out", 0)))
#         self.net_var.set(str(max(0, net)))
#         self.time_lbl.config(text=time_ago(door_data.get("last_updated", 0)))

#     def _set_initial(self):
#         val = simpledialog.askinteger(
#             "Set initial count",
#             f"How many people were already inside at {self.door_name}\n"
#             f"when the system started?",
#             minvalue=0, maxvalue=9999,
#             initialvalue=self._initial,
#         )
#         if val is not None:
#             self._initial = val
#             # Patch state.json so net_inside updates immediately
#             state = read_state()
#             if self.door_id in state.get("doors", {}):
#                 state["doors"][self.door_id]["initial_count"] = val
#                 state["doors"][self.door_id]["net_inside"] = (
#                     val
#                     + state["doors"][self.door_id].get("total_in", 0)
#                     - state["doors"][self.door_id].get("total_out", 0)
#                 )
#                 state["global_inside"] = sum(
#                     d["net_inside"] for d in state["doors"].values()
#                 )
#                 write_state(state)

#     def _reset(self):
#         if not messagebox.askyesno("Reset", f"Reset counts for {self.door_name}?"):
#             return
#         self._initial = 0
#         state = read_state()
#         if self.door_id in state.get("doors", {}):
#             state["doors"][self.door_id]["total_in"]      = 0
#             state["doors"][self.door_id]["total_out"]     = 0
#             state["doors"][self.door_id]["initial_count"] = 0
#             state["doors"][self.door_id]["net_inside"]    = 0
#             state["global_in"]     = sum(d["total_in"]  for d in state["doors"].values())
#             state["global_out"]    = sum(d["total_out"] for d in state["doors"].values())
#             state["global_inside"] = sum(d["net_inside"] for d in state["doors"].values())
#             write_state(state)


# class DashboardApp(tk.Tk):
#     def __init__(self):
#         super().__init__()
#         self.title("Door Counter — Live Monitor")
#         self.configure(bg=C_BG)
#         self.resizable(False, False)
#         self._build()
#         self._schedule_refresh()

#     def _build(self):
#         pad = {"padx": 16, "pady": 0}

#         # ── Header ────────────────────────────────────────────────────────────
#         hdr = tk.Frame(self, bg=C_BG)
#         hdr.pack(fill="x", padx=16, pady=(16, 10))
#         tk.Label(hdr, text="Door counter",
#                  font=("Helvetica", 16, "bold"),
#                  fg=C_TEXT, bg=C_BG).pack(side="left")
#         self.active_badge = tk.Label(hdr, text="0 active",
#                                      font=("Helvetica", 10),
#                                      bg="#EAF3DE", fg="#27500A",
#                                      padx=8, pady=2)
#         self.active_badge.pack(side="left", padx=10)
#         self.clock_lbl = tk.Label(hdr, text="",
#                                   font=("Helvetica", 10), fg=C_MUTED, bg=C_BG)
#         self.clock_lbl.pack(side="right")

#         # ── Global summary ────────────────────────────────────────────────────
#         summary = tk.Frame(self, bg=C_BG)
#         summary.pack(fill="x", padx=16, pady=(0, 12))

#         self.g_in  = tk.StringVar(value="0")
#         self.g_out = tk.StringVar(value="0")
#         self.g_net = tk.StringVar(value="0")

#         for label_text, var, colour, col in [
#             ("Total in (all doors)",  self.g_in,  C_GREEN, 0),
#             ("Total out (all doors)", self.g_out, C_BLUE,  1),
#             ("Currently inside",      self.g_net, C_TEAL,  2),
#         ]:
#             cell = tk.Frame(summary, bg="#F1EFE8", padx=14, pady=10)
#             cell.grid(row=0, column=col,
#                       padx=(0, 8) if col < 2 else 0, sticky="ew")
#             summary.columnconfigure(col, weight=1)
#             tk.Label(cell, text=label_text, font=("Helvetica", 10),
#                      fg=C_SUB, bg="#F1EFE8").pack(anchor="w")
#             tk.Label(cell, textvariable=var, font=("Helvetica", 28, "bold"),
#                      fg=colour, bg="#F1EFE8").pack(anchor="w")

#         # ── Door cards ────────────────────────────────────────────────────────
#         self.door_cards: list[DoorCard] = []
#         for door_id, door_name in zip(DOOR_IDS, DOOR_NAMES):
#             card = DoorCard(self, door_id=door_id, door_name=door_name)
#             card.pack(fill="x", padx=16, pady=(0, 8))
#             self.door_cards.append(card)

#         # bottom padding
#         tk.Frame(self, bg=C_BG, height=8).pack()

#         self.geometry("520x680")

#     def _refresh(self):
#         state = read_state()
#         doors = state.get("doors", {})

#         # Global summary
#         self.g_in.set(str(state.get("global_in", 0)))
#         self.g_out.set(str(state.get("global_out", 0)))
#         self.g_net.set(str(max(0, state.get("global_inside", 0))))

#         # Active badge
#         active = sum(1 for d in doors.values() if d.get("active", False))
#         self.active_badge.config(text=f"{active} active")

#         # Clock
#         self.clock_lbl.config(
#             text=time.strftime("%H:%M:%S")
#         )

#         # Per-door cards
#         for card in self.door_cards:
#             card.refresh(doors.get(card.door_id))

#     def _schedule_refresh(self):
#         self._refresh()
#         self.after(REFRESH_MS, self._schedule_refresh)


# if __name__ == "__main__":
#     app = DashboardApp()
#     app.mainloop()

"""
dashboard/ui.py

Two-tab dashboard:
  Tab 1 — Door counts : IN/OUT/inside per door, reset, set initial count
  Tab 2 — Who's inside: prev/next navigation, photo thumbnail, description

Run in a separate terminal:
    python dashboard/ui.py
"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import json
import os
import time

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

STATE_FILE = "dashboard/state.json"
OCCUPANTS_FILE = "dashboard/occupants.json"
EVENT_QUEUE = "event_queue"
REFRESH_MS = 1000

DOOR_IDS = ["door1", "door2", "door3"]
DOOR_NAMES = ["Door 1 — Main entrance", "Door 2", "Door 3"]

# Colors
C_GREEN = "#3B6D11"
C_BLUE = "#185FA5"
C_TEAL = "#0F6E56"
C_BG = "#F5F5F3"
C_CARD = "#FFFFFF"
C_ACTIVE = "#1D9E75"
C_MUTED = "#888780"
C_RED = "#A32D2D"
C_TEXT = "#1A1A18"
C_SUB = "#5F5E5A"
C_META = "#F1EFE8"

C_SOFT_GREEN = "#EAF3DE"
C_SOFT_BLUE = "#E7F0FA"
C_SOFT_TEAL = "#E6F6F1"
C_BIG_BG = "#E8F5E9"
C_BIG_TEXT = "#1B5E20"
C_BORDER = "#D3D1C7"
C_HOVER = "#F9F9F9"


def read_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {
            "doors": {},
            "global_in": 0,
            "global_out": 0,
            "global_inside": 0,
            "timestamp": 0
        }
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {
            "doors": {},
            "global_in": 0,
            "global_out": 0,
            "global_inside": 0,
            "timestamp": 0
        }


def write_state(state: dict):
    os.makedirs("dashboard", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def read_occupants() -> dict:
    if not os.path.exists(OCCUPANTS_FILE):
        return {}
    try:
        with open(OCCUPANTS_FILE, "r") as f:
            return json.load(f).get("occupants", {})
    except Exception:
        return {}


def time_ago(ts: float) -> str:
    if not ts:
        return "no events yet"
    d = time.time() - ts
    if d < 60:
        return f"{int(d)}s ago"
    if d < 3600:
        return f"{int(d/60)}m ago"
    return f"{int(d/3600)}h ago"


class StatCard(tk.Frame):
    def __init__(self, parent, title: str, value_var: tk.StringVar,
                 bg_color: str, value_color: str, **kwargs):
        super().__init__(
            parent,
            bg=bg_color,
            highlightthickness=1,
            highlightbackground=C_BORDER,
            bd=0,
            **kwargs
        )

        tk.Label(
            self,
            text=title,
            font=("Helvetica", 10),
            fg=C_SUB,
            bg=bg_color
        ).pack(anchor="w", padx=14, pady=(10, 2))

        tk.Label(
            self,
            textvariable=value_var,
            font=("Helvetica", 28, "bold"),
            fg=value_color,
            bg=bg_color
        ).pack(anchor="w", padx=14, pady=(0, 10))


class DoorCard(tk.Frame):
    def __init__(self, parent, door_id: str, door_name: str, **kwargs):
        super().__init__(
            parent,
            bg=C_CARD,
            relief="flat",
            highlightthickness=1,
            highlightbackground=C_BORDER,
            **kwargs
        )
        self.door_id = door_id
        self.door_name = door_name
        self._initial = 0
        self._build()
        self._bind_hover_recursive(self)

    def _bind_hover_recursive(self, widget):
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        for child in widget.winfo_children():
            self._bind_hover_recursive(child)

    def _on_enter(self, _event=None):
        self.configure(bg=C_HOVER)

    def _on_leave(self, _event=None):
        self.configure(bg=C_CARD)

    def _build(self):
        hdr = tk.Frame(self, bg=C_CARD)
        hdr.pack(fill="x", padx=14, pady=(12, 0))

        self.dot = tk.Label(
            hdr,
            text="●",
            font=("Helvetica", 10),
            fg=C_MUTED,
            bg=C_CARD
        )
        self.dot.pack(side="left")

        self.title_lbl = tk.Label(
            hdr,
            text=self.door_name,
            font=("Helvetica", 13, "bold"),
            fg=C_TEXT,
            bg=C_CARD
        )
        self.title_lbl.pack(side="left", padx=(6, 0))

        self.status_lbl = tk.Label(
            hdr,
            text="not configured",
            font=("Helvetica", 10),
            fg=C_MUTED,
            bg=C_CARD
        )
        self.status_lbl.pack(side="right")

        stats = tk.Frame(self, bg=C_CARD)
        stats.pack(fill="x", padx=14, pady=10)

        self.in_var = tk.StringVar(value="—")
        self.out_var = tk.StringVar(value="—")
        self.net_var = tk.StringVar(value="—")

        stat_data = [
            ("🟢 In", self.in_var, C_SOFT_GREEN, C_GREEN),
            ("🔵 Out", self.out_var, C_SOFT_BLUE, C_BLUE),
            ("👥 Inside", self.net_var, C_SOFT_TEAL, C_TEAL),
        ]

        for col, (label_text, var, bg_col, val_col) in enumerate(stat_data):
            cell = tk.Frame(stats, bg=bg_col, padx=10, pady=6)
            cell.grid(row=0, column=col, padx=(0, 6) if col < 2 else 0, sticky="ew")
            stats.columnconfigure(col, weight=1)

            tk.Label(
                cell,
                text=label_text,
                font=("Helvetica", 10),
                fg=C_SUB,
                bg=bg_col
            ).pack(anchor="w")

            tk.Label(
                cell,
                textvariable=var,
                font=("Helvetica", 22, "bold"),
                fg=val_col,
                bg=bg_col
            ).pack(anchor="w")

        ftr = tk.Frame(self, bg=C_CARD)
        ftr.pack(fill="x", padx=14, pady=(0, 12))

        tk.Button(
            ftr,
            text="Set initial count",
            font=("Helvetica", 10),
            relief="flat",
            bg="#F1EFE8",
            fg=C_TEXT,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._set_initial
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            ftr,
            text="Reset",
            font=("Helvetica", 10),
            relief="flat",
            bg="#FCEBEB",
            fg=C_RED,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._reset
        ).pack(side="left")

        self.time_lbl = tk.Label(
            ftr,
            text="",
            font=("Helvetica", 10),
            fg=C_MUTED,
            bg=C_CARD
        )
        self.time_lbl.pack(side="right")

        self.inactive_lbl = tk.Label(
            self,
            text="No cameras assigned to this door",
            font=("Helvetica", 11),
            fg=C_MUTED,
            bg=C_CARD
        )

    def refresh(self, door_data: dict | None):
        if door_data is None or not door_data.get("active", False):
            self.dot.config(fg=C_MUTED)
            self.status_lbl.config(text="not configured", fg=C_MUTED)
            self.in_var.set("—")
            self.out_var.set("—")
            self.net_var.set("—")
            self.time_lbl.config(text="")
            self.inactive_lbl.pack(pady=(0, 12))
            self.configure(highlightbackground=C_BORDER, highlightthickness=1)
            return

        self.inactive_lbl.pack_forget()
        self.dot.config(fg=C_ACTIVE)
        self.status_lbl.config(text="running", fg=C_ACTIVE)
        self.configure(highlightbackground=C_ACTIVE, highlightthickness=2)

        net = (
            door_data.get("initial_count", self._initial)
            + door_data.get("total_in", 0)
            - door_data.get("total_out", 0)
        )

        self.in_var.set(str(door_data.get("total_in", 0)))
        self.out_var.set(str(door_data.get("total_out", 0)))
        self.net_var.set(str(max(0, net)))
        self.time_lbl.config(text=f"Last event: {time_ago(door_data.get('last_updated', 0))}")

    def _set_initial(self):
        val = simpledialog.askinteger(
            "Set initial count",
            f"How many people were already inside at {self.door_name}\nwhen the system started?",
            minvalue=0,
            maxvalue=9999,
            initialvalue=self._initial,
        )
        if val is not None:
            self._initial = val
            state = read_state()
            if self.door_id in state.get("doors", {}):
                state["doors"][self.door_id]["initial_count"] = val
                state["doors"][self.door_id]["net_inside"] = (
                    val
                    + state["doors"][self.door_id].get("total_in", 0)
                    - state["doors"][self.door_id].get("total_out", 0)
                )
                state["global_inside"] = sum(
                    d["net_inside"] for d in state["doors"].values()
                )
                write_state(state)

    def _reset(self):
        if not messagebox.askyesno("Reset", f"Reset counts for {self.door_name}?"):
            return
        self._initial = 0
        state = read_state()
        if self.door_id in state.get("doors", {}):
            state["doors"][self.door_id]["total_in"] = 0
            state["doors"][self.door_id]["total_out"] = 0
            state["doors"][self.door_id]["initial_count"] = 0
            state["doors"][self.door_id]["net_inside"] = 0
            state["global_in"] = sum(d["total_in"] for d in state["doors"].values())
            state["global_out"] = sum(d["total_out"] for d in state["doors"].values())
            state["global_inside"] = sum(d["net_inside"] for d in state["doors"].values())
            write_state(state)


class OccupantsTab(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=C_BG, **kwargs)
        self._people = []
        self._index = 0
        self._photo = None
        self._build()

    def _build(self):
        self.empty_lbl = tk.Label(
            self,
            text="Building is currently empty",
            font=("Helvetica", 13),
            fg=C_MUTED,
            bg=C_BG
        )
        self.empty_lbl.pack(expand=True, pady=40)

        self.content = tk.Frame(self, bg=C_BG)

        self.counter_lbl = tk.Label(
            self.content,
            text="",
            font=("Helvetica", 11),
            fg=C_MUTED,
            bg=C_BG
        )
        self.counter_lbl.pack(pady=(12, 6))

        self.card = tk.Frame(
            self.content,
            bg=C_CARD,
            highlightthickness=1,
            highlightbackground=C_BORDER
        )
        self.card.pack(padx=16, fill="x")

        badge_row = tk.Frame(self.card, bg=C_CARD)
        badge_row.pack(fill="x", padx=16, pady=(14, 8))

        self.id_badge = tk.Label(
            badge_row,
            text="",
            font=("Helvetica", 11, "bold"),
            bg="#E6F1FB",
            fg="#0C447C",
            padx=10,
            pady=3
        )
        self.id_badge.pack(side="left")

        tk.Label(
            badge_row,
            text="inside",
            font=("Helvetica", 10),
            bg="#EAF3DE",
            fg="#27500A",
            padx=8,
            pady=3
        ).pack(side="left", padx=8)

        body = tk.Frame(self.card, bg=C_CARD)
        body.pack(fill="x", padx=16, pady=(0, 16))

        self.photo_frame = tk.Frame(body, bg=C_META, width=110, height=150)
        self.photo_frame.pack_propagate(False)
        self.photo_frame.pack(side="left", padx=(0, 14))

        self.photo_lbl = tk.Label(
            self.photo_frame,
            bg=C_META,
            fg=C_MUTED,
            font=("Helvetica", 10)
        )
        self.photo_lbl.pack(expand=True)

        desc_frame = tk.Frame(body, bg=C_CARD)
        desc_frame.pack(side="left", fill="both", expand=True)

        tk.Label(
            desc_frame,
            text="Description",
            font=("Helvetica", 10),
            fg=C_SUB,
            bg=C_CARD
        ).pack(anchor="w")

        self.desc_lbl = tk.Label(
            desc_frame,
            text="",
            font=("Helvetica", 12),
            fg=C_TEXT,
            bg=C_CARD,
            wraplength=280,
            justify="left",
            anchor="nw"
        )
        self.desc_lbl.pack(anchor="w", pady=(4, 0))

        nav = tk.Frame(self.content, bg=C_BG)
        nav.pack(pady=12)

        self.prev_btn = tk.Button(
            nav,
            text="← Prev",
            font=("Helvetica", 11),
            relief="flat",
            bg=C_META,
            fg=C_TEXT,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._prev
        )
        self.prev_btn.pack(side="left", padx=6)

        self.next_btn = tk.Button(
            nav,
            text="Next →",
            font=("Helvetica", 11),
            relief="flat",
            bg=C_META,
            fg=C_TEXT,
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._next
        )
        self.next_btn.pack(side="left", padx=6)

    def _prev(self):
        if self._people:
            self._index = (self._index - 1) % len(self._people)
            self._render()

    def _next(self):
        if self._people:
            self._index = (self._index + 1) % len(self._people)
            self._render()

    def refresh(self, occupants: dict):
        people = sorted(occupants.items(), key=lambda x: int(x[0]))
        old_ids = [p[0] for p in self._people]
        new_ids = [p[0] for p in people]

        if old_ids != new_ids:
            cur = self._people[self._index][0] if self._people else None
            self._people = people
            self._index = new_ids.index(cur) if cur in new_ids else 0
        else:
            self._people = people

        if not self._people:
            self.content.pack_forget()
            self.empty_lbl.pack(expand=True, pady=40)
            return

        self.empty_lbl.pack_forget()
        self.content.pack(fill="both", expand=True)
        self._render()

    def _render(self):
        if not self._people:
            return

        self._index = max(0, min(self._index, len(self._people) - 1))
        pid, desc = self._people[self._index]
        total = len(self._people)

        self.counter_lbl.config(text=f"Person {self._index + 1} of {total}")
        self.id_badge.config(text=f"Global ID: {pid}")
        self.desc_lbl.config(text=desc or "Analyzing…")
        self.prev_btn.config(state="normal" if total > 1 else "disabled")
        self.next_btn.config(state="normal" if total > 1 else "disabled")

        self._photo = None
        self.photo_lbl.config(image="", text="No photo")

        if PIL_OK:
            for path in [
                f"{EVENT_QUEUE}/IN_{pid}.jpg",
                f"{EVENT_QUEUE}/person_{pid}.jpg",
                f"{EVENT_QUEUE}/crop_{pid}.jpg"
            ]:
                if os.path.exists(path):
                    try:
                        img = Image.open(path).convert("RGB")
                        img.thumbnail((110, 150), Image.LANCZOS)
                        self._photo = ImageTk.PhotoImage(img)
                        self.photo_lbl.config(image=self._photo, text="")
                    except Exception:
                        pass
                    break
            else:
                self.photo_lbl.config(text="No photo\nsaved")
        else:
            self.photo_lbl.config(text="Install Pillow\nfor photos")


class DashboardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Door Counter — Live Monitor")
        self.configure(bg=C_BG)
        self.resizable(False, False)
        self._build()
        self._schedule_refresh()

    def _build(self):
        hdr = tk.Frame(self, bg=C_BG)
        hdr.pack(fill="x", padx=16, pady=(16, 10))

        tk.Label(
            hdr,
            text="Door Counter Dashboard",
            font=("Helvetica", 18, "bold"),
            fg=C_TEXT,
            bg=C_BG
        ).pack(side="left")

        self.active_badge = tk.Label(
            hdr,
            text="0 active",
            font=("Helvetica", 10, "bold"),
            bg=C_SOFT_GREEN,
            fg="#27500A",
            padx=10,
            pady=3
        )
        self.active_badge.pack(side="left", padx=10)

        self.clock_lbl = tk.Label(
            hdr,
            text="",
            font=("Helvetica", 10),
            fg=C_MUTED,
            bg=C_BG
        )
        self.clock_lbl.pack(side="right")

        self.big_inside = tk.StringVar(value="0")

        big_box = tk.Frame(
            self,
            bg=C_BIG_BG,
            highlightthickness=1,
            highlightbackground="#C8E6C9",
            bd=0
        )
        big_box.pack(fill="x", padx=16, pady=(0, 12))

        tk.Label(
            big_box,
            text="LIVE PEOPLE INSIDE",
            font=("Helvetica", 11, "bold"),
            fg="#2E7D32",
            bg=C_BIG_BG
        ).pack(anchor="w", padx=16, pady=(12, 2))

        tk.Label(
            big_box,
            textvariable=self.big_inside,
            font=("Helvetica", 38, "bold"),
            fg=C_BIG_TEXT,
            bg=C_BIG_BG
        ).pack(anchor="center", pady=(0, 12))

        summary = tk.Frame(self, bg=C_BG)
        summary.pack(fill="x", padx=16, pady=(0, 12))

        self.g_in = tk.StringVar(value="0")
        self.g_out = tk.StringVar(value="0")
        self.g_net = tk.StringVar(value="0")

        cards = [
            ("🟢 Total in", self.g_in, C_SOFT_GREEN, C_GREEN),
            ("🔵 Total out", self.g_out, C_SOFT_BLUE, C_BLUE),
            ("👥 Inside now", self.g_net, C_SOFT_TEAL, C_TEAL),
        ]

        for col, (title, var, bg_col, val_col) in enumerate(cards):
            card = StatCard(summary, title, var, bg_col, val_col)
            card.grid(row=0, column=col, padx=(0, 8) if col < 2 else 0, sticky="ew")
            summary.columnconfigure(col, weight=1)

        style = ttk.Style()
        style.configure("D.TNotebook", background=C_BG, borderwidth=0)
        style.configure("D.TNotebook.Tab", font=("Helvetica", 11), padding=[14, 6])

        nb = ttk.Notebook(self, style="D.TNotebook")
        nb.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        tab1 = tk.Frame(nb, bg=C_BG)
        nb.add(tab1, text="Door counts")

        section = tk.Frame(tab1, bg=C_BG)
        section.pack(fill="x", pady=(0, 8))

        tk.Label(
            section,
            text="Door Status",
            font=("Helvetica", 13, "bold"),
            fg=C_TEXT,
            bg=C_BG
        ).pack(anchor="w")

        tk.Label(
            section,
            text="Live counters for each entrance",
            font=("Helvetica", 10),
            fg=C_MUTED,
            bg=C_BG
        ).pack(anchor="w")

        self.door_cards = []
        for did, dname in zip(DOOR_IDS, DOOR_NAMES):
            card = DoorCard(tab1, door_id=did, door_name=dname)
            card.pack(fill="x", pady=(0, 10))
            self.door_cards.append(card)

        tab2 = tk.Frame(nb, bg=C_BG)
        nb.add(tab2, text="Who's inside")

        self.occ_tab = OccupantsTab(tab2)
        self.occ_tab.pack(fill="both", expand=True)

        footer = tk.Frame(self, bg=C_BG)
        footer.pack(fill="x", padx=16, pady=(0, 10))

        self.footer_lbl = tk.Label(
            footer,
            text="Auto refresh: every 1 second",
            font=("Helvetica", 9),
            fg=C_MUTED,
            bg=C_BG
        )
        self.footer_lbl.pack(anchor="e")

        self.geometry("560x820")

    def _refresh(self):
        state = read_state()
        occ = read_occupants()
        doors = state.get("doors", {})

        global_in = state.get("global_in", 0)
        global_out = state.get("global_out", 0)
        global_inside = max(0, state.get("global_inside", 0))

        self.g_in.set(str(global_in))
        self.g_out.set(str(global_out))
        self.g_net.set(str(global_inside))
        self.big_inside.set(str(global_inside))

        active = sum(1 for d in doors.values() if d.get("active", False))
        self.active_badge.config(text=f"{active} active")
        self.clock_lbl.config(text=time.strftime("%H:%M:%S"))

        for card in self.door_cards:
            card.refresh(doors.get(card.door_id))

        self.occ_tab.refresh(occ)

        if global_inside > 0:
            self.configure(bg="#F0F7F1")
        else:
            self.configure(bg=C_BG)

    def _schedule_refresh(self):
        self._refresh()
        self.after(REFRESH_MS, self._schedule_refresh)


if __name__ == "__main__":
    app = DashboardApp()
    app.mainloop()
    DashboardApp().mainloop()