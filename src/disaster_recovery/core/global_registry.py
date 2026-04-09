"""
core/global_registry.py

The central brain of the multi-camera system.

Receives track updates from each camera, matches them across cameras
using three signals combined:
  1. Appearance similarity  (Re-ID embedding cosine similarity)
  2. Time window            (transition time between cam0 → cam1)
  3. Floor distance         (homography-mapped position on shared floor)

Maintains a global person registry and produces deduplicated IN/OUT counts.

For your specific setup:
  cam0 = inside camera  (person exits: walks toward glass door)
  cam1 = outside camera (same person appears seconds later outside)
"""

import time
import numpy as np
from dataclasses import dataclass, field
from collections import defaultdict

from disaster_recovery.core.reid import cosine_similarity


# ── Config defaults (overridden by cameras.yaml values) ──────────────────────
DEFAULT_COSINE_THRESHOLD   = 0.65   # min similarity to consider a Re-ID match
DEFAULT_TIME_WINDOW        = 8.0    # seconds — max gap between cam appearances
DEFAULT_FLOOR_THRESHOLD    = 120.0  # cm — max floor distance to allow match
MIN_CROPS_FOR_EMBEDDING    = 3      # collect at least N crops before trying to match
EMBEDDING_HISTORY          = 10     # how many crops to average per track


@dataclass
class TrackRecord:
    """Stores state for one local camera track."""
    cam_id:        str
    local_id:      int
    global_id:     int | None  = None    # assigned once matched
    embedding:     np.ndarray | None = None
    crop_buffer:   list = field(default_factory=list)  # recent crops for averaging
    last_seen:     float = field(default_factory=time.time)
    last_foot:     tuple | None = None   # last known pixel foot position
    last_floor:    tuple | None = None   # last known floor coord (cm)
    crossed_line:  bool  = False         # has this track crossed the door line?
    direction:     str | None = None     # 'IN' or 'OUT' when crossed


@dataclass
class GlobalPerson:
    """One unique real-world person, possibly seen by multiple cameras."""
    global_id:    int
    first_seen:   float = field(default_factory=time.time)
    last_seen:    float = field(default_factory=time.time)
    cameras_seen: set = field(default_factory=set)
    direction:    str | None = None       # final counted direction
    counted:      bool = False            # has this person been added to totals?
    embedding:    np.ndarray | None = None


