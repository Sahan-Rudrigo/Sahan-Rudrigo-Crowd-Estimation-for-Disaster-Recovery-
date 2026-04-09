import cv2
import numpy as np

class LineCounter:
    def __init__(self, camera_id: str, line: list):
        self.cam_id = camera_id
        # Line format: [x1, y1, x2, y2]
        self.pt_A = (line[0], line[1])
        self.pt_B = (line[2], line[3])
        self.previous_sides = {}
        self.counted_ids = set()

    def _get_side(self, p):
        """Cross product to find which side of the line a point is on."""
        val = (self.pt_B[0] - self.pt_A[0]) * (p[1] - self.pt_A[1]) - (self.pt_B[1] - self.pt_A[1]) * (p[0] - self.pt_A[0])
        return 1 if val > 0 else -1

    def update(self, tracks: list, timestamp: float) -> list:
        """Checks if any tracks crossed the line. Returns a list of events."""
        events = []
        for t in tracks:
            tid = t["track_id"]
            foot = t["foot"]
            
            current_side = self._get_side(foot)
            
            if tid in self.previous_sides:
                prev_side = self.previous_sides[tid]
                
                # If side changed, they crossed!
                if current_side != prev_side and tid not in self.counted_ids:
                    direction = "IN" if current_side > 0 else "OUT"
                    self.counted_ids.add(tid)
                    events.append({
                        "track_id": tid,
                        "direction": direction,
                        "timestamp": timestamp
                    })
                    
            self.previous_sides[tid] = current_side
            
        return events

    def reset_counts(self):
        self.counted_ids.clear()

def draw_line_counter(frame: np.ndarray, counter: LineCounter, recent_events: list) -> np.ndarray:
    vis = frame.copy()
    cv2.line(vis, counter.pt_A, counter.pt_B, (0, 255, 0), 3)
    cv2.putText(vis, "ENTRY LINE", (counter.pt_A[0], counter.pt_A[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return vis