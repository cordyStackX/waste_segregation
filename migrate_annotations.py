"""Copy old three-bin box annotations into detailed, folder-inferred classes."""

from pathlib import Path

from detection_classes import CLASSES, class_id_for_image

SOURCE = Path("public")
OLD_ANNOTATIONS = Path("annotations")
NEW_ANNOTATIONS = Path("annotations_detailed")

files = sorted(OLD_ANNOTATIONS.rglob("*.txt")) if OLD_ANNOTATIONS.exists() else []
if not files:
    raise SystemExit("No saved annotations found under annotations/")
if NEW_ANNOTATIONS.exists():
    raise SystemExit(f"{NEW_ANNOTATIONS}/ already exists; it was left untouched")

converted = 0
for old_path in files:
    relative = old_path.relative_to(OLD_ANNOTATIONS)
    stem_path = SOURCE / relative.with_suffix("")
    image_path = stem_path
    if not image_path.is_file():
        candidates = [path for path in stem_path.parent.glob(stem_path.name + ".*") if path.is_file()]
        if len(candidates) != 1:
            print(f"skip {old_path}: matching source image not found uniquely")
            continue
        image_path = candidates[0]

    class_id = class_id_for_image(image_path, SOURCE)
    rows = []
    for line_no, line in enumerate(old_path.read_text().splitlines(), 1):
        values = line.split()
        if len(values) != 5:
            raise ValueError(f"Expected YOLO box row with 5 values: {old_path}:{line_no}")
        # Preserve the saved box coordinates; replace the old bin class with
        # the detailed class inferred from the image's category folder.
        rows.append(" ".join([str(class_id), *values[1:]]))

    out = NEW_ANNOTATIONS / image_path.relative_to(SOURCE).with_suffix(".txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(rows) + ("\n" if rows else ""))
    converted += 1

print(f"Converted {converted} annotation files into {NEW_ANNOTATIONS}/")
print("Labels were inferred from folder names; review every box and class in annotate.py before training.")
print("Classes: " + ", ".join(f"{i}: {name}" for i, name in enumerate(CLASSES)))
