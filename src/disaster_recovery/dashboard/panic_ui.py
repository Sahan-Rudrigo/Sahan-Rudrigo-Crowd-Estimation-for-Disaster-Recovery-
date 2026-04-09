# """
# dashboard/panic_ui.py

# Panic Detection UI — two phases in one window:

#   LEARN phase:
#     - Load a normal behaviour video
#     - Video plays in the UI window
#     - Live speed histogram builds up as people walk
#     - "Finalize Learning" button saves the baseline to config/panic_baseline.json

#   TEST phase:
#     - Load a panic/test video
#     - Video plays with real-time panic detection overlay
#     - Red bounding boxes + banner for panicking persons
#     - Live stats: people tracked, panic count, threshold

# Run:
#     python dashboard/panic_ui.py
# """

# import tkinter as tk
# from tkinter import filedialog, messagebox
# import threading
# import time
# import os
# import sys
# import json
# import math
# import cv2
# import numpy as np
# from PIL import Image, ImageTk

# PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# if PROJECT_ROOT not in sys.path:
#     sys.path.insert(0, PROJECT_ROOT)

# from ultralytics import YOLO
# from tools.homography import HomographyMapper
# from panic.panic_detector import PanicDetector

# BASELINE_FILE = "config/panic_baseline.json"
# CONFIG_PATH   = "config/cameras.yaml"
# FRAME_SKIP    = 2

# C_BG    = "#F5F5F3"; C_CARD  = "#FFFFFF"; C_TEXT  = "#1A1A18"
# C_MUTED = "#888780"; C_META  = "#F1EFE8"; C_SUB   = "#5F5E5A"
# C_GREEN = "#3B6D11"; C_RED   = "#A32D2D"; C_BLUE  = "#185FA5"
# C_AMBER = "#854F0B"


# class PanicUI(tk.Tk):
#     def __init__(self):
#         super().__init__()
#         self.title("Panic Detection System")
#         self.configure(bg=C_BG)
#         self.resizable(False, False)

#         # Shared state
#         self._stop_flag   = threading.Event()
#         self._thread      = None
#         self._photo_ref   = None   # keep ImageTk reference alive

#         # ML objects (lazy loaded)
#         self._yolo    = None
#         self._mapper  = None
#         self._detector = PanicDetector(BASELINE_FILE)

#         self._build()
#         self._check_baseline()

#     # ── UI construction ───────────────────────────────────────────────────────

#     def _build(self):
#         # Header
#         hdr = tk.Frame(self, bg=C_BG)
#         hdr.pack(fill="x", padx=16, pady=(16, 6))
#         tk.Label(hdr, text="Panic detection",
#                  font=("Helvetica", 16, "bold"), fg=C_TEXT, bg=C_BG).pack(side="left")
#         self.baseline_badge = tk.Label(hdr, text="no baseline",
#                                        font=("Helvetica", 10),
#                                        bg="#FCEBEB", fg="#A32D2D", padx=8, pady=2)
#         self.baseline_badge.pack(side="left", padx=10)

#         # Video canvas
#         canvas_frame = tk.Frame(self, bg="#1A1A18",
#                                 highlightthickness=1, highlightbackground="#D3D1C7")
#         canvas_frame.pack(padx=16, pady=(0, 10))
#         self.canvas = tk.Label(canvas_frame, bg="#1A1A18",
#                                width=640, height=360)
#         self.canvas.pack()
#         self._show_placeholder("No video loaded")

#         # Stats row
#         stats = tk.Frame(self, bg=C_BG)
#         stats.pack(fill="x", padx=16, pady=(0, 10))
#         self.stat_vars = {}
#         for label, key, col, c in [
#             ("Threshold",      "threshold",  C_AMBER, 0),
#             ("Tracked people", "tracked",    C_BLUE,  1),
#             ("Panicking now",  "panicking",  C_RED,   2),
#             ("Total alerts",   "total_alerts", C_RED, 3),
#         ]:
#             cell = tk.Frame(stats, bg=C_META, padx=10, pady=8)
#             cell.grid(row=0, column=c, padx=(0,8) if c<3 else 0, sticky="ew")
#             stats.columnconfigure(c, weight=1)
#             tk.Label(cell, text=label, font=("Helvetica", 10),
#                      fg=C_SUB, bg=C_META).pack(anchor="w")
#             v = tk.StringVar(value="—")
#             self.stat_vars[key] = v
#             tk.Label(cell, textvariable=v, font=("Helvetica", 18, "bold"),
#                      fg=col, bg=C_META).pack(anchor="w")

