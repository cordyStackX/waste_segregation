"""Run waste_detailed-4 detection on one or more image files."""

import json
import os
import sys
from pathlib import Path

from ultralytics import YOLO


MODEL_PATH = Path(
    os.getenv(
        "WASTE_DETECTION_MODEL",
        "runs/detect/waste_detailed-4/weights/best.pt",
    )
)
DEVICE = os.getenv("DEVICE", "0")
CONFIDENCE = float(os.getenv("WASTE_CONFIDENCE", "0.35"))
IMAGE_SIZE = int(os.getenv("WASTE_IMAGE_SIZE", "640"))
BIN_BY_CLASS = json.loads(Path("bin_by_class.json").read_text())

if len(sys.argv) < 2:
    raise SystemExit("Usage: python test.py <image> [<image> ...]")
if not MODEL_PATH.is_file():
    raise SystemExit(f"Detector weights not found: {MODEL_PATH}")

model = YOLO(str(MODEL_PATH))
for image_path in sys.argv[1:]:
    result = model.predict(
        image_path,
        device=DEVICE,
        imgsz=IMAGE_SIZE,
        conf=CONFIDENCE,
        verbose=False,
    )[0]
    print(f"\n{image_path}")
    if result.boxes is None or len(result.boxes) == 0:
        print("  No waste item detected")
        continue
    for box in result.boxes:
        class_name = result.names[int(box.cls[0].item())]
        bin_name = BIN_BY_CLASS.get(class_name, "unknown")
        confidence = float(box.conf[0].item())
        coordinates = [int(round(value)) for value in box.xyxy[0].tolist()]
        print(
            f"  {bin_name}: {class_name} {confidence:.1%} "
            f"box={coordinates}"
        )
