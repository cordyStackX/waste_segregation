# Waste Segregation

An AI-assisted waste segregation system made of three parts that work together:

| Part | Tech | Role |
|---|---|---|
| **Front end** | Flutter | User interface: live camera view, result display, status |
| **Brain** | Python + Ultralytics YOLO | Classifies the waste item from a camera image |
| **Controller** | C++ (Arduino) | Drives the hardware that physically sorts the waste |

```
                       ┌─────────┐
                       │ Camera  │  (opened ONLY by Python)
                       └────┬────┘
                            │ frames
                     ┌──────▼───────┐   GET /video (MJPEG stream)   ┌──────────┐
                     │ Python Brain │ ----------------------------> │ Flutter  │
                     │ YOLO11n-cls  │   GET /api/result (JSON)      │ Front end│
                     │ + Flask      │ ----------------------------> │          │
                     └──────┬───────┘                               └──────────┘
                            │ USB serial: sort command / status
                     ┌──────▼───────┐
                     │ Arduino (C++)│
                     │  Controller  │
                     └──────────────┘
```

The Python brain is the single source of truth. It owns the camera, runs the model, decides the class, and sends the sort command to the Arduino. Flutter only **displays** what Python reports and never opens the camera itself.

> The Flutter ↔ Python link (MJPEG stream plus JSON endpoint) is the chosen design. The Python ↔ Arduino serial protocol is still a proposal. Edit that section to match your sketch.

---

## How it works

1. The Python brain reads frames from the camera.
2. It runs a YOLO11 **classification** model on the frames (about 5 predictions per second) and gets a class with a confidence score.
3. The class is mapped to a bin: **biodegradable** or **non-biodegradable**.
4. The brain serves the annotated live video at `/video` and the latest result as JSON at `/api/result`.
5. The Flutter app shows the video and displays the class, confidence, and target bin.
6. The brain sends a sort command to the Arduino controller, which moves the sorting mechanism and reports its status back.

If the confidence is below the threshold (default 60%), the item is reported as `unsure` and no sort command should be sent.

---

## Repository structure

```
waste_segregation/
├── public/                  # Raw images, organized by category
│   ├── biodegradable/
│   │   ├── Food scraps/
│   │   └── fruit peels/
│   ├── non_biodegradable/
│   │   ├── cans/
│   │   ├── glass/
│   │   ├── paper/
│   │   ├── plastic/
│   │   └── Plastic bottles/
│   └── residual_special_waste/
├── build_dataset.py         # Builds dataset/ (train/val split) from public/
├── main.py                  # Trains the YOLO classifier
├── test.py                  # Classifies one or more image files
├── camera.py                # Live webcam classification (local window)
├── server.py                # Flask server: /video stream + /api/result for Flutter
├── dataset/                 # Generated, not committed
├── runs/                    # Training output, not committed
└── README.md
```

Add the Flutter app and the Arduino sketch folders here once they are in the repo (for example `app/` and `firmware/`).

---

## 1. Python brain

### Requirements

- Python 3.12 recommended (3.14 works but needs the `if __name__ == "__main__":` guard in training scripts)
- NVIDIA GPU optional, CPU also works but is slower
- Tested on Arch Linux with a GTX 960M (2 GB VRAM)

### Setup

```bash
python -m venv .venv
source .venv/bin/activate

# Install PyTorch FIRST. See "GPU notes" below if you have an older NVIDIA card.
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

pip install ultralytics
```

Verify the GPU:

```bash
python -c "import torch; print(torch.cuda.get_arch_list()); print(torch.ones(1).cuda()*2)"
```

#### GPU notes (Maxwell cards such as the GTX 960M)

The default PyTorch wheel can drop support for older GPUs. The GTX 960M is `sm_50`, so check that `sm_50` appears in `get_arch_list()`. If it does not, install from the `cu126` index as shown above (or pin an older torch version). Installing `ultralytics` afterwards can replace torch, so re-run the check at the end.

### Prepare the dataset