#         # Log box
#         log_frame = tk.Frame(self, bg=C_BG)
#         log_frame.pack(fill="x", padx=16, pady=(0, 10))
#         tk.Label(log_frame, text="Event log",
#                  font=("Helvetica", 11, "bold"), fg=C_TEXT, bg=C_BG).pack(anchor="w")
#         self.log_box = tk.Text(log_frame, height=5, font=("Courier", 10),
#                                bg="#1A1A18", fg="#E0E0E0",
#                                relief="flat", state="disabled",
#                                highlightthickness=1, highlightbackground="#D3D1C7")
#         self.log_box.pack(fill="x")
#         # Tag colours
#         self.log_box.tag_config("alert",  foreground="#FF6B6B")
#         self.log_box.tag_config("info",   foreground="#7EC8E3")
#         self.log_box.tag_config("ok",     foreground="#90EE90")
#         self.log_box.tag_config("warn",   foreground="#FFD700")

#         # Button row
#         btn_row = tk.Frame(self, bg=C_BG)
#         btn_row.pack(fill="x", padx=16, pady=(0, 16))

#         self.learn_btn = tk.Button(
#             btn_row, text="Learn normal behaviour",
#             font=("Helvetica", 11), relief="flat",
#             bg="#EAF3DE", fg=C_GREEN, padx=14, pady=7,
#             cursor="hand2", command=self._start_learn)
#         self.learn_btn.pack(side="left", padx=(0, 8))

#         self.test_btn = tk.Button(
#             btn_row, text="Test panic detection",
#             font=("Helvetica", 11), relief="flat",
#             bg="#FCEBEB", fg=C_RED, padx=14, pady=7,
#             cursor="hand2", command=self._start_test)
#         self.test_btn.pack(side="left", padx=(0, 8))

#         self.stop_btn = tk.Button(
#             btn_row, text="Stop",
#             font=("Helvetica", 11), relief="flat",
#             bg=C_META, fg=C_TEXT, padx=14, pady=7,
#             cursor="hand2", state="disabled",
#             command=self._stop)
#         self.stop_btn.pack(side="left")

#         self.status_lbl = tk.Label(btn_row, text="Ready",
#                                    font=("Helvetica", 10), fg=C_MUTED, bg=C_BG)
#         self.status_lbl.pack(side="right")

#         self.geometry("690x700")

#     # ── Helpers ───────────────────────────────────────────────────────────────

#     def _show_placeholder(self, text: str):
#         img = np.zeros((360, 640, 3), dtype=np.uint8)
#         cv2.putText(img, text, (180, 190),
#                     cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 80, 80), 2)
#         self._update_canvas(img)

#     def _update_canvas(self, frame: np.ndarray):
#         """Convert OpenCV frame to Tkinter image and show on canvas."""
#         rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#         h, w = rgb.shape[:2]
#         # Fit to 640x360
#         scale = min(640/w, 360/h)
#         if scale < 1.0:
#             rgb = cv2.resize(rgb, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_LINEAR)
#         pil  = Image.fromarray(rgb)
#         self._photo_ref = ImageTk.PhotoImage(pil)
#         self.canvas.config(image=self._photo_ref, width=640, height=360)

#     def _log(self, msg: str, tag: str = "info"):
#         self.log_box.config(state="normal")
#         ts = time.strftime("%H:%M:%S")
#         self.log_box.insert("end", f"[{ts}] {msg}\n", tag)
#         self.log_box.see("end")
#         self.log_box.config(state="disabled")

#     def _set_status(self, text: str):
#         self.status_lbl.config(text=text)

#     def _set_buttons(self, running: bool):
#         state_run  = "disabled" if running else "normal"
#         state_stop = "normal"   if running else "disabled"
#         self.learn_btn.config(state=state_run)
#         self.test_btn.config(state=state_run)
#         self.stop_btn.config(state=state_stop)

#     def _check_baseline(self):
#         if os.path.exists(BASELINE_FILE):
#             self._detector.load_baseline()
#             thresh = self._detector.panic_threshold
#             self.baseline_badge.config(
#                 text=f"baseline loaded  threshold={thresh:.0f} cm/s",
#                 bg="#EAF3DE", fg="#27500A")
#             self.stat_vars["threshold"].set(f"{thresh:.0f} cm/s")
#             self._log(f"Baseline loaded — threshold {thresh:.0f} cm/s", "ok")
#         else:
#             self._log("No baseline found. Run 'Learn normal behaviour' first.", "warn")

