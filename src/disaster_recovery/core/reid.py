"""
core/reid.py

Extracts appearance feature vectors (embeddings) from person crops
using a lightweight Re-ID model (OSNet via torchreid).

These embeddings are used by the global registry to match the same
person across cam0 (inside) and cam1 (outside).
"""

import cv2
import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image


# ── Transforms matching OSNet training preprocessing ─────────────────────────
_MEAN = [0.485, 0.456, 0.406]
_STD  = [0.229, 0.224, 0.225]

_transform = T.Compose([
    T.Resize((256, 128)),          # OSNet input size: height=256, width=128
    T.ToTensor(),
    T.Normalize(mean=_MEAN, std=_STD),
])


class ReIDExtractor:
    def __init__(self, device: str = "auto"):
        """
        Loads OSNet x0_25 — a lightweight model good enough for
        a constrained door scenario. Downloads weights on first run.
        """
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.model = self._load_model()
        print(f"[ReID] OSNet loaded on {self.device}")

    def _load_model(self) -> torch.nn.Module:
        try:
            import torchreid
            model = torchreid.models.build_model(
                name="osnet_x0_25",
                num_classes=1000,
                pretrained=True,
            )
            model = model.to(self.device)
            model.eval()
            return model
        except Exception as e:
            print(f"[ReID] torchreid failed: {e}")
            print("[ReID] Falling back to simple colour histogram features.")
            return None

    def extract(self, crop: np.ndarray) -> np.ndarray | None:
        """
        Extract a 512-dim feature vector from a person crop (BGR numpy array).

        Returns:
            Normalised float32 numpy array of shape (512,), or None if crop invalid.
        """
        if crop is None or crop.size == 0:
            return None
        if crop.shape[0] < 20 or crop.shape[1] < 10:
            return None   # too small to be reliable

        if self.model is not None:
            return self._deep_extract(crop)
        else:
            return self._histogram_fallback(crop)

    def _deep_extract(self, crop: np.ndarray) -> np.ndarray | None:
        try:
            # BGR → RGB → PIL
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            tensor = _transform(pil).unsqueeze(0).to(self.device)

            with torch.no_grad():
                feat = self.model(tensor)

            vec = feat.squeeze().cpu().numpy().astype(np.float32)
            norm = np.linalg.norm(vec)
            return vec / norm if norm > 0 else vec
        except Exception as e:
            print(f"[ReID] Extraction error: {e}")
            return None

    def _histogram_fallback(self, crop: np.ndarray) -> np.ndarray:
        """
        Simple HSV colour histogram as a fallback when torchreid is unavailable.
        Less accurate but still useful for a controlled indoor/outdoor door scene.
        """
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        # Upper body only (top 60%) — more stable than full body
        h = int(crop.shape[0] * 0.6)
        upper = hsv[:h, :, :]

        hist_h = cv2.calcHist([upper], [0], None, [36], [0, 180]).flatten()
        hist_s = cv2.calcHist([upper], [1], None, [32], [0, 256]).flatten()
        hist_v = cv2.calcHist([upper], [2], None, [32], [0, 256]).flatten()

        vec = np.concatenate([hist_h, hist_s, hist_v]).astype(np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def extract_averaged(self, crops: list[np.ndarray]) -> np.ndarray | None:
        """
        Extract embeddings from multiple crops of the same track and average them.
        This is much more robust than using a single frame.

        Args:
            crops: list of BGR numpy arrays from different frames of the same track

        Returns:
            Averaged, normalised embedding vector.
        """
        vectors = []
        for crop in crops:
            vec = self.extract(crop)
            if vec is not None:
                vectors.append(vec)

        if not vectors:
            return None

        avg = np.mean(vectors, axis=0).astype(np.float32)
        norm = np.linalg.norm(avg)
        return avg / norm if norm > 0 else avg


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two normalised vectors. Range: -1 to 1."""
    if a is None or b is None:
        return 0.0
    return float(np.dot(a, b))