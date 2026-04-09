"""
core/homography.py

Loads homography matrices from cameras.yaml and provides a simple
map_to_floor() function used at runtime by the Re-ID matching logic.

Usage:
    from core.homography import HomographyMapper

    mapper = HomographyMapper("config/cameras.yaml")
    floor_pt = mapper.map_to_floor("cam0", foot_pixel=(320, 480))
    # returns (x_cm, y_cm) in real-world floor coordinates
    # or None if this camera has no calibration saved
"""

import os
import cv2
import numpy as np
import yaml


class HomographyMapper:
    def __init__(self, config_path: str = "config/cameras.yaml"):
        self.config_path = config_path
        # cam_id (str) → 3x3 numpy matrix
        self._matrices: dict[str, np.ndarray] = {}
        self._load()

    def _load(self):
        """Load all homography matrices from cameras.yaml."""
        if not os.path.exists(self.config_path):
            print(f"[Homography] Config not found: {self.config_path}")
            return

        with open(self.config_path, "r") as f:
            cfg = yaml.safe_load(f) or {}

        loaded = 0
        for cam in cfg.get("cameras", []):
            cam_id = str(cam.get("id", cam.get("name", "")))
            matrix_data = cam.get("homography_matrix")
            if matrix_data:
                self._matrices[cam_id] = np.array(matrix_data, dtype=np.float64)
                loaded += 1

        print(f"[Homography] Loaded {loaded} calibrated camera(s): {list(self._matrices.keys())}")

    def is_calibrated(self, cam_id: str) -> bool:
        return str(cam_id) in self._matrices

    def map_to_floor(self, cam_id: str, foot_pixel: tuple) -> tuple | None:
        """
        Convert a pixel coordinate (foot point) to real-world floor coordinates.

        Args:
            cam_id:     camera ID string e.g. 'cam0'
            foot_pixel: (x, y) pixel coordinate — use bottom-centre of bounding box

        Returns:
            (x_cm, y_cm) floor coordinate, or None if camera not calibrated
        """
        cam_id = str(cam_id)
        if cam_id not in self._matrices:
            return None

        H = self._matrices[cam_id]
        pt = np.array([[[float(foot_pixel[0]), float(foot_pixel[1])]]], dtype=np.float32)
        result = cv2.perspectiveTransform(pt, H)
        x_cm, y_cm = float(result[0][0][0]), float(result[0][0][1])
        return (x_cm, y_cm)

    def floor_distance(self, cam_id_a: str, foot_a: tuple,
                       cam_id_b: str, foot_b: tuple) -> float | None:
        """
        Compute real-world floor distance (in cm) between two foot points
        from potentially different cameras.

        Returns distance in cm, or None if either camera is not calibrated.
        """
        fa = self.map_to_floor(cam_id_a, foot_a)
        fb = self.map_to_floor(cam_id_b, foot_b)

        if fa is None or fb is None:
            return None

        dist = np.sqrt((fa[0] - fb[0])**2 + (fa[1] - fb[1])**2)
        return float(dist)

    def reload(self):
        """Re-read config file — useful if calibration was updated while running."""
        self._matrices.clear()
        self._load()


def draw_floor_point(frame: np.ndarray, foot_pixel: tuple,
                     floor_coord: tuple | None, colour=(0, 200, 255)) -> np.ndarray:
    """
    Draw the foot point and its mapped floor coordinate on a frame.
    Useful for debugging calibration visually.
    """
    out = frame.copy()
    fx, fy = foot_pixel
    cv2.circle(out, (fx, fy), 6, colour, -1)
    cv2.circle(out, (fx, fy), 6, (255, 255, 255), 1)

    if floor_coord:
        label = f"({floor_coord[0]:.0f}, {floor_coord[1]:.0f}) cm"
    else:
        label = "uncalibrated"

    cv2.putText(out, label, (fx + 8, fy - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 1)
    return out