import cv2
from ultralytics import YOLO
from disaster_recovery.tools.homography import HomographyMapper
from disaster_recovery.panic.panic_detector import PanicDetector

def train():
    print("--- STARTING BEHAVIOR LEARNING PHASE ---")
    NORMAL_VIDEO_PATH = "cameras/test_videos/cam3.mp4" 
    CAM_ID = "cam0"

    yolo_model = YOLO("yolov8n.pt")
    mapper = HomographyMapper("config/cameras.yaml")
    detector = PanicDetector()

    cap = cv2.VideoCapture(NORMAL_VIDEO_PATH)

    # --- PERFORMANCE OPTIMIZER ---
    FRAME_SKIP = 1  # Process only 1 out of every 4 frames
    frame_count = 0

    while True:
        success, frame = cap.read()
        if not success:
            break
        
        frame_count += 1
        
        # SKIP LOGIC: Only proceed if it's the 4th frame
        if frame_count % FRAME_SKIP != 0:
            continue

        # Get the actual time of the video frame
        current_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0

        # Run YOLO Tracking
        results = yolo_model.track(frame, classes=[0], conf=0.5, persist=True, tracker="botsort.yaml", verbose=False)
        
        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xywh.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            
            for box, track_id in zip(boxes, track_ids):
                x_center, y_center, width, height = box
                foot = (int(x_center), int(y_center + height/2))
                
                floor_pos = mapper.map_to_floor(CAM_ID, foot)
                if floor_pos is not None:
                    # 1. Calculate Speed (cm/s)
                    speed = detector.update_and_get_speed(track_id, floor_pos, current_time)
                    
                    # 2. Record it for the distribution curve
                    detector.record_normal_behavior(speed)
                    
        # Visuals
        display_frame = cv2.resize(frame, (0,0), fx=0.5, fy=0.5)
        cv2.putText(display_frame, f"LEARNING NORMAL BEHAVIOR)", 
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        cv2.imshow("Training Phase", display_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # 3. Save the math (Mean and Std Dev) to JSON
    detector.finalize_training()
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    train()