#     def _load_models(self):
#         if self._yolo is None:
#             self._log("Loading YOLOv8n…", "info")
#             self._yolo = YOLO("yolov8n.pt")
#         if self._mapper is None:
#             self._mapper = HomographyMapper(CONFIG_PATH)

#     def _stop(self):
#         self._stop_flag.set()
#         self._set_status("Stopping…")

#     # ── Learn phase ───────────────────────────────────────────────────────────

#     def _start_learn(self):
#         path = filedialog.askopenfilename(
#             title="Select normal behaviour video",
#             filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv")])
#         if not path:
#             return
#         self._stop_flag.clear()
#         self._set_buttons(True)
#         self._log(f"Learning from: {os.path.basename(path)}", "info")
#         self._thread = threading.Thread(target=self._learn_worker,
#                                         args=(path,), daemon=True)
#         self._thread.start()

#     def _learn_worker(self, video_path: str):
#         self.after(0, lambda: self._set_status("Learning…"))
#         self._load_models()

#         detector = PanicDetector(BASELINE_FILE)
#         cap = cv2.VideoCapture(video_path)
#         total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
#         frame_count  = 0
#         speed_count  = 0

#         cam_id = "cam0"

#         while not self._stop_flag.is_set():
#             success, frame = cap.read()
#             if not success:
#                 break
#             frame_count += 1
#             if frame_count % FRAME_SKIP != 0:
#                 continue

#             current_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
#             results = self._yolo.track(frame, classes=[0], conf=0.5,
#                                        persist=True, tracker="bytetrack.yaml",
#                                        verbose=False)
#             vis = frame.copy()

#             if results[0].boxes.id is not None:
#                 boxes     = results[0].boxes.xywh.cpu().numpy()
#                 track_ids = results[0].boxes.id.int().cpu().tolist()

#                 for box, tid in zip(boxes, track_ids):
#                     xc, yc, w, h = box
#                     x1, y1 = int(xc-w/2), int(yc-h/2)
#                     x2, y2 = int(xc+w/2), int(yc+h/2)
#                     foot = (int(xc), int(yc+h/2))

#                     floor_pos = self._mapper.map_to_floor(cam_id, foot)
#                     if floor_pos:
#                         speed = detector.update_and_get_speed(tid, floor_pos, current_time)
#                         detector.record_normal_behavior(speed)
#                         if speed > 10:
#                             speed_count += 1

#                     cv2.rectangle(vis, (x1,y1), (x2,y2), (100, 200, 100), 2)
#                     cv2.putText(vis, f"ID {tid}", (x1, y1-8),
#                                 cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100,200,100), 1)

#             # Progress bar overlay
#             progress = frame_count / max(total_frames, 1)
#             bar_w = int(vis.shape[1] * progress)
#             cv2.rectangle(vis, (0, vis.shape[0]-8), (bar_w, vis.shape[0]),
#                           (100, 200, 100), -1)

#             # Status overlay
#             overlay = vis.copy()
#             cv2.rectangle(overlay, (0,0), (420, 52), (20,20,20), -1)
#             cv2.addWeighted(overlay, 0.55, vis, 0.45, 0, vis)
#             cv2.putText(vis, f"LEARNING  speeds recorded: {speed_count}",
#                         (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
#                         (100, 230, 100), 2)

#             self.after(0, lambda f=vis: self._update_canvas(f))
#             self.after(0, lambda n=speed_count: self.stat_vars["tracked"].set(str(n)))

#         cap.release()

#         if not self._stop_flag.is_set() and len(detector.normal_speeds) >= 10:
#             detector.finalize_training()
#             self._detector = detector
#             thresh = detector.panic_threshold
#             mean   = detector.mean_speed

#             self.after(0, lambda: [
#                 self.baseline_badge.config(
#                     text=f"baseline saved  threshold={thresh:.0f} cm/s",
#                     bg="#EAF3DE", fg="#27500A"),
#                 self.stat_vars["threshold"].set(f"{thresh:.0f} cm/s"),
#                 self._log(f"Learning complete — avg speed {mean:.0f} cm/s  "
#                           f"threshold {thresh:.0f} cm/s", "ok"),
#                 self._set_status("Learning complete"),
#             ])
#         elif not self._stop_flag.is_set():
#             self.after(0, lambda: [
#                 self._log("Not enough movement data — try a longer video", "warn"),
#                 self._set_status("Learning failed — not enough data"),
#             ])
#         else:
#             self.after(0, lambda: self._set_status("Stopped"))

