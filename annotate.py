"""Draw YOLO bounding boxes for images in public/ using OpenCV (3 classes).

Keys: 1-3 choose class, u undo box, c clear boxes, s save + next, n next,
      p previous, d (twice) remove image, q/Esc quit.
"""

from pathlib import Path
import shutil
import sys

import cv2
from detection_classes import CLASSES, class_id_for_image

SOURCE = Path("public")
ANNOTATIONS = Path("annotations_detailed")
TRASH = Path("removed_images")  # images removed with "d" are moved here
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
WINDOW = "Waste image annotator"
MAX_WIDTH = 1200
MAX_HEIGHT = 800
WHITE = (255, 255, 255)
RED = (40, 50, 240)
FONT = cv2.FONT_HERSHEY_SIMPLEX

# BGR colors, one per class
CLASS_COLORS = [
    (60, 220, 80),    # biodegradable
    (255, 170, 30),   # non_biodegradable
    (40, 50, 240),    # residual_special_waste
]
CLASS_LEGEND = (
    "  ".join(f"{i + 1} {name}" for i, name in enumerate(CLASSES))
    + "  |  d remove image"
)
MAX_KEYS = len(CLASSES)  # keys 1-3


def color_of(cls):
    return CLASS_COLORS[cls] if 0 <= cls < len(CLASS_COLORS) else WHITE


# Only scan files inside class folders (skips logos/infographics directly in public/)
images = sorted(
    (
        path
        for path in SOURCE.rglob("*")
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTENSIONS
        and path.parent != SOURCE
    ),
    key=lambda path: str(path).lower(),
)
if not images:
    raise SystemExit(f"No images found under {SOURCE}")

index = 0
boxes = []
selected_class = 0
drag_start = None
drag_now = None
display_image = None
scale = 1.0
image_width = image_height = 0
pending_delete = False  # True after the first "d" press, waiting for confirmation


def label_path(image_path):
    return ANNOTATIONS / image_path.relative_to(SOURCE).with_suffix(".txt")


def remove_image(path):
    """Move the image to TRASH (keeping its class folder) and drop its label file."""
    dest = TRASH / path.relative_to(SOURCE)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dest))
    labels = label_path(path)
    if labels.exists():
        labels.unlink()
    print(f"Removed: {path} -> {dest}")


# Resume: skip images that already have a saved label file.
# Run `python annotate.py --all` to go through everything again.
if "--all" not in sys.argv:
    images = [p for p in images if not label_path(p).exists()]
    if not images:
        raise SystemExit("All images already have labels. Use --all to review them.")


def clamp(value, low, high):
    return max(low, min(value, high))


def mouse(event, x, y, _flags, _param):
    global drag_start, drag_now, boxes
    if display_image is None:
        return
    h, w = display_image.shape[:2]
    if event == cv2.EVENT_LBUTTONDOWN:
        drag_start = (x, y)
        drag_now = (x, y)
    elif event == cv2.EVENT_MOUSEMOVE and drag_start is not None:
        drag_now = (x, y)
    elif event == cv2.EVENT_LBUTTONUP and drag_start is not None:
        x1, x2 = sorted((clamp(drag_start[0], 0, w - 1), clamp(x, 0, w - 1)))
        y1, y2 = sorted((clamp(drag_start[1], 0, h - 1), clamp(y, 0, h - 1)))
        if x2 - x1 >= 2 and y2 - y1 >= 2:
            boxes.append((selected_class, x1, y1, x2, y2))
        drag_start = None
        drag_now = None


