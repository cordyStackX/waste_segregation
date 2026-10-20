"""Split reviewed annotations into a YOLO detection train/validation dataset."""

import random
import shutil
from pathlib import Path

from detection_classes import CLASSES

SOURCE = Path("public")
ANNOTATIONS = Path("annotations_detailed")
DESTINATION = Path("detection_dataset")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
VAL_RATIO = 0.2
SEED = 0

images = sorted(
    (path for path in SOURCE.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
    key=lambda path: str(path).lower(),
)
reviewed = [(image, ANNOTATIONS / image.relative_to(SOURCE).with_suffix(".txt")) for image in images]
reviewed = [(image, label) for image, label in reviewed if label.is_file()]
if len(reviewed) < 2:
    raise SystemExit("Annotate at least two images first with: python annotate.py")

random.Random(SEED).shuffle(reviewed)
val_count = max(1, round(len(reviewed) * VAL_RATIO))
splits = {"val": reviewed[:val_count], "train": reviewed[val_count:]}

if DESTINATION.exists():
    shutil.rmtree(DESTINATION)
for split, rows in splits.items():
    for image, label in rows:
        relative = image.relative_to(SOURCE)
        image_out = DESTINATION / "images" / split / relative
        label_out = DESTINATION / "labels" / split / relative.with_suffix(".txt")
        image_out.parent.mkdir(parents=True, exist_ok=True)
        label_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, image_out)
        shutil.copy2(label, label_out)

yaml = DESTINATION / "data.yaml"
yaml.write_text(
    f"path: {DESTINATION.resolve()}\n"
    "train: images/train\n"
    "val: images/val\n\n"
    "names:\n"
    + "".join(f"  {index}: {name}\n" for index, name in enumerate(CLASSES))
)
print(f"Prepared {len(splits['train'])} train and {len(splits['val'])} validation images in {DESTINATION}/")
print(f"Dataset config: {yaml}")