#         self.after(0, lambda: self._set_buttons(False))

#     # ── Test phase ────────────────────────────────────────────────────────────

#     def _start_test(self):
#         if not self._detector.is_trained:
#             if not messagebox.askyesno(
#                 "No baseline",
#                 "No baseline loaded. Run 'Learn normal behaviour' first.\n\n"
#                 "Continue anyway with default threshold (200 cm/s)?"):
#                 return
#             self._detector.panic_threshold = 200.0
#             self._detector.is_trained = True

#         path = filedialog.askopenfilename(
#             title="Select test video",
#             filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv")])
#         if not path:
#             return
#         self._stop_flag.clear()
#         self._set_buttons(True)
#         self._log(f"Testing: {os.path.basename(path)}", "info")
#         self._thread = threading.Thread(target=self._test_worker,
#                                         args=(path,), daemon=True)
#         self._thread.start()

#     def _test_worker(self, video_path: str):
#         self.after(0, lambda: self._set_status("Running panic detection…"))
#         self._load_models()

#         cap   = cv2.VideoCapture(video_path)
#         detector    = self._detector
#         frame_count = 0
#         total_alerts = 0
#         last_alert_time = 0
#         alert_until = 0
#         cam_id = "cam0"

#         while not self._stop_flag.is_set():
#             success, frame = cap.read()
#             if not success:
#                 break
#             frame_count += 1
#             if frame_count % FRAME_SKIP != 0:
#                 continue

#             current_video_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
#             current_real_time  = time.time()
#             vis = frame.copy()

#             results = self._yolo.track(frame, classes=[0], conf=0.5,
#                                        persist=True, tracker="bytetrack.yaml",
#                                        verbose=False)

#             panic_count  = 0
#             tracked_count = 0

#             if results[0].boxes.id is not None:
#                 boxes     = results[0].boxes.xywh.cpu().numpy()
#                 track_ids = results[0].boxes.id.int().cpu().tolist()
#                 tracked_count = len(track_ids)

#                 for box, tid in zip(boxes, track_ids):
#                     xc, yc, w, h = box
#                     x1, y1 = int(xc-w/2), int(yc-h/2)
#                     x2, y2 = int(xc+w/2), int(yc+h/2)
#                     foot = (int(xc), int(yc+h/2))

#                     floor_pos = self._mapper.map_to_floor(cam_id, foot)
#                     if floor_pos is None:
#                         floor_pos = (0.0, 0.0)

#                     speed    = detector.update_and_get_speed(tid, floor_pos, current_video_time)
#                     panicking = detector.is_panicking(speed)

#                     if panicking:
#                         panic_count  += 1
#                         total_alerts += 1
#                         color = (0, 0, 255)
#                         # Thick red box
#                         cv2.rectangle(vis, (x1,y1), (x2,y2), color, 4)
#                         # Speed label
#                         cv2.putText(vis, f"ALERT  {speed:.0f} cm/s",
#                                     (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX,
#                                     0.55, color, 2)
#                         # Foot dot
#                         cv2.circle(vis, foot, 6, (0,0,255), -1)

#                         if current_real_time - last_alert_time > 0.5:
#                             last_alert_time = current_real_time
#                             alert_until     = current_real_time + 2.0
#                             msg = f"PANIC  ID {tid}  {speed:.0f} cm/s"
#                             self.after(0, lambda m=msg: self._log(m, "alert"))

#                     else:
#                         color = (60, 220, 100)
#                         cv2.rectangle(vis, (x1,y1), (x2,y2), color, 2)
#                         cv2.putText(vis, f"ID {tid}  {speed:.0f}",
#                                     (x1, y1-8), cv2.FONT_HERSHEY_SIMPLEX,
#                                     0.42, color, 1)

#             # ── Mass panic banner ─────────────────────────────────────────────
#             if panic_count >= 3:
#                 alert_until = current_real_time + 3.0
#                 self.after(0, lambda: self._log(
#                     "MASS PANIC EVENT DETECTED", "alert"))