def load_image(path):
    global boxes, display_image, scale, image_width, image_height, selected_class
    try:
        default_class = class_id_for_image(path, SOURCE)
    except ValueError as err:
        print(f"Skipping: {err}")
        return False
    original = cv2.imread(str(path))
    if original is None:
        print(f"Cannot read image: {path}")
        return False
    image_height, image_width = original.shape[:2]
    scale = min(MAX_WIDTH / image_width, MAX_HEIGHT / image_height, 1.0)
    display_image = cv2.resize(
        original, (round(image_width * scale), round(image_height * scale))
    )
    selected_class = default_class

    boxes = []
    labels = label_path(path)
    if labels.exists():
        shown_h, shown_w = display_image.shape[:2]
        for line in labels.read_text().splitlines():
            values = line.split()
            if len(values) != 5:
                continue
            cls, cx, cy, width, height = map(float, values)
            cls = int(cls)
            if not 0 <= cls < len(CLASSES):
                continue  # old/invalid class ID
            x1 = round((cx - width / 2) * shown_w)
            y1 = round((cy - height / 2) * shown_h)
            x2 = round((cx + width / 2) * shown_w)
            y2 = round((cy + height / 2) * shown_h)
            boxes.append((cls, x1, y1, x2, y2))
    return True


def save(path):
    out = label_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    shown_h, shown_w = display_image.shape[:2]
    for cls, x1, y1, x2, y2 in boxes:
        cx = ((x1 + x2) / 2) / shown_w
        cy = ((y1 + y2) / 2) / shown_h
        width = (x2 - x1) / shown_w
        height = (y2 - y1) / shown_h
        rows.append(f"{cls} {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}")
    out.write_text("\n".join(rows) + ("\n" if rows else ""))
    print(f"Saved {len(rows)} box(es): {out}")


def render(path):
    canvas = display_image.copy()
    height = canvas.shape[0]

    # Saved boxes, colored by class
    for cls, x1, y1, x2, y2 in boxes:
        color = color_of(cls)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        cv2.putText(canvas, CLASSES[cls], (x1, max(18, y1 - 6)), FONT, 0.55, color, 2)

    # Box currently being dragged
    if drag_start is not None and drag_now is not None:
        cv2.rectangle(canvas, drag_start, drag_now, color_of(selected_class), 1)

    # Status line
    status = (
        f"{index + 1}/{len(images)}  {path.relative_to(SOURCE)}  |  "
        f"class: {CLASSES[selected_class]}  |  boxes: {len(boxes)}"
    )
    cv2.putText(canvas, status[:160], (10, 22), FONT, 0.5, WHITE, 1)
    if pending_delete:
        cv2.putText(
            canvas,
            "Press d again to REMOVE this image (any other key cancels)",
            (10, 46), FONT, 0.6, RED, 2,
        )

    # Bottom legend: keys, then colored class swatches
    cv2.putText(canvas, CLASS_LEGEND, (10, height - 30), FONT, 0.45, WHITE, 1)
    x = 10
    for name, color in zip(CLASSES, CLASS_COLORS):
        cv2.rectangle(canvas, (x, height - 20), (x + 12, height - 8), color, -1)
        cv2.putText(canvas, name, (x + 18, height - 8), FONT, 0.45, color, 1)
        x += 18 + cv2.getTextSize(name, FONT, 0.45, 1)[0][0] + 20

    cv2.imshow(WINDOW, canvas)


cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
cv2.setMouseCallback(WINDOW, mouse)
while index < len(images):
    current = images[index]
    pending_delete = False
    if not load_image(current):
        index += 1
        continue
    while True:
        render(current)
        key = cv2.waitKey(20) & 0xFF
        if key != 255 and key != ord("d"):
            pending_delete = False  # any other key cancels the confirmation

        if ord("1") <= key < ord("1") + MAX_KEYS:
            selected_class = key - ord("1")
        elif key == ord("d"):
            if pending_delete:
                remove_image(current)
                images.pop(index)  # don't advance: next image slides into this slot
                pending_delete = False
                break
            pending_delete = True
        elif key == ord("u") and boxes:
            boxes.pop()
        elif key == ord("c"):
            boxes.clear()
        elif key == ord("s"):
            save(current)
            index += 1
            break
        elif key == ord("n"):
            index += 1
            break
        elif key == ord("p") and index > 0:
            index -= 1
            break
        elif key == ord("q") or key == 27:
            cv2.destroyAllWindows()
            raise SystemExit(
                "Stopped. Saved annotations are kept; unsaved boxes on this image were discarded."
            )

cv2.destroyAllWindows()
print(f"Finished reviewing {len(images)} images. Labels are in {ANNOTATIONS}/")