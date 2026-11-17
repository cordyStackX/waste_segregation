"""Draw YOLO bounding boxes for images in public/ using OpenCV."""

from pathlib import Path

import cv2
from detection_classes import BIN_BY_CLASS, CLASSES, class_id_for_image


SOURCE = Path("public")
ANNOTATIONS = Path("annotations_detailed")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
WINDOW = "Waste image annotator"
MAX_WIDTH = 1200
MAX_HEIGHT = 800
WHITE = (255, 255, 255)

# Colors (BGR) are per bin, so you can tell the three bins apart at a glance.
BIN_COLORS = {
    "biodegradable": (60, 220, 80),
    "non_biodegradable": (255, 170, 30),
    "residual_special_waste": (40, 50, 240),
}
CLASS_LEGEND = "  ".join(f"{i + 1} {name}" for i, name in enumerate(CLASSES))
MAX_KEYS = min(len(CLASSES), 9)  # number keys 1-9


def bin_of(cls):
    return BIN_BY_CLASS[CLASSES[cls]]


def color_of(cls):
    return BIN_COLORS.get(bin_of(cls), WHITE)


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
display_image = None
scale = 1.0
image_width = image_height = 0


def label_path(image_path):
    return ANNOTATIONS / image_path.relative_to(SOURCE).with_suffix(".txt")


def mouse(event, x, y, _flags, _param):
    global drag_start, boxes
    if display_image is None:
        return
    if event == cv2.EVENT_LBUTTONDOWN:
        drag_start = (x, y)
    elif event == cv2.EVENT_LBUTTONUP and drag_start is not None:
        x1, y1 = drag_start
        x1, x2 = sorted((max(0, min(x1, display_image.shape[1] - 1)), max(0, min(x, display_image.shape[1] - 1))))
        y1, y2 = sorted((max(0, min(y1, display_image.shape[0] - 1)), max(0, min(y, display_image.shape[0] - 1))))
        if x2 - x1 >= 2 and y2 - y1 >= 2:
            boxes.append((selected_class, x1, y1, x2, y2))
        drag_start = None


def load_image(path):
    global boxes, display_image, scale, image_width, image_height, selected_class
    try:
        default_class = class_id_for_image(path, SOURCE)
    except ValueError:
        print(f"Skipping (no class mapping): {path}")
        return False
    original = cv2.imread(str(path))
    if original is None:
        print(f"Cannot read image: {path}")
        return False
    image_height, image_width = original.shape[:2]
    scale = min(MAX_WIDTH / image_width, MAX_HEIGHT / image_height, 1.0)
    display_image = cv2.resize(original, (round(image_width * scale), round(image_height * scale)))
    selected_class = default_class
    labels = label_path(path)
    boxes = []
    if labels.exists():
        for line in labels.read_text().splitlines():
            values = line.split()
            if len(values) != 5:
                continue
            cls, cx, cy, width, height = map(float, values)
            if not 0 <= int(cls) < len(CLASSES):
                continue
            x1 = round((cx - width / 2) * display_image.shape[1])
            y1 = round((cy - height / 2) * display_image.shape[0])
            x2 = round((cx + width / 2) * display_image.shape[1])
            y2 = round((cy + height / 2) * display_image.shape[0])
            boxes.append((int(cls), x1, y1, x2, y2))
    return True


def save(path):
    out = label_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    shown_height, shown_width = display_image.shape[:2]
    for cls, x1, y1, x2, y2 in boxes:
        cx = ((x1 + x2) / 2) / shown_width
        cy = ((y1 + y2) / 2) / shown_height
        width = (x2 - x1) / shown_width
        height = (y2 - y1) / shown_height
        rows.append(f"{cls} {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}")
    out.write_text("\n".join(rows) + ("\n" if rows else ""))
    print(f"Saved {len(rows)} box(es): {out}")


def render(path):
    canvas = display_image.copy()
    height = canvas.shape[0]

    # Boxes: label shows class and its bin, colored by bin
    for cls, x1, y1, x2, y2 in boxes:
        color = color_of(cls)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        text = f"{CLASSES[cls]} [{bin_of(cls)}]"
        cv2.putText(canvas, text, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    # Status line: image, selected class, and its bin
    status = (
        f"{index + 1}/{len(images)}  {path.relative_to(SOURCE)}  |  "
        f"class: {CLASSES[selected_class]} -> {bin_of(selected_class)}  |  boxes: {len(boxes)}"
    )
    cv2.putText(canvas, status[:160], (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)

    # Bottom legend: class keys, then the three bins in their colors
    cv2.putText(canvas, CLASS_LEGEND, (10, height - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1)
    x = 10
    for bin_name, color in BIN_COLORS.items():
        cv2.rectangle(canvas, (x, height - 20), (x + 12, height - 8), color, -1)
        cv2.putText(canvas, bin_name, (x + 18, height - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        x += 18 + cv2.getTextSize(bin_name, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0][0] + 20

    cv2.imshow(WINDOW, canvas)


cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
cv2.setMouseCallback(WINDOW, mouse)
while index < len(images):
    current = images[index]
    if not load_image(current):
        index += 1
        continue
    while True:
        render(current)
        key = cv2.waitKey(20) & 0xFF
        if ord("1") <= key < ord("1") + MAX_KEYS:
            selected_class = key - ord("1")
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
            raise SystemExit("Stopped. Saved annotations are kept; unsaved boxes on this image were discarded.")

cv2.destroyAllWindows()
print(f"Finished reviewing {len(images)} images. Labels are in {ANNOTATIONS}/")