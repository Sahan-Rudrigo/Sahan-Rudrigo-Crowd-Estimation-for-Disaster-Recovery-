import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from disaster_recovery.services.describer_local import run_multi_camera_system


if __name__ == "__main__":
    run_multi_camera_system()
import cv2
import os
import sys
import time
from ultralytics import YOLO

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- Custom Modules ---
from core.reid_model import ReIDExtractor
from tools.homography import HomographyMapper
from core.matcher import GlobalTracker

def run_multi_camera_system():
    print("Initializing Global Multi-Camera Tracking System...")
    
    # 1. Initialize Core Modules
    reid_extractor = ReIDExtractor()
    mapper = HomographyMapper("config/cameras.yaml")
    
    # similarity_threshold determines how strict the visual matching is
    global_tracker = GlobalTracker(similarity_threshold=0.75)
    
    # 2. Setup Cameras
    camera_ids = ["cam0", "cam1"] 
    caps = {}
    yolo_models = {}
    
    # Translation Dictionary: Maps YOLO's temporary ID to the system's Global ID
    local_to_global = {cam: {} for cam in camera_ids}
    
    # ==========================================
    # --- LINE COUNTER SETUP ---
    # ==========================================
    # Using your exact config lines
    counting_lines = {
        "cam0": ((868, 702), (1770, 908)),
        "cam1": ((1498, 1020), (692, 780))
    }
    
    # Track which side of the line a person is on per-camera
    person_line_states = {cam: {} for cam in camera_ids}
    
    # --- ADVANCED ANTI-DUPLICATE MEMORY ---
    # Format: {global_id: {"state": "IN" or "OUT", "last_cross_time": timestamp}}
    global_counted_history = {} 
    
    # Strict 5-second lock to prevent "Bounding Box Wiggle" multi-counts
    JITTER_COOLDOWN_SECONDS = 5.0 
    
    total_in = 0
    total_out = 0

    # --- NEW: Create the folder for the visual describer images ---
    os.makedirs("event_queue", exist_ok=True)

    def get_line_state(foot_pos, line_pt1, line_pt2):
        """Returns 1 if on one side of the line, -1 if on the other side."""
        dx = line_pt2[0] - line_pt1[0]
        dy = line_pt2[1] - line_pt1[1]
        position = (foot_pos[0] - line_pt1[0]) * dy - (foot_pos[1] - line_pt1[1]) * dx
        return 1 if position > 0 else -1
    # ==========================================
    
    for cam in camera_ids:
        video_path = f"cameras/test_videos/{cam}.mp4"
        caps[cam] = cv2.VideoCapture(video_path)
        
        # Instantiate a separate YOLO tracker for each camera to keep memory clean
        yolo_models[cam] = YOLO("yolov8n.pt") 
        
        if not caps[cam].isOpened():
            print(f"[ERROR] Could not open video for {cam}: {video_path}")
            return

    print("\nSystem Online. Processing Synchronized Video Streams...")

    # ==========================================
    # --- PERFORMANCE OPTIMIZER SETUP ---
    # ==========================================
    FRAME_SKIP = 5  # Process every 5th frame to prevent lag.
    global_frame_count = 0

    # 3. Main Processing Loop
    while True:
        global_frame_count += 1
        frames_read = 0
        current_time = time.time() # Used for the jitter cooldown
        
        for cam in camera_ids:
            success, frame = caps[cam].read()
            if not success:
                continue 
            
            frames_read += 1
            
            # --- FRAME SKIP LOGIC ---
            if global_frame_count % FRAME_SKIP != 0:
                continue
                
            vis_frame = frame.copy()
            
            # Run YOLO Tracking
            results = yolo_models[cam].track(frame, classes=[0], conf=0.5, persist=True, tracker="botsort.yaml", verbose=False)
            
            if results[0].boxes.id is not None:
                boxes = results[0].boxes.xywh.cpu().numpy()
                track_ids = results[0].boxes.id.int().cpu().tolist()
                confs = results[0].boxes.conf.cpu().numpy()
                
                for box, local_id, conf in zip(boxes, track_ids, confs):
                    x_center, y_center, width, height = box
                    x1, y1 = int(x_center - width/2), int(y_center - height/2)
                    x2, y2 = int(x_center + width/2), int(y_center + height/2)
                    
                    foot = (int(x_center), int(y_center + height/2))
                    
                    # Map to the real-world virtual floor
                    floor_pos = mapper.map_to_floor(cam, foot)
                    if floor_pos is None:
                        floor_pos = (0.0, 0.0) 
                        
                    # Check if we already know who this person is
                    global_id = local_to_global[cam].get(local_id)
                    
                    if global_id is None:
                        # ---------------------------------------------------------
                        # UNKNOWN PERSON: Run Quality Gate and Re-ID Extraction
                        # ---------------------------------------------------------
                        if height >= 120 and width >= 60 and conf >= 0.80:
                            x1_c, y1_c = max(0, x1), max(0, y1)
                            x2_c, y2_c = min(frame.shape[1], x2), min(frame.shape[0], y2)
                            person_crop = frame[y1_c:y2_c, x1_c:x2_c]
                            
                            feature = reid_extractor.extract_feature(person_crop)
                            global_id = global_tracker.register_or_match_person(cam, feature, floor_pos)
                            
                            local_to_global[cam][local_id] = global_id
                    else:
                        # ---------------------------------------------------------
                        # KNOWN PERSON: Update their live location on the map
                        # ---------------------------------------------------------
                        if global_id in global_tracker.identities:
                            global_tracker.identities[global_id]["last_pos"] = floor_pos
                            global_tracker.identities[global_id]["cam"] = cam

                    # ==========================================
                    # --- STATE MACHINE LINE CROSSING LOGIC ---
                    # ==========================================
                    if global_id is not None and cam in counting_lines:
                        line_pt1, line_pt2 = counting_lines[cam]
                        current_state = get_line_state(foot, line_pt1, line_pt2)
                        
                        if local_id in person_line_states[cam]:
                            previous_state = person_line_states[cam][local_id]
                            
                            if current_state != previous_state:
                                crossing_direction = "IN" if current_state == 1 else "OUT"
                                last_record = global_counted_history.get(global_id)
                                
                                # 1. JITTER CHECK: Did they just cross a line within the last 5 seconds?
                                if last_record and (current_time - last_record["last_cross_time"] < JITTER_COOLDOWN_SECONDS):
                                    print(f"  [JITTER FILTER] Ignoring rapid {crossing_direction} cross for ID {global_id}.")
                                
                                # 2. DUPLICATE CHECK: Are they already currently in this state globally?
                                elif last_record and last_record["state"] == crossing_direction:
                                    print(f"  [DUPLICATE FILTER] ID {global_id} is already {crossing_direction} (Seen on another cam).")
                                
                                # 3. VALID CROSSING!
                                else:
                                    if crossing_direction == "IN":
                                        total_in += 1
                                        print(f"--> [COUNT IN] Global ID {global_id} entered via {cam}.")
                                        
                                        # --- NEW: Send image to the Describer Service ---
                                        in_crop = frame[max(0, y1):min(frame.shape[0], y2), max(0, x1):min(frame.shape[1], x2)]
                                        cv2.imwrite(f"event_queue/IN_{global_id}.jpg", in_crop)
                                        # ------------------------------------------------

                                    else:
                                        total_out += 1
                                        print(f"<-- [COUNT OUT] Global ID {global_id} exited via {cam}.")
                                        
                                        # --- NEW: Tell the Describer Service to delete them ---
                                        with open(f"event_queue/OUT_{global_id}.txt", "w") as f:
                                            f.write("exited")
                                        # ------------------------------------------------
                                        
                                    # Save their new Global State
                                    global_counted_history[global_id] = {
                                        "state": crossing_direction, 
                                        "last_cross_time": current_time
                                    }
                                    
                        person_line_states[cam][local_id] = current_state
                    # ==========================================

                    # --- Visual Annotations ---
                    if global_id is not None:
                        color = (0, 255, 0) # Green = Identified
                        label = f"GLOBAL ID: {global_id}"
                    else:
                        color = (0, 165, 255) # Orange = Waiting for better view
                        label = f"IDing... ({conf*100:.0f}%)"
                        
                    # Draw Box and Label
                    cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(vis_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                    
                    # Draw Floor Coordinates
                    cv2.circle(vis_frame, foot, 5, (255, 0, 0), -1)
                    cv2.putText(vis_frame, f"({floor_pos[0]:.0f}, {floor_pos[1]:.0f})", (foot[0]+10, foot[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # ==========================================
            # --- UI DRAWING FOR LINE COUNTER ---
            # ==========================================
            if cam in counting_lines:
                pt1, pt2 = counting_lines[cam]
                cv2.line(vis_frame, pt1, pt2, (0, 0, 255), 3)
                
                cv2.rectangle(vis_frame, (10, 10), (250, 90), (0, 0, 0), -1)
                cv2.putText(vis_frame, f"IN: {total_in}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.putText(vis_frame, f"OUT: {total_out}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            # ==========================================

            # Resize and display
            scale = 0.5
            display_frame = cv2.resize(vis_frame, (0,0), fx=scale, fy=scale)
            cv2.imshow(f"{cam} - Global Tracking", display_frame)
            
        if frames_read == 0:
            print("Video streams finished.")
            break
            
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    for cap in caps.values():
        cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_multi_camera_system()