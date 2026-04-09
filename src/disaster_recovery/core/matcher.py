import numpy as np
from scipy.spatial.distance import cosine
import math

class GlobalTracker:
    # We add max_distance_cm (the "small gap" allowed to consider them in the same spot)
    def __init__(self, similarity_threshold=0.5, max_distance_cm=700.0):
        self.identities = {} 
        self.next_global_id = 1
        self.similarity_threshold = similarity_threshold
        self.max_distance_cm = max_distance_cm 

    def compute_similarity(self, feature1, feature2):
        if feature1 is None or feature2 is None:
            return 0.0
        return 1.0 - cosine(feature1, feature2)

    def calculate_distance(self, pos1, pos2):
        """Calculates real-world floor distance in centimeters."""
        if pos1 is None or pos2 is None:
            return float('inf') # Infinite distance if calibration is missing
        return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

    def register_or_match_person(self, cam_id, new_feature, current_floor_pos):
        best_match_id = None
        highest_score = 0.0
        best_distance = 0.0
        best_visual = 0.0

        for global_id, data in self.identities.items():
            if data["cam"] == cam_id:
                continue 

            # 1. Visual Score (What do they look like?)
            saved_feature = data["feature"]
            visual_score = self.compute_similarity(new_feature, saved_feature)

            # 2. Spatial Distance (Where are they standing?)
            saved_pos = data["last_pos"]
            distance = self.calculate_distance(current_floor_pos, saved_pos)

            # 3. The Logic Combo!
            # If the "gap" is smaller than our max distance, they are standing in the exact same physical spot.
            # We give them a +0.20 "Spatial Bonus" to force a match, even if lighting ruined the visual score!
            if distance < self.max_distance_cm:
                spatial_bonus = 0.25 
            else:
                spatial_bonus = 0.0
                # Optional: If distance > 1000cm, you could write `continue` here to instantly reject impossible teleportation!

            total_score = visual_score + spatial_bonus

            if total_score > highest_score:
                highest_score = total_score
                best_match_id = global_id
                best_distance = distance
                best_visual = visual_score

        # Did we beat the threshold?
        if best_match_id is not None and highest_score >= self.similarity_threshold:
            print(f"[MATCH] Global ID {best_match_id} -> Vis: {best_visual:.2f} + Dist Bonus (Gap: {best_distance:.0f}cm) = Total: {highest_score:.2f}")
            
            self.identities[best_match_id]["cam"] = cam_id
            self.identities[best_match_id]["last_pos"] = current_floor_pos
            return best_match_id
        
        else:
            new_id = self.next_global_id
            self.identities[new_id] = {
                "feature": new_feature,
                "last_pos": current_floor_pos,
                "cam": cam_id
            }
            self.next_global_id += 1
            print(f"[NEW PERSON] Global ID {new_id} registered at floor coordinate {current_floor_pos}")
            return new_id

# import math
# import time
# import numpy as np
# from core.reid_model import cosine_similarity

# class GlobalTracker:
#     def __init__(self,
#                  similarity_threshold: float = 0.65,
#                  max_floor_distance_cm: float = 200.0,
#                  time_window_seconds: float = 8.0,
#                  visual_weight: float = 0.80,  # <-- NEW: 80% of the decision is based on clothing
#                  spatial_weight: float = 0.20):# <-- NEW: 20% of the decision is based on position
#         """
#         Args:
#             visual_weight: How much the embedding matters (0.0 to 1.0)
#             spatial_weight: How much the position matters (0.0 to 1.0)
#                             Note: visual_weight + spatial_weight should equal 1.0
#         """
#         self.identities:    dict[int, dict] = {}
#         self.next_global_id = 1
#         self.sim_thresh     = similarity_threshold
#         self.max_dist       = max_floor_distance_cm
#         self.time_window    = time_window_seconds
        
#         # Normalize weights just in case they don't add up to 1.0
#         total_weight = visual_weight + spatial_weight
#         self.w_vis = visual_weight / total_weight
#         self.w_spa = spatial_weight / total_weight

