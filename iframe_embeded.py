"""Python inference API for the Flutter waste camera."""

import os
import socket
import threading
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from ultralytics import YOLO

import json

# Written by build_dataset.py: detailed class name -> bin
BIN_BY_CLASS = json.loads(
    (Path(__file__).parent / "bin_by_class.json").read_text()
)

MODEL_PATH = Path(os.getenv(
    "WASTE_DETECTION_MODEL",
    "runs/detect/waste_detailed-5/weights/best.pt",
))
DEVICE = os.getenv("DEVICE", "0")
CONFIDENCE = float(os.getenv("WASTE_CONFIDENCE", "0.35"))
IMAGE_SIZE = int(os.getenv("WASTE_IMAGE_SIZE", "512"))
PORT = int(os.getenv("WASTE_PORT", os.getenv("PORT", "5000")))
SSL_CERT = os.getenv("SSL_CERT")  # optional: real cert (e.g. from mkcert)
SSL_KEY = os.getenv("SSL_KEY")

# Folder produced by: flutter build web -t lib/main_web.dart --base-href /app/
WEB_DIR = Path(__file__).parent / "flutter" / "build" / "web"

if not MODEL_PATH.is_file():
    raise SystemExit(
        f"Detection weights not found: {MODEL_PATH}. "
        "Set WASTE_DETECTION_MODEL to the path of your trained detection weights."
    )

app = Flask(__name__)
CORS(app)
model = YOLO(str(MODEL_PATH))
model_lock = threading.Lock()  # Flask is threaded; keep inference one-at-a-time

state = {"label": "unsure", "conf": 0.0, "bin": None, "detections": []}


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
            "label": BIN_BY_CLASS.get(label) or label,
            "type": label,
            "conf": conf,
            "bin": BIN_BY_CLASS.get(label),
            "box": [x1, y1, x2, y2],
            "class_id": class_id,
        })
    detections.sort(key=lambda item: item["conf"], reverse=True)
    return detections


@app.route("/predict", methods=["POST"])
def predict():
    """Body: a JPEG frame. Returns detections in that frame's pixel coordinates."""
    data = np.frombuffer(request.get_data(), np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify(error="could not decode image"), 400

    with model_lock:
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
    height, width = frame.shape[:2]
    return jsonify({**state, "width": width, "height": height})


@app.route("/api/result")
def api_result():
    return jsonify(state)


@app.route("/")
def index():
    return jsonify({
        "service": "waste-detector",
        "camera": "Flutter",
        "analysis": "Python / YOLO",
        "health": "/health",
        "predict": "/predict",
        "flutter_web": "/app/",
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "model": str(MODEL_PATH),
        "classes": model.names,
        "confidence": CONFIDENCE,
        "image_size": IMAGE_SIZE,
    })


@app.route("/app/")
@app.route("/app/<path:p>")
def flutter_app(p="index.html"):
    """Optionally serves the Flutter web build from the Python API origin."""
    if not WEB_DIR.is_dir():
        return (
            "Flutter web build not found. Run: "
            "cd flutter && flutter build web -t lib/main_web.dart --base-href /app/",
            404,
        )
    return send_from_directory(WEB_DIR, p)


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "<laptop-ip>"


if __name__ == "__main__":
    use_https = os.getenv("HTTPS", "0") != "0"
    ssl_context = None
    if use_https:
        ssl_context = (SSL_CERT, SSL_KEY) if SSL_CERT and SSL_KEY else "adhoc"
    scheme = "https" if use_https else "http"
    print(f"\nPython inference API: {scheme}://{lan_ip()}:{PORT}")
    print(f"Health check:         {scheme}://{lan_ip()}:{PORT}/health")
    print(f"Flutter web app:      {scheme}://{lan_ip()}:{PORT}/app/\n")
    app.run(host="0.0.0.0", port=PORT, threaded=True, ssl_context=ssl_context)
