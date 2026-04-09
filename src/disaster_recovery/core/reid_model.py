# import torch
# import torchvision.transforms as T
# from torchvision.models import resnet50, ResNet50_Weights
# import cv2
# from PIL import Image

# class ReIDExtractor:
#     def __init__(self):
#         print("Loading Re-ID Feature Extractor (ResNet50)...")
#         self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
#         # Load pre-trained ResNet50 and remove the final classification layer
#         self.model = resnet50(weights=ResNet50_Weights.DEFAULT)
#         self.model = torch.nn.Sequential(*(list(self.model.children())[:-1]))
#         self.model.to(self.device)
#         self.model.eval() 

#         # Standard Re-ID transforms
#         self.transform = T.Compose([
#             T.Resize((256, 128)),
#             T.ToTensor(),
#             T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
#         ])

#         # Initialize CLAHE for lighting equalization
#         # clipLimit=2.0 prevents over-exposure, tileGridSize=(8,8) balances local shadows
#         self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))

#     def extract_feature(self, crop_img):
#         """
#         Takes a cropped OpenCV image of a person, balances the lighting using CLAHE, 
#         and returns a 1D feature vector.
#         """
#         if crop_img is None or crop_img.size == 0:
#             return None

#         # --- Lighting Pre-processing (CLAHE) ---
#         # 1. Convert BGR to LAB color space (L = Lightness, A/B = Colors)
#         lab = cv2.cvtColor(crop_img, cv2.COLOR_BGR2LAB)
#         l_channel, a_channel, b_channel = cv2.split(lab)
        
#         # 2. Apply CLAHE only to the Lightness channel
#         cl = self.clahe.apply(l_channel)
        
#         # 3. Merge the balanced Lightness back with the original Colors
#         merged_lab = cv2.merge((cl, a_channel, b_channel))
        
#         # 4. Convert back to BGR
#         balanced_img = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)
#         # ---------------------------------------

#         # Convert to RGB for PyTorch processing
#         rgb_img = cv2.cvtColor(balanced_img, cv2.COLOR_BGR2RGB)
#         pil_img = Image.fromarray(rgb_img)

#         # Apply transforms and add batch dimension
#         input_tensor = self.transform(pil_img).unsqueeze(0).to(self.device)

#         # Extract features without calculating gradients
#         with torch.no_grad():
#             feature = self.model(input_tensor)
        
#         return feature.cpu().numpy().flatten()

"""
core/reid_model.py

Correct Re-ID feature extractor using OSNet — a model trained specifically
on person Re-ID datasets (Market-1501, DukeMTMC).

Key differences from the ResNet50 approach:
  - OSNet is trained to distinguish between different people, not classify objects
  - Uses CLAHE lighting normalisation (kept from your version — good idea)
  - Averages embeddings from multiple frames for stability
  - Returns L2-normalised vectors so cosine similarity works correctly
"""

import cv2
import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image


_TRANSFORM = T.Compose([
    T.Resize((256, 128)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406],
                std =[0.229, 0.224, 0.225]),
])


