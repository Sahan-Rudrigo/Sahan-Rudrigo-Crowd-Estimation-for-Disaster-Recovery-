import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from disaster_recovery.scripts.tools.calibrate import main


if __name__ == "__main__":
    main()
import argparse
import sys
import os
import cv2
import numpy as np
import yaml
import math

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH  = os.path.join(PROJECT_ROOT, "config", "cameras.yaml")

DISPLAY_SCALE = 0.5
NUM_POINTS    = 4

POINT_COLOURS = [
    (80,  180, 255),   # blue
    (80,  255, 160),   # green
    (255, 160,  80),   # orange
    (220,  80, 220),   # purple
]
POINT_LABELS = ["P1", "P2", "P3", "P4"]

# ── Shared state ──────────────────────────────────────────────────────────────
state = {
    "points": [],   # list of (orig_x, orig_y) in full-res frame coords
    "hover":  None,
}

def get_parallel_point(p1, p2, p3, hover_point):
    """
    Given line segment p1->p2, and a starting point p3,
    projects the hover_point onto the line passing through p3 that is parallel to p1->p2.
    """
    # Vector of the first line
    v_line = np.array([p2[0] - p1[0], p2[1] - p1[1]], dtype=float)
    length = np.linalg.norm(v_line)
    
    # If points 1 and 2 are identical (shouldn't happen, but safe guard)
    if length == 0: return hover_point
    
    # Normalize the direction vector
    u_line = v_line / length
    
    # Vector from p3 to hover point
    v_hover = np.array([hover_point[0] - p3[0], hover_point[1] - p3[1]], dtype=float)
    
    # Dot product gives the projection length along the parallel line
    proj_length = np.dot(v_hover, u_line)
    
    # Calculate the constrained coordinates
    constrained_x = p3[0] + proj_length * u_line[0]
    constrained_y = p3[1] + proj_length * u_line[1]
    
    return (int(constrained_x), int(constrained_y))

def mouse_callback(event, x, y, flags, param):
    inv = 1.0 / DISPLAY_SCALE
    ox, oy = int(x * inv), int(y * inv)

    if event == cv2.EVENT_MOUSEMOVE:
        # If we have 3 points, constrain the hover point for the 4th
        if len(state["points"]) == 3:
            p1, p2, p3 = state["points"][0], state["points"][1], state["points"][2]
            state["hover"] = get_parallel_point(p1, p2, p3, (ox, oy))
        else:
            state["hover"] = (ox, oy)

    elif event == cv2.EVENT_LBUTTONDOWN:
        if len(state["points"]) < NUM_POINTS:
            # If placing the 4th point, use the constrained hover coordinates
            if len(state["points"]) == 3:
                p1, p2, p3 = state["points"][0], state["points"][1], state["points"][2]
                final_pt = get_parallel_point(p1, p2, p3, (ox, oy))
                state["points"].append(final_pt)
                idx = len(state["points"])
                print(f"  {POINT_LABELS[idx - 1]} set (CONSTRAINED): {final_pt}")
            else:
                state["points"].append((ox, oy))
                idx = len(state["points"])
                print(f"  {POINT_LABELS[idx - 1]} set: ({ox}, {oy})")
            
            if len(state["points"]) == NUM_POINTS:
                print(f"\n  All {NUM_POINTS} points placed.")
                print(f"  Press Enter to enter real-world coordinates, or R to reset.\n")
        else:
            print(f"  Already have {NUM_POINTS} points — press Enter or R to reset")

    elif event == cv2.EVENT_RBUTTONDOWN:
        if state["points"]:
            removed = state["points"].pop()
            print(f"  Removed {POINT_LABELS[len(state['points'])]}: {removed}")


