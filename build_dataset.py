"""Build a YOLO dataset with detailed classes (from subfolders) + bin mapping."""

import json
import random
import shutil
from pathlib import Path
import hashlib

SOURCE = Path("public")
ANNOTATIONS = Path("annotations_detailed")
OUT = Path("detection_dataset")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
VAL_RATIO = 0.2
SEED = 42


def norm(text):
    return text.lower().replace(" ", "_").replace("-", "_")


def detailed_class(img):
    """Return (class_name, bin_name) from the folder path under public/."""
    parts = img.relative_to(SOURCE).parts
    bin_name = parts[0].lower()
    if bin_name == "residual_special_waste":
        # public/residual_special_waste/residual_special_waste/Class-A_.../img.jpg
        sub = parts[2] if len(parts) >= 4 else parts[1]
    else:
        sub = parts[1]
    return norm(sub), bin_name


# Collect images that have a label
items = []
for img in sorted(SOURCE.rglob("*")):
    if not (img.is_file() and img.suffix.lower() in IMAGE_EXTENSIONS):
        continue
    if img.parent == SOURCE:
        continue
    label = ANNOTATIONS / img.relative_to(SOURCE).with_suffix(".txt")
    if label.exists():
        name, bin_name = detailed_class(img)
        items.append((img, label, name, bin_name))

names = sorted({name for _, _, name, _ in items})
bin_by_class = {name: b for _, _, name, b in items for name in [name]}
# Paper is routed to the biodegradable bin in the app's current sorting rules.
bin_by_class["paper"] = "biodegradable"
class_id = {name: i for i, name in enumerate(names)}

# Start clean
if OUT.exists():
    shutil.rmtree(OUT)
for sub in ("images/train", "images/val", "labels/train", "labels/val"):
    (OUT / sub).mkdir(parents=True)

random.seed(SEED)
random.shuffle(items)
n_val = max(1, int(len(items) * VAL_RATIO))

for i, (img, label, name, _bin) in enumerate(items):
    split = "val" if i < n_val else "train"
    rel = "_".join(img.relative_to(SOURCE).with_suffix("").parts).replace(" ", "-")
    stem = rel[:80] + "_" + hashlib.md5(rel.encode()).hexdigest()[:8]
    shutil.copy(img, OUT / "images" / split / f"{stem}{img.suffix.lower()}")
    rows = []
    for line in label.read_text().splitlines():
        parts = line.split()
        if len(parts) == 5:
            rows.append(" ".join([str(class_id[name])] + parts[1:]))
    (OUT / "labels" / split / f"{stem}.txt").write_text(
        "\n".join(rows) + ("\n" if rows else "")
    )

(OUT / "data.yaml").write_text(
    f"path: {OUT.resolve()}\ntrain: images/train\nval: images/val\n"
    f"nc: {len(names)}\nnames: {names}\n"
)
Path("bin_by_class.json").write_text(json.dumps(bin_by_class, indent=2))

print(f"{len(items)} images: {len(items) - n_val} train, {n_val} val")
print(f"{len(names)} classes -> bins:")
for name in names:
    print(f"  {name} -> {bin_by_class[name]}")