class ReIDExtractor:
    def __init__(self, device: str = "auto"):
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.model = self._load_osnet()

        # CLAHE for lighting normalisation — good idea from your version, kept
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        # Per-track crop buffer: local_key → list of crops
        self._buffers: dict[str, list] = {}

        print(f"[ReID] Ready on {self.device}")

    def _load_osnet(self) -> torch.nn.Module:
        try:
            import torchreid
            model = torchreid.models.build_model(
                name="osnet_x0_25",   # lightweight, fast, good accuracy
                num_classes=1000,
                pretrained=True,      # downloads Market-1501 weights automatically
            )
            model.to(self.device)
            model.eval()
            print("[ReID] OSNet x0_25 loaded (trained on Market-1501)")
            return model
        except ImportError:
            print("[ReID] torchreid not installed — using histogram fallback")
            print("       Install with: pip install torchreid")
            return None
        except Exception as e:
            print(f"[ReID] OSNet load failed: {e} — using histogram fallback")
            return None

    # ── Preprocessing ─────────────────────────────────────────────────────────

    def _preprocess(self, crop: np.ndarray) -> np.ndarray:
        """Apply CLAHE lighting normalisation to a BGR crop."""
        if crop is None or crop.size == 0:
            return None
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_eq = self.clahe.apply(l)
        merged = cv2.merge((l_eq, a, b))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

    def _extract_single(self, crop: np.ndarray) -> np.ndarray | None:
        """Extract embedding from one crop. Returns L2-normalised vector."""
        if crop is None or crop.size == 0:
            return None
        if crop.shape[0] < 32 or crop.shape[1] < 16:
            return None   # too small — unreliable

        balanced = self._preprocess(crop)
        if balanced is None:
            return None

        if self.model is not None:
            return self._deep_extract(balanced)
        else:
            return self._histogram_fallback(balanced)

    def _deep_extract(self, crop: np.ndarray) -> np.ndarray | None:
        try:
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(rgb)
            tensor = _TRANSFORM(pil).unsqueeze(0).to(self.device)
            with torch.no_grad():
                feat = self.model(tensor)
            vec = feat.squeeze().cpu().numpy().astype(np.float32)
            norm = np.linalg.norm(vec)
            return vec / norm if norm > 1e-6 else None
        except Exception as e:
            print(f"[ReID] Extraction error: {e}")
            return None

    def _histogram_fallback(self, crop: np.ndarray) -> np.ndarray:
        """HSV colour histogram — used if OSNet unavailable."""
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        upper = hsv[:int(crop.shape[0] * 0.6), :, :]   # upper body only
        h = cv2.calcHist([upper], [0], None, [36], [0, 180]).flatten()
        s = cv2.calcHist([upper], [1], None, [32], [0, 256]).flatten()
        v = cv2.calcHist([upper], [2], None, [32], [0, 256]).flatten()
        vec = np.concatenate([h, s, v]).astype(np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 1e-6 else vec

    # ── Public API ────────────────────────────────────────────────────────────

    def extract_feature(self, crop: np.ndarray) -> np.ndarray | None:
        """
        Extract a single embedding from one crop.
        Use extract_averaged() when you have multiple frames of the same person.
        """
        return self._extract_single(crop)

    def add_to_buffer(self, track_key: str, crop: np.ndarray, max_size: int = 10):
        """
        Add a crop to a per-track buffer for later averaged extraction.
        track_key should be unique per camera+track, e.g. 'cam0_42'
        """
        if track_key not in self._buffers:
            self._buffers[track_key] = []
        if crop is not None and crop.size > 0:
            self._buffers[track_key].append(crop)
            self._buffers[track_key] = self._buffers[track_key][-max_size:]

    def extract_averaged(self, track_key: str = None,
                         crops: list = None) -> np.ndarray | None:
        """
        Extract and average embeddings from multiple crops.
        Pass either track_key (uses internal buffer) or crops (list of arrays).

        Averaging over multiple frames is much more robust than a single frame
        because individual frames can be blurry, occluded, or poorly lit.
        """
        if crops is None:
            crops = self._buffers.get(track_key, [])

        if len(crops) < 3:
            return None   # not enough frames yet — wait for more

        vectors = [self._extract_single(c) for c in crops]
        vectors = [v for v in vectors if v is not None]

        if not vectors:
            return None

        avg = np.mean(vectors, axis=0).astype(np.float32)
        norm = np.linalg.norm(avg)
        return avg / norm if norm > 1e-6 else None

    def clear_buffer(self, track_key: str):
        self._buffers.pop(track_key, None)

    def clear_all_buffers(self):
        self._buffers.clear()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two L2-normalised vectors.
    Range: 0.0 (completely different) to 1.0 (identical).

    NOTE: Only meaningful if both vectors are from the same model
    (both OSNet or both histogram — never mix them).
    """
    if a is None or b is None:
        return 0.0
    return float(np.clip(np.dot(a, b), 0.0, 1.0))