def draw_overlay(frame: np.ndarray, cam_id: str, frame_idx: int, total: int) -> np.ndarray:
    vis = frame.copy()
    pts = state["points"]
    hover = state["hover"]
    h, w = vis.shape[:2]

    # ── Instruction panel at bottom ───────────────────────────────────────────
    panel = vis.copy()
    cv2.rectangle(panel, (0, h - 95), (w, h), (20, 20, 20), -1)
    cv2.addWeighted(panel, 0.6, vis, 0.4, 0, vis)
    for i, line in enumerate([
        "Left click = place point  |  Right click = undo  |  R = reset",
        "Enter / S = confirm & enter real-world coords  |  +/- = change frame  |  Q = quit",
    ]):
        cv2.putText(vis, line, (10, h - 62 + i * 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    # ── Status ────────────────────────────────────────────────────────────────
    remaining = NUM_POINTS - len(pts)
    if remaining > 0:
        status_msg = f"Click {POINT_LABELS[len(pts)]}  ({remaining} remaining)"
        if len(pts) == 3:
            status_msg += " (Constrained Parallel to P1-P2)"
        status = status_msg
        status_col = (80, 200, 255)
    else:
        status = "All points set — press Enter to continue"
        status_col = (60, 255, 60)
    cv2.putText(vis, status, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_col, 2)

    # Frame info
    cv2.putText(vis, f"Camera: {cam_id}   Frame {frame_idx}/{total}  (+/- to navigate)",
                (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (160, 160, 160), 1)

    # ── Draw lines connecting placed points ────────────────────────────────
    if len(pts) >= 2:
        cv2.line(vis, pts[0], pts[1], (180, 180, 180), 2, cv2.LINE_AA) # Base Line P1-P2
    if len(pts) >= 4:
        cv2.line(vis, pts[2], pts[3], (180, 180, 180), 2, cv2.LINE_AA) # Parallel Line P3-P4
        cv2.line(vis, pts[1], pts[2], (100, 100, 100), 1, cv2.LINE_AA) # Connect side
        cv2.line(vis, pts[3], pts[0], (100, 100, 100), 1, cv2.LINE_AA) # Connect side

    # ── Rubber-band line and parallel guide ──────────────────────────
    if 0 < len(pts) < NUM_POINTS and hover:
        if len(pts) == 1:
            cv2.line(vis, pts[0], hover, (120, 120, 255), 1, cv2.LINE_AA)
        elif len(pts) == 2:
             pass # Don't draw a line from P2 to hover, wait for P3 click
        elif len(pts) == 3:
            # Draw an infinite guide line showing the parallel path
            p1, p2, p3 = pts[0], pts[1], pts[2]
            v_line = np.array([p2[0] - p1[0], p2[1] - p1[1]], dtype=float)
            if np.linalg.norm(v_line) > 0:
                u_line = v_line / np.linalg.norm(v_line)
                # Draw a long guide line passing through P3
                guide_start = (int(p3[0] - u_line[0]*3000), int(p3[1] - u_line[1]*3000))
                guide_end = (int(p3[0] + u_line[0]*3000), int(p3[1] + u_line[1]*3000))
                cv2.line(vis, guide_start, guide_end, (50, 50, 50), 1, cv2.LINE_AA)
            
            # Draw the actual rubber band from P3 to constrained hover
            cv2.line(vis, pts[2], hover, (120, 255, 120), 2, cv2.LINE_AA)

    # ── Point markers ─────────────────────────────────────────────────────
    for i, pt in enumerate(pts):
        col = POINT_COLOURS[i]
        cv2.circle(vis, pt, 8, col, -1)
        cv2.circle(vis, pt, 8, (255, 255, 255), 1)
        cv2.putText(vis, POINT_LABELS[i], (pt[0] + 11, pt[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
        cv2.putText(vis, f"({pt[0]},{pt[1]})", (pt[0] + 11, pt[1] + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1)

    return vis


def ask_real_world_coords(image_points: list) -> list:
    print("\n" + "=" * 60)
    print("  Enter real-world floor coordinates for each point.")
    print("  Use centimetres. Pick one corner as (0, 0).")
    print("=" * 60)
    print("\n  Example — 4 floor tile corners forming a 30x30 cm square:")
    print("    P1 = (0, 0)    P2 = (30, 0)    P3 = (30, 30)    P4 = (0, 30)")
    print()

    floor_points = []
    for i, img_pt in enumerate(image_points):
        col_name = ["blue", "green", "orange", "purple"][i]
        print(f"  {POINT_LABELS[i]} ({col_name} dot) — image pixel: {img_pt}")
        while True:
            try:
                raw = input(f"    Real-world coords  x_cm, y_cm: ").strip()
                parts = raw.replace(",", " ").split()
                if len(parts) != 2:
                    raise ValueError
                x_cm, y_cm = float(parts[0]), float(parts[1])
                floor_points.append([x_cm, y_cm])
                print(f"    → Saved: ({x_cm}, {y_cm}) cm\n")
                break
            except (ValueError, KeyboardInterrupt):
                print("    Invalid input — enter two numbers separated by comma or space")

    return floor_points

def compute_homography(image_points: list, floor_points: list) -> np.ndarray:
    src = np.array(image_points, dtype=np.float32)
    dst = np.array(floor_points,  dtype=np.float32)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    inliers = int(mask.sum()) if mask is not None else 0
    print(f"\n  Homography computed — {inliers}/{len(image_points)} inliers (RANSAC)")
    return H

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    return {}

def save_calibration(cam_id: str, image_points: list, floor_points: list, H: np.ndarray):
    cfg = load_config()
    if "cameras" not in cfg:
        cfg["cameras"] = []

    cam_entry = next((c for c in cfg["cameras"] if str(c.get("id", "")) == str(cam_id)
                      or c.get("name", "") == cam_id), None)
    if cam_entry is None:
        cam_entry = {"id": cam_id, "name": cam_id}
        cfg["cameras"].append(cam_entry)

    cam_entry["homography_points_image"] = image_points
    cam_entry["homography_points_floor"]  = floor_points
    cam_entry["homography_matrix"]        = H.tolist()

    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)

    print(f"\n  Saved calibration for {cam_id} → {CONFIG_PATH}")
    print(f"  Homography matrix saved (3x3)\n")

def verify_homography(H: np.ndarray, image_points: list, floor_points: list):
    print("  Reprojection check (image point → mapped floor vs expected floor):")
    total_err = 0.0
    for i, (img_pt, fl_pt) in enumerate(zip(image_points, floor_points)):
        src = np.array([[[img_pt[0], img_pt[1]]]], dtype=np.float32)
        dst = cv2.perspectiveTransform(src, H)[0][0]
        err = np.sqrt((dst[0] - fl_pt[0])**2 + (dst[1] - fl_pt[1])**2)
        total_err += err
        status = "OK" if err < 5.0 else "WARN"
        print(f"    {POINT_LABELS[i]}: mapped=({dst[0]:.1f}, {dst[1]:.1f}) cm  "
              f"expected=({fl_pt[0]:.1f}, {fl_pt[1]:.1f}) cm  "
              f"error={err:.2f} cm  [{status}]")
    print(f"  Mean error: {total_err / len(image_points):.2f} cm")

def main():
    parser = argparse.ArgumentParser(description="Camera homography calibration tool")
    parser.add_argument("--video",  required=True, help="Path to video file for this camera")
    parser.add_argument("--cam",    required=True, help="Camera ID string, e.g. cam0, cam1")
    parser.add_argument("--frame",  type=int, default=60, help="Starting frame number (default: 60)")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open: {args.video}")
        sys.exit(1)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_idx = min(args.frame, total - 1)

    def read_frame(idx):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, f = cap.read()
        return f if ret else None

    frame = read_frame(frame_idx)
    if frame is None:
        sys.exit(1)

    h_orig, w_orig = frame.shape[:2]
    
    existing = load_config()
    for cam_entry in existing.get("cameras", []):
        if str(cam_entry.get("id", "")) == args.cam or cam_entry.get("name") == args.cam:
            pts = cam_entry.get("homography_points_image", [])
            if pts:
                state["points"] = [(int(p[0]), int(p[1])) for p in pts]
            break

    win = f"Calibrate — {args.cam}"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, mouse_callback)

    confirmed = False
    while True:
        vis = draw_overlay(frame, args.cam, frame_idx, total)
        dw = int(vis.shape[1] * DISPLAY_SCALE)
        dh = int(vis.shape[0] * DISPLAY_SCALE)
        cv2.imshow(win, cv2.resize(vis, (dw, dh), interpolation=cv2.INTER_AREA))

        key = cv2.waitKey(30) & 0xFF

        if key == ord("q"): break
        elif key in (13, ord("s")):
            if len(state["points"]) == NUM_POINTS:
                confirmed = True
                break
        elif key == ord("r"): state["points"] = []
        elif key in (ord("+"), ord("=")):
            frame_idx = min(frame_idx + 50, total - 1)
            frame = read_frame(frame_idx)
        elif key == ord("-"):
            frame_idx = max(frame_idx - 50, 0)
            frame = read_frame(frame_idx)

    cap.release()
    cv2.destroyAllWindows()

    if not confirmed: return

    image_points = [[p[0], p[1]] for p in state["points"]]
    floor_points  = ask_real_world_coords(image_points)

    H = compute_homography(image_points, floor_points)
    verify_homography(H, image_points, floor_points)
    save_calibration(args.cam, image_points, floor_points, H)

if __name__ == "__main__":
    main()