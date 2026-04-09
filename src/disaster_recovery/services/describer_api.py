import os
import time
import glob
import json
from PIL import Image
import google.generativeai as genai

API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=API_KEY)

QUEUE_FOLDER = "event_queue"
# This is the file the Dashboard UI reads from
OCCUPANTS_JSON = "dashboard/occupants.json"

class LiveOccupancyRegistry:
    def __init__(self):
        print("Connecting to Gemini Vision API...")
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        self.active_occupants = {}
        
        # Ensure folders exist
        os.makedirs(QUEUE_FOLDER, exist_ok=True)
        os.makedirs("dashboard", exist_ok=True)
        
        # Clear/Init the JSON file on start
        self.save_to_json()
        print("\n[READY] Describer Service Online. Connected to Dashboard.\n")

    def save_to_json(self):
        """Saves the current inside-building list to a file for the Dashboard UI."""
        try:
            with open(OCCUPANTS_JSON, "w") as f:
                json.dump({"occupants": self.active_occupants}, f, indent=2)
        except Exception as e:
            print(f"Error saving to JSON: {e}")

    def generate_description(self, image_path):
        """Passes the saved crop to the Gemini API."""
        try:
            raw_image = Image.open(image_path).convert('RGB')
            prompt = "Describe the clothing of the person in this image in one short, concise sentence. Focus on colors and clothing types. Do not describe the background."
            
            response = self.model.generate_content([prompt, raw_image])
            return response.text.strip()
        except Exception as e:
            return f"Failed to analyze image: {e}"

    def display_live_dashboard(self):
        """Terminal view (kept for debugging)."""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("==================================================")
        print("          LIVE BUILDING OCCUPANCY REGISTRY        ")
        print("==================================================")
        
        if not self.active_occupants:
            print("  Building is currently empty.")
        else:
            print(f"  Total People Inside: {len(self.active_occupants)}\n")
            for gid, desc in sorted(self.active_occupants.items()):
                print(f"  [ID: {gid}] {desc}")
        print("==================================================\n")

    def run(self):
        while True:
            updated = False

            # 1. Check for OUT events
            out_files = glob.glob(os.path.join(QUEUE_FOLDER, "OUT_*.txt"))
            for out_file in out_files:
                filename = os.path.basename(out_file)
                global_id = filename.replace("OUT_", "").replace(".txt", "")
                
                if global_id in self.active_occupants:
                    del self.active_occupants[global_id]
                    updated = True
                
                os.remove(out_file)

            # 2. Check for IN events
            in_files = glob.glob(os.path.join(QUEUE_FOLDER, "IN_*.jpg"))
            for in_file in in_files:
                filename = os.path.basename(in_file)
                global_id = filename.replace("IN_", "").replace(".jpg", "")
                
                print(f"Analyzing new person: ID {global_id}...")
                description = self.generate_description(in_file)
                
                self.active_occupants[global_id] = description
                updated = True
                
                # Note: We do NOT delete the .jpg immediately 
                # because the Dashboard UI needs it to show the photo!
                # Move it to a permanent subfolder so it doesn't get re-processed
                os.makedirs(f"{QUEUE_FOLDER}/processed", exist_ok=True)
                os.rename(in_file, f"{QUEUE_FOLDER}/person_{global_id}.jpg")

            if updated:
                self.save_to_json()
                self.display_live_dashboard()

            time.sleep(0.5)

if __name__ == "__main__":
    registry = LiveOccupancyRegistry()
    registry.run()