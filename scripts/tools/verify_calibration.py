import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from disaster_recovery.scripts.tools.verify_calibration import main


if __name__ == "__main__":
    main()
import argparse
import sys
import os
import cv2
import yaml
import numpy as np
from ultralytics import YOLO

# Add the project root to the path so we can import core.homography
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from tools.homography import HomographyMapper

DISPLAY_SCALE = 0.5

def main():
    parser = argparse.ArgumentParser(description="Verify homography calibration visually")
    parser.add_argument("--video", required=True)
    parser.add_argument("--cam",   required=True)
    parser.add_argument("--model", default="yolov8n.pt")
    args = parser.parse_args()

    # --- 1. Load YOLO (Directly, like in main.py) ---
    print(f"Loading YOLO model: {args.model}")
    model = YOLO(args.model)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open: {args.video}")
        sys.exit(1)

    # --- 2. Initialize the Mapper ---
    config_path = os.path.join(PROJECT_ROOT, "config", "cameras.yaml")
    mapper  = HomographyMapper(config_path)

    if not mapper.is_calibrated(args.cam):
        print(f"[ERROR] Camera '{args.cam}' has no calibration.")
        print(f"  Run: python scripts/tools/calibrate.py --video {args.video} --cam {args.cam}")
        sys.exit(1)

    print(f"\n[Verify] Camera: {args.cam}")
    print("  Floor coords displayed at each person's foot position.")
    print("  Press Q to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # --- 3. Run YOLO Tracking ---
        # conf=0.5 ensures we only track confident human detections
        results = model.track(frame, classes=[0], conf=0.5, persist=True, tracker="bytetrack.yaml", verbose=False)
        
        vis = frame.copy()

        # If YOLO found people and assigned IDs
        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xywh.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()

            for box, track_id in zip(boxes, track_ids):
                # Calculate bounding box coordinates
                x_center, y_center, width, height = box
                x1 = int(x_center - (width / 2))
                y1 = int(y_center - (height / 2))
                x2 = int(x_center + (width / 2))
                y2 = int(y_center + (height / 2))
                
                # The "foot" coordinate (bottom center)
                foot_x, foot_y = int(x_center), int(y_center + (height / 2))
                foot = (foot_x, foot_y)

                # Draw bounding box
                cv2.rectangle(vis, (x1, y1), (x2, y2), (100, 100, 255), 2)
                
                # Track ID
                cv2.putText(vis, f"ID {track_id}", (x1, y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 255), 2)

                # --- 4. MAP TO FLOOR AND DRAW ---
                floor_coord = mapper.map_to_floor(args.cam, foot)
                
                # Draw the foot dot
                cv2.circle(vis, foot, 6, (0, 200, 255), -1)
                cv2.circle(vis, foot, 6, (255, 255, 255), 1)

                # Draw the real-world cm coordinates next to the foot
                if floor_coord:
                    label = f"({floor_coord[0]:.0f}, {floor_coord[1]:.0f}) cm"
                else:
                    label = "uncalibrated"

                cv2.putText(vis, label, (foot_x + 8, foot_y - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 2)

        # --- 5. Draw the 4 original calibration points (Yellow Rings) ---
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        
        for cam_entry in cfg.get("cameras", []):
            if str(cam_entry.get("id", cam_entry.get("name", ""))) == args.cam:
                for i, (img_pt, fl_pt) in enumerate(zip(
                    cam_entry.get("homography_points_image", []),
                    cam_entry.get("homography_points_floor", [])
                )):
                    px, py = int(img_pt[0]), int(img_pt[1])
                    cv2.circle(vis, (px, py), 8, (0, 255, 255), 2)
                    cv2.putText(vis, f"P{i+1}({fl_pt[0]:.0f},{fl_pt[1]:.0f})",
                                (px + 10, py - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

        # UI text
        cv2.putText(vis, f"Cam: {args.cam}  |  Q=quit",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

        # --- 6. Resize and Display ---
        dw = int(vis.shape[1] * DISPLAY_SCALE)
        dh = int(vis.shape[0] * DISPLAY_SCALE)
        cv2.imshow(f"Calibration verify — {args.cam}", cv2.resize(vis, (dw, dh)))

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()