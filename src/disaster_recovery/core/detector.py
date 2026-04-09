"""
core/detector.py

Wraps YOLOv8 to detect only 'person' class (class id 0).
Returns bounding boxes, confidence scores, and cropped person images.
"""

import cv2
import numpy as np
from ultralytics import YOLO


class PersonDetector:
    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.4, device: str = "auto"):
        """
        Args:
            model_path: path to YOLO weights file, e.g. 'yolov8n.pt' or 'models/yolov8m.pt'
            confidence: minimum detection confidence threshold (0.0 - 1.0)
            device: 'auto' selects GPU if available, else CPU. Or pass 'cpu', 'cuda:0'
        """
        if device == "auto":
            import torch
            device = "cuda:0" if torch.cuda.is_available() else "cpu"

        self.model = YOLO(model_path)
        self.confidence = confidence
        self.device = device
        self.person_class_id = 0   # COCO class 0 = person

        print(f"[Detector] Loaded {model_path} on {device}")

    def detect(self, frame: np.ndarray) -> list[dict]:
        """
        Run detection on a single frame.

        Returns list of detections, each a dict:
        {
            'bbox':  [x1, y1, x2, y2],   # pixel coords
            'conf':  float,               # confidence score
            'crop':  np.ndarray,          # cropped person image (for Re-ID)
            'foot':  (cx, y2),            # foot point = bottom centre of bbox
        }
        """
        results = self.model(
            frame,
            classes=[self.person_class_id],
            conf=self.confidence,
            device=self.device,
            verbose=False,
        )

        detections = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])

                # Clamp to frame bounds
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(frame.shape[1], x2)
                y2 = min(frame.shape[0], y2)

                # Skip degenerate boxes
                if x2 <= x1 or y2 <= y1:
                    continue

                crop = frame[y1:y2, x1:x2]
                cx = (x1 + x2) // 2
                foot = (cx, y2)   # bottom centre — used for floor mapping

                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "conf": conf,
                    "crop": crop,
                    "foot": foot,
                })

        return detections


def draw_detections(frame: np.ndarray, detections: list[dict]) -> np.ndarray:
    """Draw raw detection boxes on frame (before tracking). For debugging only."""
    out = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        conf = det["conf"]
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 255), 1)
        cv2.putText(out, f"{conf:.2f}", (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    return out