#             if current_real_time < alert_until:
#                 overlay = vis.copy()
#                 cv2.rectangle(overlay, (0,0), (vis.shape[1], 90), (0,0,200), -1)
#                 cv2.addWeighted(overlay, 0.45, vis, 0.55, 0, vis)
#                 cv2.putText(vis, "!!! PANIC DETECTED !!!",
#                             (vis.shape[1]//2 - 230, 62),
#                             cv2.FONT_HERSHEY_DUPLEX, 1.4, (255,255,255), 3)

#             # ── Stats overlay ─────────────────────────────────────────────────
#             thresh_txt = f"Threshold: {detector.panic_threshold:.0f} cm/s"
#             cv2.putText(vis, thresh_txt, (10, vis.shape[0]-12),
#                         cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)

#             self.after(0, lambda f=vis: self._update_canvas(f))
#             self.after(0, lambda t=tracked_count, p=panic_count, a=total_alerts: [
#                 self.stat_vars["tracked"].set(str(t)),
#                 self.stat_vars["panicking"].set(str(p)),
#                 self.stat_vars["total_alerts"].set(str(a)),
#             ])

#         cap.release()
#         self.after(0, lambda: [
#             self._set_status("Finished"),
#             self._set_buttons(False),
#             self._log(f"Done — total alerts: {total_alerts}", "ok"),
#             self._show_placeholder("Test complete"),
#         ])


# if __name__ == "__main__":
#     app = PanicUI()
#     app.mainloop()

"""
dashboard/panic_ui.py

Panic Detection UI — two phases in one window:

  LEARN phase:
    - Load a normal behaviour video
    - Video plays in the UI window
    - Live speed histogram builds up as people walk
    - "Finalize Learning" button saves the baseline to config/panic_baseline.json

  TEST phase:
    - Load a panic/test video
    - Video plays with real-time panic detection overlay
    - Red bounding boxes + banner for panicking persons
    - Live stats: panic count, threshold

Run:
    python dashboard/panic_ui.py
"""

