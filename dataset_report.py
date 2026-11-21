"""Summarize and plot three-bin annotations without building or training."""

import argparse
from collections import Counter
from html import escape
from pathlib import Path

from detection_classes import CLASSES


SOURCE = Path("public")
ANNOTATIONS = Path("annotations_detailed")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
COLORS = ["#40dc50", "#ffaa1e", "#2832f0"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/label_audit/label_distribution.svg"),
        help="where to save the chart",
    )
    args = parser.parse_args()

    images = sorted(
        path
        for path in SOURCE.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTENSIONS
        and path.parent != SOURCE
    )
    if not images:
        raise SystemExit(f"No images found under {SOURCE}/")

    instances = Counter()
    images_by_class = Counter()
    matched_images = 0
    duplicate_formats = 0
    empty_labels = 0
    invalid_rows = 0
    invalid_row_examples = []
    invalid_class_ids = Counter()
    matched_labels = set()

    for image in images:
        label = ANNOTATIONS / image.relative_to(SOURCE).with_suffix(".txt")
        if not label.is_file():
            continue
        if label in matched_labels:
            duplicate_formats += 1
            continue
        matched_images += 1
        matched_labels.add(label)
        found_classes = set()
        for line_no, line in enumerate(label.read_text(errors="replace").splitlines(), 1):
            values = line.split()
            if not values:
                continue
            if len(values) != 5:
                invalid_rows += 1
                invalid_row_examples.append(f"{label}:{line_no}: expected 5 YOLO values")
                continue
            try:
                class_id = int(values[0])
            except ValueError:
                invalid_rows += 1
                invalid_row_examples.append(f"{label}:{line_no}: invalid class ID")
                continue
            if not 0 <= class_id < len(CLASSES):
                invalid_class_ids[class_id] += 1
                invalid_rows += 1
                invalid_row_examples.append(f"{label}:{line_no}: class ID {class_id} is out of range")
                continue
            try:
                coords = [float(value) for value in values[1:]]
            except ValueError:
                invalid_rows += 1
                invalid_row_examples.append(f"{label}:{line_no}: non-numeric coordinates")
                continue
            center_x, center_y, width, height = coords
            if (
                not all(0 <= value <= 1 for value in coords)
                or width <= 0
                or height <= 0
                or center_x - width / 2 < 0
                or center_y - height / 2 < 0
                or center_x + width / 2 > 1
                or center_y + height / 2 > 1
            ):
                invalid_rows += 1
                invalid_row_examples.append(f"{label}:{line_no}: box is outside image bounds")
                continue
            instances[class_id] += 1
            found_classes.add(class_id)

        if not found_classes:
            empty_labels += 1
        for class_id in found_classes:
            images_by_class[class_id] += 1

    orphan_labels = [path for path in ANNOTATIONS.rglob("*.txt") if path not in matched_labels]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    counts = [instances[index] for index in range(len(CLASSES))]
    width, height = 900, 520
    left, right, top, bottom = 90, 40, 80, 110
    chart_height = height - top - bottom
    max_count = max(counts, default=0) or 1
    scale_max = max(1, int(max_count * 1.15))
    chart = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="450" y="38" text-anchor="middle" font-family="sans-serif" font-size="23" font-weight="bold">Annotated waste boxes by bin (before training)</text>',
        f'<text x="25" y="{top + chart_height // 2}" transform="rotate(-90 25 {top + chart_height // 2})" text-anchor="middle" font-family="sans-serif" font-size="16">Valid box annotations</text>',
    ]
    for tick in range(6):
        value = round(scale_max * tick / 5)
        y = top + chart_height - round(chart_height * value / scale_max)
        chart.extend([
            f'<line x1="{left}" y1="{y}" x2="{width-right}" y2="{y}" stroke="#d8dce2"/>',
            f'<text x="{left-12}" y="{y+5}" text-anchor="end" font-family="sans-serif" font-size="13" fill="#4b5563">{value}</text>',
        ])
    slot = (width - left - right) / len(CLASSES)
    bar_width = slot * 0.5
    for class_id, (name, count) in enumerate(zip(CLASSES, counts)):
        x = left + slot * class_id + (slot - bar_width) / 2
        bar_height = chart_height * count / scale_max
        y = top + chart_height - bar_height
        chart.extend([
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="5" fill="{COLORS[class_id]}"/>',
            f'<text x="{x+bar_width/2:.1f}" y="{max(top+18, y-9):.1f}" text-anchor="middle" font-family="sans-serif" font-size="17" font-weight="bold">{count}</text>',
            f'<text x="{x+bar_width/2:.1f}" y="{height-60}" text-anchor="middle" font-family="sans-serif" font-size="14">{escape(name.replace("_", " "))}</text>',
        ])
    chart.append("</svg>")
    args.output.write_text("\n".join(chart) + "\n")

    print(f"Images found: {len(images)}")
    print(f"Images with matching annotation files: {matched_images}")
    print(f"Duplicate image formats skipped: {duplicate_formats}")
    print(f"Images with no valid boxes: {empty_labels}")
    print(f"Orphan annotation files: {len(orphan_labels)}")
    for class_id, name in enumerate(CLASSES):
        print(
            f"{name}: {instances[class_id]} boxes across "
            f"{images_by_class[class_id]} images"
        )
    print(f"Invalid box rows: {invalid_rows}")
    for example in invalid_row_examples[:10]:
        print(f"  {example}")
    if len(invalid_row_examples) > 10:
        print(f"  ... and {len(invalid_row_examples) - 10} more")
    print(f"Invalid class IDs: {dict(sorted(invalid_class_ids.items())) or 'none'}")
    print(f"Chart saved to: {args.output}")


if __name__ == "__main__":
    main()
