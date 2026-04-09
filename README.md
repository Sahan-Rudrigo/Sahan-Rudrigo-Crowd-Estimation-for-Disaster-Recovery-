# Crowd Estimation for Disaster Recovery

Real-time multi-camera crowd monitoring with global ID tracking, door line counting, and panic detection.

## Project Structure

```text
data_M_project/
├─ src/
│  └─ disaster_recovery/             # Main Python package (professional src layout)
│     ├─ apps/                       # Runtime pipelines
│     ├─ services/                   # Background services
│     ├─ scripts/                    # Utility and calibration logic
│     ├─ core/                       # Tracking, matching, re-id internals
│     ├─ panic/                      # Panic detection logic
│     ├─ tools/                      # Shared homography utilities
│     └─ dashboard/                  # Dashboard application modules
├─ apps/
│  └─ run_tracking.py                # Wrapper: preserves legacy command
├─ services/
│  ├─ describer_api.py               # Wrapper: preserves legacy command
│  └─ describer_local.py             # Wrapper: preserves legacy command
├─ scripts/
│  ├─ train_panic_baseline.py        # Wrapper: preserves legacy command
│  └─ tools/
│     ├─ calibrate.py                # Wrapper: preserves legacy command
│     ├─ set_door_line.py            # Wrapper: preserves legacy command
│     └─ verify_calibration.py       # Wrapper: preserves legacy command
├─ tests/
│  ├─ test_cuda.py                   # CUDA/GPU sanity check
│  └─ test_panic_detection.py        # Panic detector test runner
├─ dashboard/                        # Runtime JSON state + wrapper UI launchers
├─ config/                           # Camera and panic configuration
├─ logs/                             # Runtime logs
├─ local_blip_model/                 # Local model artifacts
├─ pyproject.toml
├─ requirements.txt
└─ yolov8n.pt
```

## Quick Start

1. Create and activate your Python environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
pip install -e .
```

3. Run the main tracker:

```bash
python apps/run_tracking.py
```

## Common Commands

```bash
# Services
python services/describer_api.py
python services/describer_local.py

# Dashboard
python dashboard/ui.py
python dashboard/panic_ui.py

# Panic workflow
python scripts/train_panic_baseline.py
python tests/test_panic_detection.py

# Calibration tools
python scripts/tools/calibrate.py --video <path_to_video> --cam cam0
python scripts/tools/verify_calibration.py --video <path_to_video> --cam cam0
python scripts/tools/set_door_line.py --video <path_to_video> --cam cam0
```

## Notes

- Run commands from the repository root.
- Source code now lives under `src/disaster_recovery`.
- Existing commands still work via wrapper files in `apps/`, `services/`, `scripts/`, and `dashboard/`.
- Keep `config/cameras.yaml` calibrated before production runs.
- `dashboard/state.json` and `dashboard/occupants.json` are runtime state files and are updated automatically.
