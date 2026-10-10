import time, threading, cv2
from flask import Flask, Response, jsonify
from flask_cors import CORS          # pip install flask flask-cors
from ultralytics import YOLO

MODEL = "runs/classify/runs/waste/experiment-3/weights/best.pt"
BIN = {"organic": "biodegradable", "plastic": "non-biodegradable", "cans": "non-biodegradable"}

app = Flask(__name__)
CORS(app)
model = YOLO(MODEL)
cap = cv2.VideoCapture(0)

state = {"label": "...", "conf": 0.0, "bin": None}
latest_jpg = None

def worker():
    global latest_jpg
    last = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.1)
            continue
        if time.time() - last >= 0.2:            # 5 predictions/sec
            r = model.predict(frame, device=0, imgsz=224, verbose=False)[0]
            conf = float(r.probs.top1conf)
            label = r.names[r.probs.top1] if conf >= 0.6 else "unsure"
            state.update(label=label, conf=conf, bin=BIN.get(label))
            last = time.time()
        cv2.putText(frame, f"{state['label']} {state['conf']:.0%}", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
        latest_jpg = cv2.imencode(".jpg", frame)[1].tobytes()
        time.sleep(0.03)

@app.route("/video")
def video():
    def gen():
        while True:
            if latest_jpg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + latest_jpg + b"\r\n"
            time.sleep(0.05)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/result")
def result():
    return jsonify(state)

@app.route("/")
def index():
    return """
    <html>
      <body style="margin:0;background:#111;color:#fff;font-family:sans-serif;text-align:center">
        <h2>Waste Classifier</h2>
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
    threading.Thread(target=worker, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True) 