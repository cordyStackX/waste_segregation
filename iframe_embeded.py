"""Python inference API for the Flutter waste camera."""

import json
import os
import socket
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from ultralytics import YOLO

# Written by build_dataset.py: detailed class name -> bin
BIN_BY_CLASS = json.loads(
    (Path(__file__).parent / "bin_by_class.json").read_text()
)

MODEL_PATH = Path(os.getenv(
    "WASTE_DETECTION_MODEL",
    "runs/detect/waste_detailed-8/weights/best.pt",
))
DEVICE = os.getenv("WASTE_DEVICE")
if DEVICE is None:
    DEVICE = "0" if torch.cuda.is_available() else "cpu"
CONFIDENCE = float(os.getenv("WASTE_CONFIDENCE", "0.50"))
IMAGE_SIZE = int(os.getenv("WASTE_IMAGE_SIZE", "640"))
ARDUINO_PORT = os.getenv("WASTE_ARDUINO_PORT")
ARDUINO_BAUD = int(os.getenv("WASTE_ARDUINO_BAUD", "9600"))
SERVO_CONFIDENCE = float(os.getenv("WASTE_SERVO_CONFIDENCE", "0.70"))
SERVO_CONFIRM_FRAMES = int(os.getenv("WASTE_SERVO_CONFIRM_FRAMES", "3"))
SERVO_REARM_FRAMES = int(os.getenv("WASTE_SERVO_REARM_FRAMES", "8"))
SERVO_COOLDOWN_SECONDS = float(os.getenv("WASTE_SERVO_COOLDOWN", "8"))
SERVO_COMMAND_BY_BIN = {
    "biodegradable": "BIO",
    "non_biodegradable": "NONBIO",
    "residual_special_waste": "RESIDUAL",
}
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
arduino_lock = threading.Lock()
trigger_lock = threading.Lock()
arduino_serial = None
arduino_status = {
    "connected": False,
    "pending": False,
    "last_action": None,
    "last_error": None,
}
servo_triggers = {
    bin_name: {
        "confirmations": 0,
        "clear_frames": 0,
        "latched": False,
        "last_attempt": 0.0,
    }
    for bin_name in SERVO_COMMAND_BY_BIN
}

state = {"label": "unsure", "conf": 0.0, "bin": None, "detections": []}


def send_arduino_command(command):
    """Send one newline-terminated command to the USB-connected Uno."""
    global arduino_serial
    if not ARDUINO_PORT:
        arduino_status.update(
            pending=False,
            last_error="WASTE_ARDUINO_PORT is not configured",
        )
        return False

    arduino_status["pending"] = True
    try:
        import serial

        with arduino_lock:
            if arduino_serial is None or not arduino_serial.is_open:
                arduino_serial = serial.Serial(
                    ARDUINO_PORT,
                    ARDUINO_BAUD,
                    timeout=0.25,
                    write_timeout=1,
                )
                # Opening a USB serial port resets many Uno-compatible boards.
                time.sleep(2)
                arduino_serial.reset_input_buffer()

            arduino_serial.write(f"{command}\n".encode("ascii"))
            arduino_serial.flush()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                reply = arduino_serial.readline().decode("ascii", errors="ignore").strip()
                if reply == f"OK:{command}":
                    arduino_status.update(
                        connected=True,
                        pending=False,
                        last_action=command,
                        last_error=None,
                    )
                    return True
                if reply.startswith("ERR:"):
                    raise RuntimeError(f"Arduino replied {reply}")
            raise TimeoutError(f"Arduino did not acknowledge {command}")
    except Exception as error:
        if arduino_serial is not None:
            try:
                arduino_serial.close()
            except Exception:
                pass
            arduino_serial = None
        arduino_status.update(
            connected=False,
            pending=False,
            last_error=str(error),
        )
        return False


def maybe_open_servo(detections):
    """Trigger each lid only after stable, high-confidence bin detections."""
    now = time.monotonic()
    detected_confidence = {
        bin_name: max(
            (item["conf"] for item in detections if item["bin"] == bin_name),
            default=0.0,
        )
        for bin_name in SERVO_COMMAND_BY_BIN
    }
    commands_to_send = []

    with trigger_lock:
        for bin_name, command in SERVO_COMMAND_BY_BIN.items():
            trigger = servo_triggers[bin_name]
            if detected_confidence[bin_name] >= SERVO_CONFIDENCE:
                trigger["confirmations"] += 1
                trigger["clear_frames"] = 0
            else:
                trigger["confirmations"] = 0
                trigger["clear_frames"] += 1
                if trigger["clear_frames"] >= SERVO_REARM_FRAMES:
                    trigger["latched"] = False

            if (
                trigger["confirmations"] >= SERVO_CONFIRM_FRAMES
                and not trigger["latched"]
                and now - trigger["last_attempt"] >= SERVO_COOLDOWN_SECONDS
            ):
                trigger["last_attempt"] = now
                trigger["latched"] = True
                commands_to_send.append(f"OPEN:{command}")

    for command in commands_to_send:
        threading.Thread(
            target=send_arduino_command,
            args=(command,),
            daemon=True,
        ).start()


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
    maybe_open_servo(detections)
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


@app.route("/api/arduino/status")
def api_arduino_status():
    return jsonify({
        **arduino_status,
        "configured": bool(ARDUINO_PORT),
        "port": ARDUINO_PORT,
        "servo_threshold": SERVO_CONFIDENCE,
        "confirm_frames": SERVO_CONFIRM_FRAMES,
        "rearm_frames": SERVO_REARM_FRAMES,
        "cooldown_seconds": SERVO_COOLDOWN_SECONDS,
        "bins": {
            bin_name: {
                "command": f"OPEN:{command}",
                "latched": servo_triggers[bin_name]["latched"],
            }
            for bin_name, command in SERVO_COMMAND_BY_BIN.items()
        },
    })


@app.route("/")
def index():
    return jsonify({
        "service": "waste-detector",
        "camera": "Flutter",
        "analysis": "Python / YOLO",
        "health": "/health",
        "predict": "/predict",
        "arduino_status": "/api/arduino/status",
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
