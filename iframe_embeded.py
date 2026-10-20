import os
import threading
import time
from pathlib import Path

import cv2
from flask import Flask, Response, jsonify
from flask_cors import CORS
from ultralytics import YOLO

from detection_classes import BIN_BY_CLASS


MODEL_PATH = Path(os.getenv(
    "WASTE_DETECTION_MODEL",
    "runs/detect/runs/detect/waste-3/weights/best.pt",
))
DEVICE = os.getenv("DEVICE", "0")
CONFIDENCE = 0.35
IMAGE_SIZE = 640

if not MODEL_PATH.is_file():
    raise SystemExit(
        f"Detection weights not found: {MODEL_PATH}. "
        "Set WASTE_DETECTION_MODEL to the path of your trained detection weights."
    )

app = Flask(__name__)
CORS(app)
model = YOLO(str(MODEL_PATH))
cap = cv2.VideoCapture(0)

state = {"label": "unsure", "conf": 0.0, "bin": None, "detections": []}
latest_jpg = None


def read_detections(result):
    detections = []
    if result.boxes is None:
        return detections

    for box in result.boxes:
        class_id = int(box.cls[0].item())
        label = result.names[class_id]
        conf = float(box.conf[0].item())
        x1, y1, x2, y2 = (int(round(value)) for value in box.xyxy[0].tolist())
        detections.append({
            "label": label,
            "conf": conf,
            "bin": BIN_BY_CLASS.get(label),
            "box": [x1, y1, x2, y2],
            "class_id": class_id,
        })
    detections.sort(key=lambda item: item["conf"], reverse=True)
    return detections


def draw_detections(frame, detections):
    for item in detections:
        x1, y1, x2, y2 = item["box"]
        color = (50 + (item["class_id"] * 47) % 206, 220, 80 + (item["class_id"] * 29) % 176)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{item['label']} {item['conf']:.0%}"
        cv2.putText(frame, label, (x1, max(22, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
    return frame


def worker():
    global latest_jpg
    last_prediction = 0.0
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.1)
            continue

        now = time.time()
        if now - last_prediction >= 0.2:  # Run inference up to 5 times per second.
            result = model.predict(
                frame,
                device=DEVICE,
                imgsz=IMAGE_SIZE,
                conf=CONFIDENCE,
                verbose=False,
            )[0]
            detections = read_detections(result)
            top = detections[0] if detections else None
            state.update(
                label=top["label"] if top else "unsure",
                conf=top["conf"] if top else 0.0,
                bin=top["bin"] if top else None,
                detections=detections,
            )
            last_prediction = now

        draw_detections(frame, state["detections"])
        latest_jpg = cv2.imencode(".jpg", frame)[1].tobytes()
        time.sleep(0.03)


@app.route("/video")
def video():
    def generate():
        while True:
            if latest_jpg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + latest_jpg + b"\r\n"
            time.sleep(0.05)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/result")
def result():
    return jsonify(state)


@app.route("/")
def index():
    return """
    <html>
      <body style="margin:0;background:#111;color:#fff;font-family:sans-serif;text-align:center">
        <h2>Waste Detector</h2>
        <img src="/video" style="max-width:100%;border-radius:8px">
        <pre id="out">loading...</pre>
        <script>
          setInterval(async () => {
            const r = await fetch('/api/result');
            document.getElementById('out').textContent = JSON.stringify(await r.json(), null, 2);
          }, 300);
        </script>
      </body>
    </html>
    """


if __name__ == "__main__":
    if not cap.isOpened():
        raise SystemExit("Can't open camera. Check permissions or change VideoCapture(0).")
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True)
