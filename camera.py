import json
from pathlib import Path

import cv2
from ultralytics import YOLO

MODEL_PATH = "runs/detect/waste_detailed-6/weights/best.pt"  # change if your best.pt is elsewhere
CONFIDENCE = 0.5
IMAGE_SIZE = 640
WINDOW = "Waste detector (q to quit, f for fullscreen)"

# Written by build_dataset.py: detailed class name -> bin
BIN_BY_CLASS = json.loads(Path("bin_by_class.json").read_text())
BIN_COLORS = {  # BGR
    "biodegradable": (60, 220, 80),
    "non_biodegradable": (255, 170, 30),
    "residual_special_waste": (40, 50, 240),
}

model = YOLO(MODEL_PATH)
cap = cv2.VideoCapture(0)  # 0 = default webcam; try 1 if it doesn't open
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

if not cap.isOpened():
    raise SystemExit("Can't open camera. Try index 1, or check permissions.")

cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)  # resizable window
cv2.resizeWindow(WINDOW, 1280, 720)
fullscreen = False

while True:
    ok, frame = cap.read()
    if not ok:
        break

    h, w = frame.shape[:2]
    scale = w / 640  # grow text and lines with the frame size
    thickness = max(2, round(3 * scale / 2))
    font_scale = 0.9 * scale / 1.5

    r = model.predict(frame, device=0, imgsz=IMAGE_SIZE, conf=CONFIDENCE, verbose=False)[0]

    for box in r.boxes:
        name = r.names[int(box.cls[0])]
        bin_name = BIN_BY_CLASS.get(name, name)
        conf = float(box.conf[0])
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
        color = BIN_COLORS.get(bin_name, (255, 255, 255))

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        text = f"{bin_name} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        top = max(th + 12, y1)
        cv2.rectangle(frame, (x1, top - th - 12), (x1 + tw + 10, top), color, -1)  # label background
        cv2.putText(frame, text, (x1 + 5, top - 6), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, (0, 0, 0), thickness)

    cv2.imshow(WINDOW, frame)
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break
    if key == ord("f"):
        fullscreen = not fullscreen
        cv2.setWindowProperty(
            WINDOW, cv2.WND_PROP_FULLSCREEN,
            cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL,
        )

cap.release()
cv2.destroyAllWindows()