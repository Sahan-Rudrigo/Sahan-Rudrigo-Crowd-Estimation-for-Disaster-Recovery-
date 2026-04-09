import numpy as np
import math
import json
import os

class PanicDetector:
    def __init__(self, baseline_file="config/panic_baseline.json"):
        self.history = {}          # {track_id: (floor_pos, timestamp)}
        self.normal_speeds = []    
        self.baseline_file = baseline_file
        
        self.mean_speed = 0.0
        self.std_speed = 0.0
        self.panic_threshold = 0.0
        self.is_trained = False

    def update_and_get_speed(self, track_id, floor_pos, current_video_time):
        """Calculates real-world speed in cm/second based on the homography floor map."""
        speed = 0.0
        if track_id in self.history:
            last_pos, last_time = self.history[track_id]
            dt = current_video_time - last_time
            
            # Only calculate if the time gap is reasonable (avoids tracking glitches)
            if 0 < dt < 2.0: 
                dx = floor_pos[0] - last_pos[0]
                dy = floor_pos[1] - last_pos[1]
                dist_cm = math.sqrt(dx**2 + dy**2)
                speed = dist_cm / dt 
                
        self.history[track_id] = (floor_pos, current_video_time)
        return speed

    def record_normal_behavior(self, speed):
        """Builds the Gaussian curve. Filters out standing still or tracking glitches."""
        if 10.0 < speed < 400.0: 
            self.normal_speeds.append(speed)

    def finalize_training(self):
        """Calculates the distribution and saves it to a JSON file."""
        if len(self.normal_speeds) < 50:
            print("[WARNING] Not enough movement data for a highly accurate baseline.")
            if len(self.normal_speeds) == 0:
                self.normal_speeds = [50.0] # Fallback to prevent crashes
            
        self.mean_speed = float(np.mean(self.normal_speeds))
        self.std_speed = float(np.std(self.normal_speeds))
        
        # Panic Threshold = Mean + 3 Standard Deviations (The 99.7% Rule)
        self.panic_threshold = self.mean_speed + (3 * self.std_speed)
        self.is_trained = True
        
        # Ensure config folder exists and save the data
        os.makedirs(os.path.dirname(self.baseline_file), exist_ok=True)
        with open(self.baseline_file, 'w') as f:
            json.dump({
                "mean_speed": self.mean_speed,
                "std_speed": self.std_speed,
                "panic_threshold": self.panic_threshold
            }, f, indent=4)
            
        print("\n" + "="*45)
        print(" [AI] NORMAL BEHAVIOR LEARNING COMPLETE")
        print("="*45)
        print(f" Average Walking Speed: {self.mean_speed:.0f} cm/s")
        print(f" Standard Deviation:    {self.std_speed:.0f} cm/s")
        print(f" 🚨 PANIC THRESHOLD:    > {self.panic_threshold:.0f} cm/s")
        print(f" Saved to: {self.baseline_file}")
        print("="*45 + "\n")

    def load_baseline(self):
        """Loads the saved JSON configuration before running the detector."""
        if os.path.exists(self.baseline_file):
            with open(self.baseline_file, 'r') as f:
                data = json.load(f)
                self.mean_speed = data["mean_speed"]
                self.std_speed = data["std_speed"]
                self.panic_threshold = data["panic_threshold"]
                self.is_trained = True
            print(f"[INFO] Loaded Panic Baseline: Threshold = {self.panic_threshold:.0f} cm/s")
            return True
        else:
            print(f"[ERROR] Baseline file {self.baseline_file} not found. Run training first!")
            return False

    def is_panicking(self, speed):
        """Returns True if the speed breaks the mathematical threshold."""
        if not self.is_trained:
            return False
        return speed > self.panic_threshold