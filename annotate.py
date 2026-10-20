"""Draw YOLO bounding boxes for images in public/ using OpenCV."""

from pathlib import Path

import cv2


SOURCE = Path("public")
ANNOTATIONS = Path("annotations")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
CLASSES = ["biodegradable", "non_biodegradable", "residual_special_waste"]
WINDOW = "Waste image annotator"
MAX_WIDTH = 1200
MAX_HEIGHT = 800

images = sorted(
    (path for path in SOURCE.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
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
    global boxes, display_image, scale, image_width, image_height
    original = cv2.imread(str(path))
    if original is None:
        print(f"Cannot read image: {path}")
        return False
    image_height, image_width = original.shape[:2]
    scale = min(MAX_WIDTH / image_width, MAX_HEIGHT / image_height, 1.0)
    display_image = cv2.resize(original, (round(image_width * scale), round(image_height * scale)))
    labels = label_path(path)
    boxes = []
    if labels.exists():
        for line in labels.read_text().splitlines():
            values = line.split()
            if len(values) != 5:
                continue
            cls, cx, cy, width, height = map(float, values)
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
    for cls, x1, y1, x2, y2 in boxes:
        color = ((60, 220, 80), (255, 170, 30), (40, 50, 240))[cls]
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        cv2.putText(canvas, CLASSES[cls], (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    selected = CLASSES[selected_class]
    status = f"{index + 1}/{len(images)}  {path.relative_to(SOURCE)}  |  class: {selected}  |  boxes: {len(boxes)}"
    cv2.putText(canvas, status[:140], (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
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
        if key in (ord("1"), ord("2"), ord("3")):
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