class GlobalRegistry:
    def __init__(self,
                 reid_extractor,
                 homography_mapper=None,
                 cosine_threshold: float  = DEFAULT_COSINE_THRESHOLD,
                 time_window: float       = DEFAULT_TIME_WINDOW,
                 floor_threshold: float   = DEFAULT_FLOOR_THRESHOLD):
        """
        Args:
            reid_extractor:    ReIDExtractor instance
            homography_mapper: HomographyMapper instance (optional but recommended)
            cosine_threshold:  min cosine similarity for appearance match
            time_window:       max seconds between camera transitions
            floor_threshold:   max floor distance (cm) for position match
        """
        self.reid        = reid_extractor
        self.mapper      = homography_mapper
        self.cos_thresh  = cosine_threshold
        self.time_win    = time_window
        self.floor_thresh = floor_threshold

        # local track key "cam0_42" → TrackRecord
        self._tracks:  dict[str, TrackRecord] = {}

        # global_id → GlobalPerson
        self._persons: dict[int, GlobalPerson] = {}

        self._next_global_id = 1
        self._count_in  = 0
        self._count_out = 0

        # For logging
        self.events: list[dict] = []

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def count_in(self) -> int:
        return self._count_in

    @property
    def count_out(self) -> int:
        return self._count_out

    # ── Main update call ──────────────────────────────────────────────────────

    def update_track(self,
                     cam_id: str,
                     track: dict,
                     timestamp: float,
                     line_event: dict | None = None,
                     extract_embedding: bool = True):
        """
        Called every frame for every active track on a camera.

        Args:
            cam_id:      'cam0' or 'cam1'
            track:       track dict from CameraTracker.update()
                         must contain: track_id, crop, foot, bbox
            timestamp:   current video time in seconds
            line_event:  crossing event dict from LineCounter, or None
        """
        key = f"{cam_id}_{track['track_id']}"

        # ── Create or update TrackRecord ──────────────────────────────────────
        if key not in self._tracks:
            self._tracks[key] = TrackRecord(
                cam_id=cam_id,
                local_id=track["track_id"],
            )

        rec = self._tracks[key]
        rec.last_seen = timestamp
        rec.last_foot = track["foot"]

        # Update floor position if homography available
        if self.mapper and self.mapper.is_calibrated(cam_id):
            rec.last_floor = self.mapper.map_to_floor(cam_id, track["foot"])

        # Buffer crops for averaged embedding
        if extract_embedding and track["crop"] is not None and track["crop"].size > 0:
            rec.crop_buffer.append(track["crop"])
            rec.crop_buffer = rec.crop_buffer[-EMBEDDING_HISTORY:]

        # Recompute embedding once we have enough crops (only on reid frames)
        if extract_embedding and len(rec.crop_buffer) >= MIN_CROPS_FOR_EMBEDDING:
            new_emb = self.reid.extract_averaged(rec.crop_buffer)
            if new_emb is not None:
                rec.embedding = new_emb

        # ── Handle line crossing event ────────────────────────────────────────
        if line_event and not rec.crossed_line:
            rec.crossed_line = True
            rec.direction = line_event["direction"]

            # Try to match to existing global person or create new one
            global_id = self._match_or_create(rec, timestamp)
            rec.global_id = global_id

            person = self._persons[global_id]
            person.cameras_seen.add(cam_id)
            person.last_seen = timestamp

            # Count only once per global person
            if not person.counted:
                person.direction = rec.direction
                person.counted   = True

                if rec.direction == "IN":
                    self._count_in += 1
                else:
                    self._count_out += 1

                event = {
                    "global_id": global_id,
                    "direction": rec.direction,
                    "cam_id":    cam_id,
                    "local_id":  track["track_id"],
                    "timestamp": timestamp,
                }
                self.events.append(event)
                self._log_event(event)

        elif rec.global_id is None and len(rec.crop_buffer) >= MIN_CROPS_FOR_EMBEDDING:
            # Try a passive match (no crossing yet) to link tracks proactively
            gid = self._find_match(rec, timestamp)
            if gid is not None:
                rec.global_id = gid
                self._persons[gid].cameras_seen.add(cam_id)

    # ── Matching logic ────────────────────────────────────────────────────────

    def _match_or_create(self, rec: TrackRecord, timestamp: float) -> int:
        """Find the best matching global person or create a new one."""
        gid = self._find_match(rec, timestamp)
        if gid is not None:
            return gid

        # No match — this is a new unique person
        gid = self._next_global_id
        self._next_global_id += 1
        self._persons[gid] = GlobalPerson(
            global_id=gid,
            embedding=rec.embedding,
        )
        return gid

    def _find_match(self, rec: TrackRecord, timestamp: float) -> int | None:
        """
        Search existing global persons for a match using three signals.
        Returns global_id if matched, else None.
        """
        if rec.embedding is None:
            return None

        best_gid   = None
        best_score = -1.0

        for gid, person in self._persons.items():
            # Skip if this track already belongs to this global person
            if rec.global_id == gid:
                continue

            # Skip if we've already seen this person on this camera
            # (prevents matching cam0 track to a cam0-only global person
            #  when the track is also cam0 — would be a duplicate)
            if rec.cam_id in person.cameras_seen and len(person.cameras_seen) == 1:
                # Only skip same-camera match if no other cameras involved
                pass   # allow: same camera can re-appear after occlusion

            # ── Signal 1: Time window ─────────────────────────────────────────
            time_gap = abs(timestamp - person.last_seen)
            if time_gap > self.time_win:
                continue   # too far apart in time

            # ── Signal 2: Appearance similarity ──────────────────────────────
            if person.embedding is not None:
                sim = cosine_similarity(rec.embedding, person.embedding)
            else:
                sim = 0.5   # no embedding yet, give neutral score

            if sim < self.cos_thresh:
                continue   # appearance doesn't match

            # ── Signal 3: Floor distance (if available) ───────────────────────
            floor_ok = True
            if self.mapper and rec.last_floor is not None:
                # Find any track from this global person to compare floor position
                for other_key, other_rec in self._tracks.items():
                    if other_rec.global_id == gid and other_rec.last_floor is not None:
                        dist = np.sqrt(
                            (rec.last_floor[0] - other_rec.last_floor[0])**2 +
                            (rec.last_floor[1] - other_rec.last_floor[1])**2
                        )
                        # For cross-camera matches the person has moved — allow large dist
                        # but reject clearly impossible positions (e.g. 500cm away instantly)
                        if dist > self.floor_thresh * 3:
                            floor_ok = False
                        break

            if not floor_ok:
                continue

            # ── Combined score: weighted appearance + time bonus ──────────────
            time_bonus = max(0.0, 1.0 - time_gap / self.time_win) * 0.15
            score = sim + time_bonus

            if score > best_score:
                best_score = score
                best_gid   = gid

        return best_gid

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup_stale_tracks(self, current_timestamp: float, max_age: float = 30.0):
        """
        Remove track records that haven't been seen for max_age seconds.
        Call this periodically (e.g. every 5 seconds).
        """
        stale = [k for k, r in self._tracks.items()
                 if current_timestamp - r.last_seen > max_age]
        for k in stale:
            del self._tracks[k]

    # ── Info / debugging ──────────────────────────────────────────────────────

    def get_active_global_ids(self) -> list[int]:
        return list(self._persons.keys())

    def get_track_global_id(self, cam_id: str, local_id: int) -> int | None:
        key = f"{cam_id}_{local_id}"
        rec = self._tracks.get(key)
        return rec.global_id if rec else None

    def summary(self) -> dict:
        return {
            "count_in":       self._count_in,
            "count_out":      self._count_out,
            "net_inside":     self._count_in - self._count_out,
            "unique_persons": len(self._persons),
            "active_tracks":  len(self._tracks),
        }

    def _log_event(self, event: dict):
        arrow = "→  IN" if event["direction"] == "IN" else "← OUT"
        print(f"  [t={event['timestamp']:.1f}s]  Global ID {event['global_id']}  {arrow}"
              f"  (cam={event['cam_id']} local={event['local_id']})"
              f"  total IN={self._count_in}  OUT={self._count_out}")