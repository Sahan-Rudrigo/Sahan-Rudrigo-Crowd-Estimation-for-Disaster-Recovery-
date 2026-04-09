import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)


import cv2
import time
from ultralytics import YOLO
from disaster_recovery.tools.homography import HomographyMapper
from disaster_recovery.panic.panic_detector import PanicDetector

def test():
    print("--- STARTING PANIC DETECTION PHASE ---")
    PANIC_VIDEO_PATH = "cameras/test_videos/panic.mp4" 
    CAM_ID = "cam0"

    yolo_model = YOLO("yolov8n.pt")
    mapper = HomographyMapper("config/cameras.yaml")
    
    detector = PanicDetector()
    if not detector.load_baseline():
        return

    cap = cv2.VideoCapture(PANIC_VIDEO_PATH)

    FRAME_SKIP = 1  
    frame_count = 0
    
    # --- ALARM SETTINGS ---
    last_alert_time = 0
    alert_display_until = 0

    while True:
        success, frame = cap.read()
        if not success:
            break
            
        frame_count += 1
        if frame_count % FRAME_SKIP != 0:
            continue

        current_video_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        current_real_time = time.time()
        vis_frame = frame.copy()

        results = yolo_model.track(frame, classes=[0], conf=0.5, persist=True, tracker="botsort.yaml", verbose=False)
        
        panic_count = 0 # How many people are panicking in this specific frame?

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xywh.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            
            for box, track_id in zip(boxes, track_ids):
                x_center, y_center, width, height = box
                x1, y1 = int(x_center - width/2), int(y_center - height/2)
                x2, y2 = int(x_center + width/2), int(y_center + height/2)
                
                foot = (int(x_center), int(y_center + height/2))
                floor_pos = mapper.map_to_floor(CAM_ID, foot)
                
                if floor_pos is not None:
                    speed = detector.update_and_get_speed(track_id, floor_pos, current_video_time)
                    is_panic = detector.is_panicking(speed)
                    
                    if is_panic:
                        panic_count += 1
                        color = (0, 0, 255)
                        label = f"ALERT: ID {track_id} RUNNING ({speed:.0f} cm/s)"
                        
                        # --- TERMINAL OUTPUT ---
                        # Only print once every 0.5 seconds to avoid spamming the console
                        if current_real_time - last_alert_time > 0.5:
                            print(f"[!] PANIC DETECTED: ID {track_id} is moving at {speed:.1f} cm/s")
                            last_alert_time = current_real_time
                            alert_display_until = current_real_time + 2.0 # Show alert on UI for 2 seconds
                        
                        cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 4)
                    else:
                        color = (0, 255, 0)
                        label = f"ID {track_id} ({speed:.0f} cm/s)"
                        cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
                        
                    cv2.putText(vis_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # --- MASS PANIC LOGIC ---
        if panic_count >= 3:
            print("\n🚨🚨🚨 CRITICAL: MASS PANIC EVENT DETECTED! 🚨🚨🚨\n")
            alert_display_until = current_real_time + 3.0 # Longer visual alert

        # --- UI VISUAL ALERT OVERLAY ---
        if current_real_time < alert_display_until:
            # Draw a big red warning banner at the top of the screen
            overlay = vis_frame.copy()
            cv2.rectangle(overlay, (0, 0), (frame.shape[1], 100), (0, 0, 255), -1)
            cv2.addWeighted(overlay, 0.4, vis_frame, 0.6, 0, vis_frame)
            cv2.putText(vis_frame, "!!! PANIC DETECTED !!!", (int(frame.shape[1]/2) - 250, 70), 
                        cv2.FONT_HERSHEY_DUPLEX, 1.5, (255, 255, 255), 3)

        # Scale and Display
        display_frame = cv2.resize(vis_frame, (0,0), fx=0.5, fy=0.5)
        cv2.imshow("Disaster Recovery: Panic Detection", display_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    test()