"""Build a YOLO dataset using the project's three bin classes."""

import argparse
import json
import random
import shutil
from pathlib import Path
import hashlib

from detection_classes import BIN_BY_CLASS, CLASSES

SOURCE = Path("public")
ANNOTATIONS = Path("annotations_detailed")
OUT = Path("detection_dataset")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
VAL_RATIO = 0.2
SEED = 42

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--replace",
    action="store_true",
    help="delete and rebuild an existing detection_dataset/",
)
args = parser.parse_args()


# Collect images that have a label
items = []
for img in sorted(SOURCE.rglob("*")):
    if not (img.is_file() and img.suffix.lower() in IMAGE_EXTENSIONS):
        continue
    if img.parent == SOURCE:
        continue
    label = ANNOTATIONS / img.relative_to(SOURCE).with_suffix(".txt")
    if label.exists():
        items.append((img, label))

if not items:
    raise SystemExit(
        f"No labeled images found under {SOURCE}; existing {OUT}/ was left untouched."
    )

# Validate source labels before touching the generated dataset.
for label in (label for _, label in items):
    for line_no, line in enumerate(label.read_text().splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"Expected 5 YOLO values at {label}:{line_no}")
        try:
            class_id = int(parts[0])
        except ValueError as error:
            raise ValueError(f"Invalid class ID at {label}:{line_no}") from error
        if not 0 <= class_id < len(CLASSES):
            raise ValueError(
                f"Class ID {class_id} at {label}:{line_no} is outside the three-bin range 0-2"
            )

if OUT.exists() and not args.replace:
    raise SystemExit(
        f"{OUT}/ already exists and was left untouched. Pass --replace to rebuild it."
    )

# Start clean only after confirming there are labeled images and valid labels.
if OUT.exists():
    shutil.rmtree(OUT)
for sub in ("images/train", "images/val", "labels/train", "labels/val"):
    (OUT / sub).mkdir(parents=True)

random.seed(SEED)
random.shuffle(items)
n_val = max(1, int(len(items) * VAL_RATIO))

for i, (img, label) in enumerate(items):
    split = "val" if i < n_val else "train"
    rel = "_".join(img.relative_to(SOURCE).with_suffix("").parts).replace(" ", "-")
    stem = rel[:80] + "_" + hashlib.md5(rel.encode()).hexdigest()[:8]
    shutil.copy(img, OUT / "images" / split / f"{stem}{img.suffix.lower()}")
    rows = []
    for line in label.read_text().splitlines():
        parts = line.split()
        if len(parts) == 5:
            try:
                class_id = int(parts[0])
            except ValueError:
                continue
            rows.append(" ".join([str(class_id)] + parts[1:]))
    (OUT / "labels" / split / f"{stem}.txt").write_text(
        "\n".join(rows) + ("\n" if rows else "")
    )

(OUT / "data.yaml").write_text(
    "train: images/train\nval: images/val\n"
    f"nc: {len(CLASSES)}\nnames: {CLASSES}\n"
)
Path("bin_by_class.json").write_text(json.dumps(BIN_BY_CLASS, indent=2))

print(f"{len(items)} images: {len(items) - n_val} train, {n_val} val")
print(f"{len(CLASSES)} bin classes:")
for name in CLASSES:
    print(f"  {name}")
