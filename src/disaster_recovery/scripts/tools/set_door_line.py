import argparse
import sys
import os
import cv2
import numpy as np
import yaml

# Config is resolved from repository root working directory.
CONFIG_PATH = os.path.join("config", "cameras.yaml")

# ── State shared with mouse callback ─────────────────────────────────────────
state = {
    "points": [],       # list of (x, y) — max 2
    "hover":  None,     # current mouse position for live preview
    "saved":  False,
}

# --- RESIZING VARIABLES ---
DISPLAY_SCALE = 0.5  # Scale down to 50% for display
inv_scale = 1.0 / DISPLAY_SCALE

def mouse_callback(event, x, y, flags, param):
    # Convert display coordinates back to original frame coordinates
    orig_x = int(x * inv_scale)
    orig_y = int(y * inv_scale)

    if event == cv2.EVENT_MOUSEMOVE:
        state["hover"] = (orig_x, orig_y)

    elif event == cv2.EVENT_LBUTTONDOWN:
        if len(state["points"]) < 2:
            state["points"].append((orig_x, orig_y))
            label = "A" if len(state["points"]) == 1 else "B"
            print(f"  Point {label} set: ({orig_x}, {orig_y})")
        else:
            print("  Already have 2 points — press R to reset or Enter to save")

    elif event == cv2.EVENT_RBUTTONDOWN:
        if state["points"]:
            removed = state["points"].pop()
            print(f"  Removed point: {removed}")


def draw_overlay(frame: np.ndarray) -> np.ndarray:
    """Draw points, line, and instructions onto frame."""
    vis = frame.copy()
    pts = state["points"]
    hover = state["hover"]

    # ── Instruction panel ────────────────────────────────────────────────────
    h, w = vis.shape[:2]
    panel = vis.copy()
    cv2.rectangle(panel, (0, h - 90), (w, h), (20, 20, 20), -1)
    cv2.addWeighted(panel, 0.6, vis, 0.4, 0, vis)

    instructions = [
        "Left click = place point  |  Right click = undo  |  R = reset",
        "Enter or S = save & exit  |  +/- = next/prev frame  |  Q = quit",
    ]
    for i, line in enumerate(instructions):
        cv2.putText(vis, line, (10, h - 60 + i * 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 200, 200), 1)

    # ── Status ───────────────────────────────────────────────────────────────
    if len(pts) == 0:
        status = "Click point A (first end of the door line)"
        status_col = (80, 200, 255)
    elif len(pts) == 1:
        status = "Click point B (second end of the door line)"
        status_col = (80, 255, 160)
    else:
        status = "Line set!  Press Enter or S to save"
        status_col = (60, 255, 60)

    cv2.putText(vis, status, (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_col, 2)

    # ── Live rubber-band preview ────────────
    if len(pts) == 1 and hover:
        cv2.line(vis, pts[0], hover, (100, 100, 255), 1, cv2.LINE_AA)

    # ── Drawn line ─────────────────────────────────────────
    if len(pts) == 2:
        cv2.line(vis, pts[0], pts[1], (0, 220, 100), 2, cv2.LINE_AA)

        mx = (pts[0][0] + pts[1][0]) // 2
        my = (pts[0][1] + pts[1][1]) // 2
        dx = pts[1][0] - pts[0][0]
        dy = pts[1][1] - pts[0][1]
        length = max(1, int((dx**2 + dy**2) ** 0.5))
        nx, ny = -dy / length, dx / length

        arrow_len = 35
        in_end = (int(mx + nx * arrow_len), int(my + ny * arrow_len))
        cv2.arrowedLine(vis, (mx, my), in_end, (80, 255, 120), 2, tipLength=0.35)
        cv2.putText(vis, "IN", (in_end[0] + 5, in_end[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 255, 120), 2)

        out_end = (int(mx - nx * arrow_len), int(my - ny * arrow_len))
        cv2.arrowedLine(vis, (mx, my), out_end, (80, 160, 255), 2, tipLength=0.35)
        cv2.putText(vis, "OUT", (out_end[0] + 5, out_end[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 160, 255), 2)

    # ── Point markers ────────────────────────────────────────────────────────
    colours = [(80, 180, 255), (80, 255, 160)]
    labels  = ["A", "B"]
    for i, pt in enumerate(pts):
        cv2.circle(vis, pt, 7, colours[i], -1)
        cv2.circle(vis, pt, 7, (255, 255, 255), 1)
        cv2.putText(vis, labels[i], (pt[0] - 5, pt[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 2)

    return vis

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    return {}

def save_line_to_config(cam_id: str, line: list):
    cfg = load_config()
    if "door_lines" not in cfg:
        cfg["door_lines"] = {}

    cfg["door_lines"][cam_id] = line

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)

    print(f"\n  Saved to {CONFIG_PATH}:")
    print(f"    door_lines[{cam_id}] = {line}\n")


def main():
    parser = argparse.ArgumentParser(description="Interactively draw the door counting line")
    parser.add_argument("--video", required=True, help="Path to video file")
    parser.add_argument("--cam", type=str, required=True, help="Camera ID (e.g., cam1, cam2)")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open video: {args.video}")
        sys.exit(1)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_idx = min(30, total - 1)

    def read_frame(idx: int) -> np.ndarray:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, f = cap.read()
        return f if ret else None

    frame = read_frame(frame_idx)
    if frame is None:
        sys.exit(1)

    # ── Load existing line if any ─────────────────────────────────────────────
    existing_cfg = load_config()
    existing_line = existing_cfg.get("door_lines", {}).get(args.cam)
    if existing_line:
        state["points"] = [(existing_line[0], existing_line[1]), (existing_line[2], existing_line[3])]
        print(f"  Loaded existing line for {args.cam}: {existing_line}")

    win_name = f"Set door line — {args.cam}"
    cv2.namedWindow(win_name)
    cv2.setMouseCallback(win_name, mouse_callback)

    while True:
        vis = draw_overlay(frame)
        
        # --- RESIZE FOR DISPLAY ---
        width = int(vis.shape[1] * DISPLAY_SCALE)
        height = int(vis.shape[0] * DISPLAY_SCALE)
        display_frame = cv2.resize(vis, (width, height), interpolation=cv2.INTER_AREA)

        cv2.imshow(win_name, display_frame)
        key = cv2.waitKey(30) & 0xFF

        if key == ord("q"):
            break
        elif key in (13, ord("s")):    # Enter or S
            if len(state["points"]) == 2:
                line = [state["points"][0][0], state["points"][0][1], 
                        state["points"][1][0], state["points"][1][1]]
                save_line_to_config(args.cam, line)
                break
        elif key == ord("r"):
            state["points"] = []
        elif key in (ord("+"), ord("=")): 
            frame_idx = min(frame_idx + 50, total - 1)
            frame = read_frame(frame_idx)
        elif key == ord("-"):             
            frame_idx = max(frame_idx - 50, 0)
            frame = read_frame(frame_idx)

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()