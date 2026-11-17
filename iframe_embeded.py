"""Waste detector server: the phone's camera streams frames here, YOLO runs on the laptop.

Open https://<laptop-ip>:5000 on the iPhone, tap "Start camera".
Flutter web wrapper (iframe) is served at https://<laptop-ip>:5000/app/
iOS Safari only allows camera access over HTTPS, so this serves HTTPS (self-signed by
default; needs `pip install cryptography`).
"""

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
    "runs/detect/waste_detailed/weights/best.pt",
))
DEVICE = os.getenv("DEVICE", "0")
CONFIDENCE = 0.35
IMAGE_SIZE = 640
PORT = int(os.getenv("PORT", "5000"))
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
            "label": label,
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


PAGE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Waste Detector</title>
  <style>
    body { margin:0; background:#111; color:#fff; font-family:-apple-system, sans-serif; text-align:center; }
    h2 { margin:12px 0; }
    .wrap { position:relative; width:100%; max-width:720px; margin:0 auto; background:#000; }
    video { display:block; width:100%; }
    canvas#overlay { position:absolute; inset:0; width:100%; height:100%; }
    button { margin:14px; padding:14px 28px; font-size:18px; border:0; border-radius:10px; background:#3cdc50; color:#000; }
    #top { font-size:22px; font-weight:600; min-height:30px; margin:8px 12px; color:#3cdc50; }
    pre { text-align:left; margin:8px 12px; font-size:12px; white-space:pre-wrap; color:#aaa; }
  </style>
</head>
<body>
  <h2>Waste Detector</h2>
  <div class="wrap">
    <video id="cam" playsinline muted autoplay></video>
    <canvas id="overlay"></canvas>
  </div>
  <button id="start">Start camera</button>
  <div id="top"></div>
  <pre id="out"></pre>
  <script>
    const SEND_WIDTH = 640;
    const LABEL_GREEN = "#3cdc50";  // label text color (change to taste)
    const COLORS = { biodegradable: "#3cdc50", non_biodegradable: "#ffaa1e", residual_special_waste: "#f03232" };
    const video = document.getElementById("cam");
    const overlay = document.getElementById("overlay");
    const octx = overlay.getContext("2d");
    const topEl = document.getElementById("top");
    const out = document.getElementById("out");
    const grab = document.createElement("canvas");
    const gctx = grab.getContext("2d");
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    document.getElementById("start").onclick = async (e) => {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        out.textContent = "Camera API unavailable. This page must be opened over https://";
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
          audio: false,
        });
        video.srcObject = stream;
        await video.play();
        e.target.style.display = "none";
        loop();
      } catch (err) {
        out.textContent = "Camera error: " + err.message;
      }
    };

    function draw(data, vw, vh) {
      overlay.width = vw;
      overlay.height = vh;
      octx.clearRect(0, 0, vw, vh);
      const f = vw / data.width;
      octx.lineWidth = Math.max(2, vw / 300);
      const fontPx = Math.round(vw / 22);
      const pad = Math.max(4, Math.round(vw / 120));
      octx.font = `bold ${fontPx}px sans-serif`;
      octx.textBaseline = "top";
      for (const d of data.detections) {
        const [x1, y1, x2, y2] = d.box.map((v) => v * f);
        octx.strokeStyle = COLORS[d.bin] || "#ffffff";
        octx.strokeRect(x1, y1, x2 - x1, y2 - y1);

        // Label: solid green tag with black text, so it is readable on any background.
        const text = `${d.label} ${Math.round(d.conf * 100)}%`;
        const tagW = octx.measureText(text).width + pad * 2;
        const tagH = fontPx + pad * 2;
        const tagY = y1 - tagH >= 0 ? y1 - tagH : y1;  // flip inside the box at the top edge
        octx.fillStyle = LABEL_GREEN;
        octx.fillRect(x1, tagY, tagW, tagH);
        octx.fillStyle = "#000";
        octx.fillText(text, x1 + pad, tagY + pad);
      }
      if (data.detections.length) {
        topEl.textContent = `${data.label} (${Math.round(data.conf * 100)}%) → ${data.bin}`;
        topEl.style.color = LABEL_GREEN;
      } else {
        topEl.textContent = "unsure";
        topEl.style.color = "#aaa";
      }
      out.textContent = JSON.stringify(data.detections.map((d) => ({ label: d.label, bin: d.bin, conf: +d.conf.toFixed(2) })), null, 1);
    }

    async function loop() {
      const vw = video.videoWidth, vh = video.videoHeight;
      if (vw) {
        const s = Math.min(1, SEND_WIDTH / vw);
        grab.width = Math.round(vw * s);
        grab.height = Math.round(vh * s);
        gctx.drawImage(video, 0, 0, grab.width, grab.height);
        const blob = await new Promise((r) => grab.toBlob(r, "image/jpeg", 0.7));
        try {
          const res = await fetch("/predict", { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: blob });
          draw(await res.json(), vw, vh);
        } catch (err) {
          out.textContent = "Server error: " + err.message;
          await sleep(500);
        }
      }
      setTimeout(loop, 50); // waits for each response first, so requests never pile up
    }
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return PAGE


@app.route("/app/")
@app.route("/app/<path:p>")
def flutter_app(p="index.html"):
    """Serves the Flutter web build (which embeds the detector page in an iframe)."""
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
    print(f"\nOpen on your iPhone (same Wi-Fi): {scheme}://{lan_ip()}:{PORT}")
    print(f"Flutter web app:                  {scheme}://{lan_ip()}:{PORT}/app/\n")
    app.run(host="0.0.0.0", port=PORT, threaded=True, ssl_context=ssl_context)