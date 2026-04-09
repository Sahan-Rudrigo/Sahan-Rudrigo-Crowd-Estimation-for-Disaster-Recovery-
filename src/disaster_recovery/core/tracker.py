import cv2
import numpy as np
from ultralytics import YOLO

class CameraTracker:
    def __init__(self, camera_id: str, model_path: str = "yolov8n.pt", confidence: float = 0.5, device: str = "auto"):
        self.cam_id = camera_id
        self.model = YOLO(model_path)
        self.conf = confidence
        self.track_history = {} # Stores past positions for drawing trails

    def update(self, frame: np.ndarray) -> list:
        """Runs YOLO and returns a clean list of dictionaries for each person."""
        results = self.model.track(frame, classes=[0], conf=self.conf, persist=True, tracker="bytetrack.yaml", verbose=False)
        
        active_tracks = []
        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xywh.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            
            for box, track_id in zip(boxes, track_ids):
                x_center, y_center, width, height = box
                x1, y1 = int(x_center - width/2), int(y_center - height/2)
                x2, y2 = int(x_center + width/2), int(y_center + height/2)
                
                foot = (int(x_center), int(y_center + height/2))
                # --- FIX: Calculate the centre coordinate ---
                centre = (int(x_center), int(y_center))
                
                # Take a crop of the person for Re-ID later
                crop = frame[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
                
                active_tracks.append({
                    "track_id": track_id,
                    "bbox": [x1, y1, x2, y2],
                    "foot": foot,
                    "centre": centre, # --- FIX: Pass the centre coordinate to main.py ---
                    "crop": crop
                })
                
                # Save history for drawing
                if track_id not in self.track_history:
                    self.track_history[track_id] = []
                self.track_history[track_id].append(foot)
                if len(self.track_history[track_id]) > 30: # Keep last 30 frames
                    self.track_history[track_id].pop(0)
                    
        return active_tracks

def draw_tracks(frame: np.ndarray, tracks: list, history: dict) -> np.ndarray:
    """Draws boxes and tracking trails."""
    vis = frame.copy()
    for t in tracks:
        x1, y1, x2, y2 = t["bbox"]
        tid = t["track_id"]
        cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 100, 100), 2)
        
        # Draw trail
        if tid in history and len(history[tid]) > 1:
            pts = np.array(history[tid], np.int32).reshape((-1, 1, 2))
            cv2.polylines(vis, [pts], isClosed=False, color=(255, 100, 100), thickness=2)
    return vis