"""
dashboard/panic_ui.py

Panic Detection UI — two phases in one window:

  LEARN phase:
    - Load a normal behaviour video
    - Video plays in the UI window
    - Live speed histogram builds up as people walk
    - "Finalize Learning" button saves the baseline to config/panic_baseline.json

  TEST phase:
    - Load a panic/test video
    - Video plays with real-time panic detection overlay
    - Red bounding boxes + banner for panicking persons
    - Live stats: panic count, total alerts (cooldown filtered)

Run:
    python dashboard/panic_ui.py
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import time
import os
import json
import math
import cv2
import numpy as np
from PIL import Image, ImageTk

from ultralytics import YOLO
from disaster_recovery.tools.homography import HomographyMapper
from disaster_recovery.panic.panic_detector import PanicDetector

BASELINE_FILE = "config/panic_baseline.json"
CONFIG_PATH   = "config/cameras.yaml"
FRAME_SKIP    = 2

C_BG    = "#F5F5F3"; C_CARD  = "#FFFFFF"; C_TEXT  = "#1A1A18"
C_MUTED = "#888780"; C_META  = "#F1EFE8"; C_SUB   = "#5F5E5A"
C_GREEN = "#3B6D11"; C_RED   = "#A32D2D"; C_BLUE  = "#185FA5"
C_AMBER = "#854F0B"


class PanicUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Panic Detection System")
        self.configure(bg=C_BG)
        self.resizable(False, False)

        # Shared state
        self._stop_flag   = threading.Event()
        self._thread      = None
        self._photo_ref   = None   # keep ImageTk reference alive

        # ML objects (lazy loaded)
        self._yolo    = None
        self._mapper  = None
        self._detector = PanicDetector(BASELINE_FILE)

        self._build()
        self._check_baseline()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=C_BG)
        hdr.pack(fill="x", padx=16, pady=(16, 6))
        tk.Label(hdr, text="Panic detection",
                 font=("Helvetica", 16, "bold"), fg=C_TEXT, bg=C_BG).pack(side="left")

        # Video canvas
        canvas_frame = tk.Frame(self, bg="#1A1A18",
                                highlightthickness=1, highlightbackground="#D3D1C7")
        canvas_frame.pack(padx=16, pady=(0, 10))
        self.canvas = tk.Label(canvas_frame, bg="#1A1A18",
                               width=640, height=360)
        self.canvas.pack()
        self._show_placeholder("No video loaded")

        # Stats row
        stats = tk.Frame(self, bg=C_BG)
        stats.pack(fill="x", padx=16, pady=(0, 10))
        self.stat_vars = {}
        for label, key, col, c in [
            ("Panicking now",  "panicking",  C_RED,   0),
            ("Total alerts",   "total_alerts", C_RED, 1),
        ]:
            cell = tk.Frame(stats, bg=C_META, padx=10, pady=8)
            cell.grid(row=0, column=c, padx=(0,8) if c<1 else 0, sticky="ew")
            stats.columnconfigure(c, weight=1)
            tk.Label(cell, text=label, font=("Helvetica", 10),
                     fg=C_SUB, bg=C_META).pack(anchor="w")
            v = tk.StringVar(value="—")
            self.stat_vars[key] = v
            tk.Label(cell, textvariable=v, font=("Helvetica", 18, "bold"),
                     fg=col, bg=C_META).pack(anchor="w")

        # Log box
        log_frame = tk.Frame(self, bg=C_BG)
        log_frame.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(log_frame, text="Event log",
                 font=("Helvetica", 11, "bold"), fg=C_TEXT, bg=C_BG).pack(anchor="w")
        self.log_box = tk.Text(log_frame, height=5, font=("Courier", 10),
                               bg="#1A1A18", fg="#E0E0E0",
                               relief="flat", state="disabled",
                               highlightthickness=1, highlightbackground="#D3D1C7")
        self.log_box.pack(fill="x")
        # Tag colours
        self.log_box.tag_config("alert",  foreground="#FF6B6B")
        self.log_box.tag_config("info",   foreground="#7EC8E3")
        self.log_box.tag_config("ok",     foreground="#90EE90")
        self.log_box.tag_config("warn",   foreground="#FFD700")

        # Button row
        btn_row = tk.Frame(self, bg=C_BG)
        btn_row.pack(fill="x", padx=16, pady=(0, 16))

        self.learn_btn = tk.Button(
            btn_row, text="Learn normal behaviour",
            font=("Helvetica", 11), relief="flat",
            bg="#EAF3DE", fg=C_GREEN, padx=14, pady=7,
            cursor="hand2", command=self._start_learn)
        self.learn_btn.pack(side="left", padx=(0, 8))

        self.test_btn = tk.Button(
            btn_row, text="Test panic detection",
            font=("Helvetica", 11), relief="flat",
            bg="#FCEBEB", fg=C_RED, padx=14, pady=7,
            cursor="hand2", command=self._start_test)
        self.test_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = tk.Button(
            btn_row, text="Stop",
            font=("Helvetica", 11), relief="flat",
            bg=C_META, fg=C_TEXT, padx=14, pady=7,
            cursor="hand2", state="disabled",
            command=self._stop)
        self.stop_btn.pack(side="left")

        self.status_lbl = tk.Label(btn_row, text="Ready",
                                   font=("Helvetica", 10), fg=C_MUTED, bg=C_BG)
        self.status_lbl.pack(side="right")

        self.geometry("690x700")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _show_placeholder(self, text: str):
        img = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.putText(img, text, (180, 190),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 80, 80), 2)
        self._update_canvas(img)

    def _update_canvas(self, frame: np.ndarray):
        """Convert OpenCV frame to Tkinter image and show on canvas."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        # Fit to 640x360
        scale = min(640/w, 360/h)
        if scale < 1.0:
            rgb = cv2.resize(rgb, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_LINEAR)
        pil  = Image.fromarray(rgb)
        self._photo_ref = ImageTk.PhotoImage(pil)
        self.canvas.config(image=self._photo_ref, width=640, height=360)

    def _log(self, msg: str, tag: str = "info"):
        self.log_box.config(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{ts}] {msg}\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _set_status(self, text: str):
        self.status_lbl.config(text=text)

    def _set_buttons(self, running: bool):
        state_run  = "disabled" if running else "normal"
        state_stop = "normal"   if running else "disabled"
        self.learn_btn.config(state=state_run)
        self.test_btn.config(state=state_run)
        self.stop_btn.config(state=state_stop)

    def _check_baseline(self):
        if os.path.exists(BASELINE_FILE):
            self._detector.load_baseline()
            self._log("Baseline profile loaded successfully.", "ok")
        else:
            self._log("No baseline found. Run 'Learn normal behaviour' first.", "warn")

    def _load_models(self):
        if self._yolo is None:
            self._log("Loading YOLOv8n…", "info")
            self._yolo = YOLO("yolov8n.pt")
        if self._mapper is None:
            self._mapper = HomographyMapper(CONFIG_PATH)

    def _stop(self):
        self._stop_flag.set()
        self._set_status("Stopping…")

    # ── Learn phase ───────────────────────────────────────────────────────────

    def _start_learn(self):
        path = filedialog.askopenfilename(
            title="Select normal behaviour video",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv")])
        if not path:
            return
        self._stop_flag.clear()
        self._set_buttons(True)
        self._log(f"Learning from: {os.path.basename(path)}", "info")
        self._thread = threading.Thread(target=self._learn_worker,
                                        args=(path,), daemon=True)
        self._thread.start()

    def _learn_worker(self, video_path: str):
        self.after(0, lambda: self._set_status("Learning…"))
        self._load_models()

        detector = PanicDetector(BASELINE_FILE)
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_count  = 0
        speed_count  = 0

        cam_id = "cam0"

        while not self._stop_flag.is_set():
            success, frame = cap.read()
            if not success:
                break
            frame_count += 1
            if frame_count % FRAME_SKIP != 0:
                continue

            current_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            results = self._yolo.track(frame, classes=[0], conf=0.5,
                                       persist=True, tracker="bytetrack.yaml",
                                       verbose=False)
            vis = frame.copy()

            if results[0].boxes.id is not None:
                boxes     = results[0].boxes.xywh.cpu().numpy()
                track_ids = results[0].boxes.id.int().cpu().tolist()

                for box, tid in zip(boxes, track_ids):
                    xc, yc, w, h = box
                    x1, y1 = int(xc-w/2), int(yc-h/2)
                    x2, y2 = int(xc+w/2), int(yc+h/2)
                    foot = (int(xc), int(yc+h/2))

                    floor_pos = self._mapper.map_to_floor(cam_id, foot)
                    if floor_pos:
                        speed = detector.update_and_get_speed(tid, floor_pos, current_time)
                        detector.record_normal_behavior(speed)
                        if speed > 10:
                            speed_count += 1

                    cv2.rectangle(vis, (x1,y1), (x2,y2), (100, 200, 100), 2)
                    cv2.putText(vis, f"ID {tid}", (x1, y1-8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100,200,100), 1)

            # Progress bar overlay
            progress = frame_count / max(total_frames, 1)
            bar_w = int(vis.shape[1] * progress)
            cv2.rectangle(vis, (0, vis.shape[0]-8), (bar_w, vis.shape[0]),
                          (100, 200, 100), -1)

            # Status overlay
            overlay = vis.copy()
            cv2.rectangle(overlay, (0,0), (420, 52), (20,20,20), -1)
            cv2.addWeighted(overlay, 0.55, vis, 0.45, 0, vis)
            cv2.putText(vis, f"LEARNING  speeds recorded: {speed_count}",
                        (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                        (100, 230, 100), 2)

            self.after(0, lambda f=vis: self._update_canvas(f))

        cap.release()

        if not self._stop_flag.is_set() and len(detector.normal_speeds) >= 10:
            detector.finalize_training()
            self._detector = detector

            self.after(0, lambda: [
                self._log("Learning complete — baseline saved successfully.", "ok"),
                self._set_status("Learning complete"),
            ])
        elif not self._stop_flag.is_set():
            self.after(0, lambda: [
                self._log("Not enough movement data — try a longer video", "warn"),
                self._set_status("Learning failed — not enough data"),
            ])
        else:
            self.after(0, lambda: self._set_status("Stopped"))

        self.after(0, lambda: self._set_buttons(False))

    # ── Test phase ────────────────────────────────────────────────────────────

    def _start_test(self):
        if not self._detector.is_trained:
            if not messagebox.askyesno(
                "No baseline",
                "No baseline loaded. Run 'Learn normal behaviour' first.\n\n"
                "Continue anyway with default settings?"):
                return
            self._detector.panic_threshold = 200.0
            self._detector.is_trained = True

        path = filedialog.askopenfilename(
            title="Select test video",
            filetypes=[("Video files", "*.mp4 *.avi *.mov *.mkv")])
        if not path:
            return
        self._stop_flag.clear()
        self._set_buttons(True)
        self._log(f"Testing: {os.path.basename(path)}", "info")
        self._thread = threading.Thread(target=self._test_worker,
                                        args=(path,), daemon=True)
        self._thread.start()

    def _test_worker(self, video_path: str):
        self.after(0, lambda: self._set_status("Running panic detection…"))
        self._load_models()

        cap   = cv2.VideoCapture(video_path)
        detector    = self._detector
        frame_count = 0
        
        # --- Updated Tracking Variables ---
        total_alerts = 0
        last_alert_times = {}  # Dictionary to track cooldown per person ID
        ALERT_COOLDOWN = 3.0   # 3-second cooldown per person
        alert_until = 0
        
        cam_id = "cam0"

        while not self._stop_flag.is_set():
            success, frame = cap.read()
            if not success:
                break
            frame_count += 1
            if frame_count % FRAME_SKIP != 0:
                continue

            current_video_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            current_real_time  = time.time()
            vis = frame.copy()

            results = self._yolo.track(frame, classes=[0], conf=0.5,
                                       persist=True, tracker="bytetrack.yaml",
                                       verbose=False)

            panic_count   = 0
            tracked_count = 0

            if results[0].boxes.id is not None:
                boxes     = results[0].boxes.xywh.cpu().numpy()
                track_ids = results[0].boxes.id.int().cpu().tolist()
                tracked_count = len(track_ids)

                for box, tid in zip(boxes, track_ids):
                    xc, yc, w, h = box
                    x1, y1 = int(xc-w/2), int(yc-h/2)
                    x2, y2 = int(xc+w/2), int(yc+h/2)
                    foot = (int(xc), int(yc+h/2))

                    floor_pos = self._mapper.map_to_floor(cam_id, foot)
                    if floor_pos is None:
                        floor_pos = (0.0, 0.0)

                    speed    = detector.update_and_get_speed(tid, floor_pos, current_video_time)
                    panicking = detector.is_panicking(speed)

                    if panicking:
                        panic_count  += 1
                        
                        color = (0, 0, 255)
                        # Thick red box (Draws every frame)
                        cv2.rectangle(vis, (x1,y1), (x2,y2), color, 4)
                        # Speed label
                        cv2.putText(vis, f"ALERT  {speed:.0f} cm/s",
                                    (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.55, color, 2)
                        # Foot dot
                        cv2.circle(vis, foot, 6, (0,0,255), -1)

                        # Cooldown check for this specific Track ID
                        last_time = last_alert_times.get(tid, 0)
                        if current_real_time - last_time > ALERT_COOLDOWN:
                            total_alerts += 1
                            last_alert_times[tid] = current_real_time
                            msg = f"PANIC  ID {tid}  {speed:.0f} cm/s"
                            self.after(0, lambda m=msg: self._log(m, "alert"))

                    else:
                        color = (60, 220, 100)
                        cv2.rectangle(vis, (x1,y1), (x2,y2), color, 2)
                        cv2.putText(vis, f"ID {tid}  {speed:.0f}",
                                    (x1, y1-8), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.42, color, 1)

            # ── Mass panic banner ─────────────────────────────────────────────
            # To filter out false alarms, an emergency is only triggered if 
            # more than 25% of the room's occupants suddenly cross the outlier threshold.
            if tracked_count > 0 and (panic_count / tracked_count) > 0.25:
                alert_until = current_real_time + 3.0
                self.after(0, lambda: self._log(
                    "MASS PANIC EVENT DETECTED (>25% threshold crossed)", "alert"))

            if current_real_time < alert_until:
                overlay = vis.copy()
                cv2.rectangle(overlay, (0,0), (vis.shape[1], 90), (0,0,200), -1)
                cv2.addWeighted(overlay, 0.45, vis, 0.55, 0, vis)
                cv2.putText(vis, "!!! PANIC DETECTED !!!",
                            (vis.shape[1]//2 - 230, 62),
                            cv2.FONT_HERSHEY_DUPLEX, 1.4, (255,255,255), 3)

            self.after(0, lambda f=vis: self._update_canvas(f))
            self.after(0, lambda p=panic_count, a=total_alerts: [
                self.stat_vars["panicking"].set(str(p)),
                self.stat_vars["total_alerts"].set(str(a)),
            ])

        cap.release()
        self.after(0, lambda: [
            self._set_status("Finished"),
            self._set_buttons(False),
            self._log(f"Done — total alerts: {total_alerts}", "ok"),
            self._show_placeholder("Test complete"),
        ])


if __name__ == "__main__":
    app = PanicUI()
    app.mainloop()
    app.mainloop()