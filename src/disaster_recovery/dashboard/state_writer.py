"""
dashboard/state_writer.py

A tiny helper you call from your existing run_multi_camera_system().
It writes the current counts to state.json every time a count changes.
The UI reads this file — that is the only connection between the two.

HOW TO USE — add just these 3 lines to your existing code:

  # At the top of run_multi_camera_system():
  from dashboard.state_writer import StateWriter
  writer = StateWriter(door_id="door1", door_name="Main entrance")

  # After every valid crossing (inside your "3. VALID CROSSING!" block):
  writer.update(total_in, total_out)
"""

import json
import os
import time

STATE_FILE = "dashboard/state.json"


class StateWriter:
    def __init__(self, door_id: str = "door1", door_name: str = "Door 1"):
        self.door_id   = door_id
        self.door_name = door_name
        os.makedirs("dashboard", exist_ok=True)
        # Write initial state so the UI has something to read on startup
        self.update(0, 0)

    def update(self, total_in: int, total_out: int, initial_count: int = 0):
        """
        Call this every time total_in or total_out changes.
        initial_count is added to net_inside (set from the UI).
        """
        # Read existing state so other doors aren't overwritten
        state = _read_state()

        # Get previous value (set from UI)
        prev = state["doors"].get(self.door_id, {})
        initial_count = prev.get("initial_count", 0)

        state["doors"][self.door_id] = {
            "name":          self.door_name,
            "total_in":      total_in,
            "total_out":     total_out,
            "initial_count": initial_count,
            "net_inside":    initial_count + total_in - total_out,
            "active":        True,
            "last_updated":  time.time(),
        }

        # Global totals across all doors
        state["global_in"]      = sum(d["total_in"]  for d in state["doors"].values())
        state["global_out"]     = sum(d["total_out"] for d in state["doors"].values())
        state["global_inside"]  = sum(d["net_inside"] for d in state["doors"].values())
        state["timestamp"]      = time.time()

        _write_state(state)


def _read_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"doors": {}, "global_in": 0, "global_out": 0,
            "global_inside": 0, "timestamp": 0}


def _write_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)