#     def register_or_match_person(self,
#                                   cam_id: str,
#                                   feature: np.ndarray,
#                                   floor_pos: tuple,
#                                   timestamp: float = None) -> int:
        
#         if timestamp is None:
#             timestamp = time.time()

#         if feature is None:
#             return self._register_new(cam_id, feature, floor_pos, timestamp)

#         best_id    = None
#         best_score = -1.0
#         best_vis   = 0.0
#         best_spa   = 0.0
#         best_dist  = 0.0

#         for gid, data in self.identities.items():

#             # ── Gate 1: Time window ───────────────────────────────────────────
#             time_gap = timestamp - data.get("last_seen", 0)
#             if time_gap > self.time_window:
#                 continue

#             if data.get("cam") == cam_id and time_gap < 2.0:
#                 continue

#             # ── 1. Calculate Visual Score (0.0 to 1.0) ────────────────────────
#             saved_feat = data.get("feature")
#             visual_score = cosine_similarity(feature, saved_feat)

#             # ── 2. Calculate Spatial Score (0.0 to 1.0) ───────────────────────
#             saved_pos = data.get("last_pos")
#             spatial_score = 0.0
#             dist = 0.0
            
#             if saved_pos and floor_pos:
#                 dist = self._distance(floor_pos, saved_pos)
                
#                 # Hard reject if it is physically impossible
#                 if dist > self.max_dist:
#                     continue 

#                 # Convert distance into a score. 
#                 # 0cm away = 1.0 score. Max distance away = 0.0 score.
#                 spatial_score = 1.0 - (dist / self.max_dist)

#             # ── 3. Weighted Fusion! ───────────────────────────────────────────
#             # Combine them using your assigned weights
#             total_score = (visual_score * self.w_vis) + (spatial_score * self.w_spa)

#             if total_score > best_score:
#                 best_score = total_score
#                 best_id    = gid
#                 best_vis   = visual_score
#                 best_spa   = spatial_score
#                 best_dist  = dist

#         # ── Decision ──────────────────────────────────────────────────────────
#         if best_id is not None and best_score >= self.sim_thresh:
            
#             self.identities[best_id]["last_pos"]  = floor_pos
#             self.identities[best_id]["cam"]        = cam_id
#             self.identities[best_id]["last_seen"]  = timestamp
            
#             old_feat = self.identities[best_id]["feature"]
#             if old_feat is not None and feature is not None:
#                 blended = 0.7 * old_feat + 0.3 * feature
#                 norm = np.linalg.norm(blended)
#                 self.identities[best_id]["feature"] = blended / norm if norm > 1e-6 else blended

#             print(f"  [MATCH] Global {best_id} | Vis: {best_vis:.2f}(80%) + Spa: {best_spa:.2f}(20%) = Final: {best_score:.2f} (Gap: {best_dist:.0f}cm)")
#             return best_id

#         else:
#             return self._register_new(cam_id, feature, floor_pos, timestamp)

#     def _register_new(self, cam_id, feature, floor_pos, timestamp) -> int:
#         gid = self.next_global_id
#         self.next_global_id += 1
#         self.identities[gid] = {
#             "feature":   feature,
#             "last_pos":  floor_pos,
#             "cam":       cam_id,
#             "last_seen": timestamp,
#             "first_seen": timestamp,
#         }
#         print(f"  [NEW]   Global {gid} registered  cam={cam_id}  floor={floor_pos}")
#         return gid

#     @staticmethod
#     def _distance(pos1: tuple, pos2: tuple) -> float:
#         return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

#     def cleanup_stale(self, current_time: float, max_age: float = 30.0):
#         stale = [gid for gid, d in self.identities.items()
#                  if current_time - d.get("last_seen", 0) > max_age]
#         for gid in stale:
#             del self.identities[gid]

#     def summary(self) -> dict:
#         return {
#             "total_registered": len(self.identities),
#             "cameras": list({d["cam"] for d in self.identities.values()}),
#         }