The raw images in `public/` are grouped as `group/class/`. YOLO classification needs a flat `train/` and `val/` layout, which `build_dataset.py` creates:

```bash
python build_dataset.py
```

What it does:

- Merges `Plastic bottles` into `plastic`, and `Food scraps` and `fruit peels` into `organic` (edit the `merge` dictionary to change this)
- Skips classes with fewer than 10 images
- Splits 80% train / 20% validation into `dataset/`

### Train

```bash
python main.py
```

Default settings (see `main.py`): `yolo11n-cls.pt`, 30 epochs, image size 224, batch 16, 2 workers, GPU 0. If you run out of VRAM, lower `batch`.

The trained model is saved under `runs/.../weights/best.pt`. Note that Ultralytics may prepend `runs/classify/` to a relative `project` path. Use an absolute `project` path for a predictable location.

### Test

```bash
python test.py path/to/photo.jpg
```

Prints the confidence for every class.

### Live camera

```bash
python camera.py
```

Press `q` to quit. Predictions are throttled (default 5 per second) to keep the GPU cool.

### Web server (camera stream and API for Flutter)

`server.py` is a small Flask app that keeps the camera and the model in Python and exposes them over HTTP, so the front end never touches the camera.

Extra dependencies:

```bash
pip install flask flask-cors
```

Run:

```bash
python server.py
```

It listens on `0.0.0.0:5000`.

| Endpoint | Returns | Used for |
|---|---|---|
| `GET /video` | MJPEG stream (`multipart/x-mixed-replace`) with the predicted label drawn on each frame | Showing the live camera in Flutter |
| `GET /api/result` | JSON with the latest prediction | Showing the class and bin in Flutter widgets, and driving the Arduino |

Example `/api/result` response:

```json
{ "label": "plastic", "conf": 0.91, "bin": "non-biodegradable" }
```

When the confidence is under 60%, `label` is `"unsure"` and `bin` is `null`.

Check it first in a browser: open `http://localhost:5000/video` and `http://localhost:5000/api/result` before connecting Flutter.

Notes:

- Only one program can open the camera at a time, so keep camera access in `server.py` and do not run `camera.py` at the same time.
- Use the laptop's LAN IP (not `localhost`) when connecting from a phone, and keep both devices on the same Wi-Fi.
- Bin mapping lives in the `BIN` dictionary in `server.py`.

### Classes and bin mapping

| Model class | Bin |
|---|---|
| organic | biodegradable |
| plastic | non-biodegradable |
| cans | non-biodegradable |

Paper and glass are not yet trained because the dataset has too few images for them.

### Improving accuracy

- Collect at least 100 images per class
- Add public datasets (for example TrashNet or other waste-classification sets). Check each license first
- Include photos from your own camera and setup, since they match what the system will see in use
- Retrain with more epochs (for example 50 with `patience=20`)

---

## 2. Flutter front end

> Fill in the app folder details once it is added to the repo.

Responsibilities:

- Show the live camera feed from the Python brain (`/video`)
- Poll `/api/result` and display the predicted class, confidence, and target bin
- Show the controller status (idle, sorting, error)

The app does **not** open the camera. All camera access and inference stay in Python.

### Setup

```bash
cd app
flutter pub get
flutter run
```

### Configuration

Set the address of the Python brain in the app config:

```
BRAIN_URL=http://<laptop-lan-ip>:5000
```

Do not use `localhost` from a phone or emulator. Use the laptop's LAN IP, with both devices on the same Wi-Fi. (The Android emulator reaches the host machine at `10.0.2.2`.)

### Showing the camera stream

| Target | Approach |
|---|---|
| Flutter Web | Embed `BRAIN_URL/video` in an iframe (`HtmlElementView`) or an `<img>` element |
| Android / iOS | Use `webview_flutter` pointing at `BRAIN_URL/video`, or an MJPEG widget package |

### Reading the result

Poll `BRAIN_URL/api/result` a few times per second (for example every 300 ms) and update the UI from the JSON:

```json
{ "label": "plastic", "conf": 0.91, "bin": "non-biodegradable" }
```

