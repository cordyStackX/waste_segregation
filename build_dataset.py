"""Build a YOLO dataset with detailed classes (from subfolders) + bin mapping."""

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

# Start clean
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
            if not 0 <= class_id < len(CLASSES):
                continue
            rows.append(" ".join([str(class_id)] + parts[1:]))
    (OUT / "labels" / split / f"{stem}.txt").write_text(
        "\n".join(rows) + ("\n" if rows else "")
    )

(OUT / "data.yaml").write_text(
    f"path: {OUT.resolve()}\ntrain: images/train\nval: images/val\n"
    f"nc: {len(CLASSES)}\nnames: {CLASSES}\n"
)
Path("bin_by_class.json").write_text(json.dumps(BIN_BY_CLASS, indent=2))

print(f"{len(items)} images: {len(items) - n_val} train, {n_val} val")
print(f"{len(CLASSES)} bin classes:")
for name in CLASSES:
    print(f"  {name}")