### Development notes

- **Android blocks plain `http://` by default.** For development, set `android:usesCleartextTraffic="true"` in `AndroidManifest.xml`.
- **Flutter Web served over https cannot load an http stream** (mixed content). Serve both over http during development, or put both behind https later.
- CORS is already enabled on the Flask server through `flask-cors`.

---

## 3. Arduino controller (C++)

> Fill in once the firmware folder is added to the repo.

Planned responsibilities:

- Receive a sort command from the brain over serial
- Move the sorting mechanism (servo or motor) to the correct bin
- Report status back (done, busy, error)

### Setup

1. Open the sketch in the Arduino IDE or use `arduino-cli`
2. Select your board and port
3. Upload

### How the brain talks to the Arduino

The Python brain sends the sort command over USB serial (for example with `pyserial`, `pip install pyserial`) after a confident prediction, and waits for the Arduino's reply. The Arduino is never sent a command while the label is `unsure`. Linux usually exposes the board as `/dev/ttyUSB0` or `/dev/ttyACM0`, and your user may need to be in the `uucp` group (Arch) to open it.

### Serial protocol (proposed)

| Direction | Message | Meaning |
|---|---|---|
| Brain → Arduino | `SORT:BIO` | Route item to the biodegradable bin |
| Brain → Arduino | `SORT:NONBIO` | Route item to the non-biodegradable bin |
| Arduino → Brain | `OK` | Sort completed |
| Arduino → Brain | `ERR:<reason>` | Something failed |

Baud rate: `9600` (adjust to match the sketch).

### Wiring

Add a pin table here, for example:

| Component | Arduino pin |
|---|---|
| Servo signal | D9 |
| Sensor | D2 |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `no kernel image is available for execution on the device` | Your PyTorch build does not support your GPU. Reinstall from the `cu126` index and check `get_arch_list()` |
| `dataset/data.yaml does not exist` | You are using the detection config. For classification use `data="dataset"` with `yolo11n-cls.pt` |
| `ConnectionResetError` during training on Python 3.14 | Wrap training in `def main()` and `if __name__ == "__main__":`, or set `workers=0`, or use Python 3.12 |
| CUDA out of memory | Lower `batch` or `imgsz` |
| Camera does not open | Try `VideoCapture(1)`, check `ls /dev/video*`, or run with `QT_QPA_PLATFORM=xcb` |
| Model predicts wrong class for paper or glass | Those classes are not trained yet. Add data and retrain |
| `/video` is blank, or the camera will not open in `server.py` | Another program (such as `camera.py`) is holding the camera. Close it, or change the index in `VideoCapture(0)` |
| Flutter cannot reach the server from a phone | Use the laptop's LAN IP instead of `localhost`, keep both on the same Wi-Fi, and allow port 5000 through the firewall |
| Android app cannot load `http://` URLs | Add `android:usesCleartextTraffic="true"` to the manifest for development |
| Flutter Web shows nothing from an https page | Browsers block http streams on https pages. Serve both over http, or both over https |
| `Permission denied: /dev/ttyUSB0` (or `ttyACM0`) | Add your user to the `uucp` group on Arch and log in again |

---

## Roadmap

- [ ] Add paper and glass classes with more data
- [ ] Retrain with camera frames from the real hardware setup
- [x] Choose the Flutter ↔ Python design (MJPEG `/video` plus JSON `/api/result`)
- [ ] Build the Flutter screens that show the stream and the result
- [ ] Finalize the Python ↔ Arduino serial protocol and add it to `server.py`
- [ ] Only send sort commands for confident predictions, and debounce repeated detections of the same item
- [ ] Add a low-confidence rejection path in the hardware (send the item to a "check manually" bin)
- [ ] Consider object detection if multiple items must be handled in one frame

---

## Team

| Role | Name |
|---|---|
| Flutter front end | _add name_ |
| Python / AI brain | _add name_ |
| Arduino / C++ controller | _add name_ |

## License

_Add a license (for example MIT). If you use third-party datasets, follow their licenses._