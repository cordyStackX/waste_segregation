# Waste Segregation

An AI-assisted waste segregation system made of three parts that work together:

| Part | Tech | Role |
|---|---|---|
| **Front end** | Flutter | Opens the camera, shows the live view, and draws detections |
| **Brain** | Python + Ultralytics YOLO + Flask | Analyzes uploaded frames and returns item boxes and target bins |
| **Controller** | C++ (Arduino) | Receives commands and operates one servo lid for each waste bin |

```
 Camera → Flutter app ── JPEG frames ──> Python + YOLO
              ▲                            │
              └──── boxes, bins, labels ───┘

 Arduino controller (optional, separate from the detection app)
```

Flutter owns camera capture and the preview. Python only runs inference and maps detailed detector classes to bins. The Arduino controller is a separate optional part of the project.

The model sorts each item into one of three categories:

| Category | Examples |
|---|---|
| `biodegradable` | food scraps, fruit peels, paper |
| `non_biodegradable` | cans, glass, plastic, plastic bottles |
| `residual_special_waste` | items that fit neither of the other two |

---

## Quick start

Tested on Arch Linux. Run the setup once, then use `run.sh` for everything else.

```bash
chmod +x setup.sh run.sh
./setup.sh              # virtual env, PyTorch, packages, Arduino core, Flutter deps
./run.sh all            # start Flutter + Python, connected to the detected Arduino
```

| Command | What it does |
|---|---|
| `./setup.sh` | One-time setup. Use `./setup.sh --cpu` for a CPU-only PyTorch build |
| `./run.sh server` | Start the Python analysis API and print its URL |
| `./run.sh camera` | Local OpenCV window with live predictions |
| `./run.sh dataset` | Build `detection_dataset/` from images and annotations |
| `./run.sh train` | Build the detection dataset, then train YOLO |
| `./run.sh test photo.jpg` | Detect waste items in image files |
| `./run.sh app` | Run the Flutter app, pointed at this machine |
| `./run.sh all` | Server, Flutter, and detected Arduino together (Ctrl+C stops both) |
| `./run.sh arduino compile` | Compile the sketch |
| `./run.sh arduino upload` | Compile and upload (auto-detects the port) |
| `./run.sh arduino monitor` | Serial monitor at 9600 baud |

Overrides go before the command, for example `DEVICE=chrome ./run.sh app`, `BRAIN_URL=http://127.0.0.1:5000 ./run.sh app`, `PORT=/dev/ttyUSB0 ./run.sh arduino upload`, or `WASTE_ARDUINO_PORT=/dev/ttyUSB0 ./run.sh all`. The Arduino firmware must already be uploaded; `all` checks the board with `PING` but does not flash it. Run `./run.sh help` for the full list.

---

## How it works

1. Flutter opens the device camera and captures frames.
2. Flutter posts each JPEG to Python's `/predict` endpoint.
3. Python runs the `waste_detailed-4` YOLO detector and maps each detected class to a bin.
4. Python returns frame-sized bounding boxes, class names, confidence scores, and bin codes.
5. Flutter draws the boxes over its preview and shows the predicted bin.

The default detection confidence threshold is 35% and can be changed with `WASTE_CONFIDENCE`.

---

## Repository structure

```
waste_segregation/
├── .github/workflows/       # CI/CD (python, flutter, arduino, release)
├── arduino/
│   └── arduino.ino          # Controller sketch (folder and file names must match)
├── flutter/                 # Flutter app (pubspec.yaml lives here)
│   └── lib/main.dart
├── public/                  # Raw images, organized by category
│   ├── biodegradable/
│   │   ├── Food scraps/
│   │   └── fruit peels/
│   ├── non_biodegradable/
│   │   ├── cans/
│   │   ├── glass/
│   │   ├── paper/              # paper is routed to biodegradable by the app
│   │   ├── plastic/
│   │   └── Plastic bottles/
│   ├── residual_special_waste/
│   └── captured/            # Optional: frames saved from your own camera
├── build_dataset.py         # Builds detection_dataset/ and writes bin mappings
├── train_detection.py       # Trains the detailed YOLO detector
├── test.py                  # Tests a YOLO model on image files
├── camera.py                # Live local OpenCV detection preview
├── iframe_embeded.py        # Flask inference API: /health + /predict
├── setup.sh                 # One-time setup
├── run.sh                   # Day-to-day commands
├── detection_dataset/       # Generated, not committed
├── runs/                    # Training output, not committed
└── README.md
```

`detection_dataset/`, `runs/`, and `*.pt` should be listed in `.gitignore`.

---

## 1. Python brain

### Requirements

- Python 3.12 recommended (3.14 works, but training scripts need the `if __name__ == "__main__":` guard)
- NVIDIA GPU optional. CPU also works but is slower
- Tested on Arch Linux with a GTX 960M (2 GB VRAM)

### Setup

`./setup.sh` does all of this. To do it by hand:

```bash
python -m venv .venv
source .venv/bin/activate

# Install PyTorch FIRST. See "GPU notes" below if you have an older NVIDIA card.
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

pip install ultralytics flask flask-cors pyserial
```

Verify the GPU:

```bash
python -c "import torch; print(torch.cuda.get_arch_list()); print(torch.ones(1).cuda()*2)"
```

#### GPU notes (Maxwell cards such as the GTX 960M)

The default PyTorch wheel can drop support for older GPUs. The GTX 960M is `sm_50`, so check that `sm_50` appears in `get_arch_list()`. If it does not, install from the `cu126` index as shown above (or pin an older torch version). Installing `ultralytics` afterwards can replace torch, so re-run the check at the end.

### Prepare and train the detector

The object detector uses images in `public/` and YOLO bounding boxes in the matching paths under `annotations_detailed/`. Build the detection dataset with:

```bash
python build_dataset.py
```

It splits labeled images into `detection_dataset/images/{train,val}` and `labels/{train,val}`, and writes `bin_by_class.json` for the inference API. To convert older box labels and review them, use:

```bash
python migrate_annotations.py
python annotate.py
```

The migration preserves box coordinates and infers detailed classes from the image folder. Review labels in `annotate.py`, then train with:

```bash
./run.sh train
```

Training writes weights under `runs/detect/waste_detailed/weights/`. Live analysis defaults to `runs/detect/waste_detailed-4/weights/best.pt`; set `WASTE_DETECTION_MODEL` if you want to use a different checkpoint.

Avoid near-duplicate photos on both sides of the train/validation split, because they can make validation results look better than real-world detection.

### Test

```bash
python test.py path/to/photo.jpg
```

Prints detected items, bounding boxes, bin names, and confidence scores.

### Live camera

```bash
python camera.py
```

Press `q` to quit. Press `f` to toggle fullscreen.

### Python analysis API

`iframe_embeded.py` loads the `waste_detailed-4` detector and accepts JPEG frames from Flutter. It does not open a camera. The Flutter app captures camera frames locally and sends them to Python for detection and bin mapping.

```bash
./run.sh server
```

The API listens on `0.0.0.0:5000` and loads `runs/detect/waste_detailed-4/weights/best.pt`.

| Endpoint | Returns | Used for |
|---|---|---|
| `GET /health` | Model name, classes, confidence, and readiness | Checking the Python service from Flutter |
| `POST /predict` | Detection boxes and bin codes for a raw JPEG request body | Flutter uploads each captured frame here |
| `GET /api/result` | The most recent prediction | Compatibility with older clients |
| `GET /api/arduino/status` | Arduino connection, servo threshold, and last action | Checking the USB-connected controller |

Example `/predict` response:

```json
{
  "width": 640,
  "height": 480,
  "detections": [
    { "label": "non_biodegradable", "type": "plastic_bottles", "conf": 0.91,
      "bin": "non_biodegradable", "box": [120, 70, 390, 440] }
  ]
}
```

Set `WASTE_CONFIDENCE` and `WASTE_IMAGE_SIZE` to tune inference. Defaults are 0.35 confidence and 512-pixel inference size.

### Improving accuracy

- Collect at least 100 images per class, and keep the classes balanced
- Add examples captured with the same camera and lighting used by the app, varying angle, distance, and background
- Add public datasets (for example TrashNet or other waste-classification sets). Check each license first
- Retrain after adding data, and test on the live camera

---

## 2. Flutter camera and scan UI

The Flutter app owns camera access and the live preview. On Linux it samples the camera's live frame stream, resizes and JPEG-encodes frames in memory, then sends them to Python's `/predict` endpoint. It does not take and save a new photo for every prediction. The app draws returned boxes and bin labels over the preview and provides pause/resume, camera switching, a Python connection status, and an in-app server address setting.

### Arch Linux camera setup

Install the GStreamer libraries required by the Linux camera plugin:

```bash
sudo pacman -S gstreamer gst-plugins-base gst-plugins-good
```

Make sure the current user can access the camera device, usually `/dev/video0`. The Python server does not open the camera, so it can run at the same time as the Flutter app.

### Run the app and detector

```bash
./run.sh all       # starts the Python API, Flutter app, and links the detected Arduino
```

Or start each process separately:

```bash
./run.sh server
./run.sh app
```

The default detector address is filled in by `run.sh`, the API uses HTTP by default, and inference automatically selects CUDA when available or CPU otherwise. Override the inference device with `WASTE_DEVICE` (for example, `WASTE_DEVICE=cpu ./run.sh server`). For a USB-connected Android phone, enable USB debugging, confirm its ID with `flutter devices`, run `adb reverse tcp:5000 tcp:5000`, then launch with `DEVICE=<phone-id> BRAIN_URL=http://127.0.0.1:5000 ./run.sh app`. The reverse forwards the phone's localhost API requests to the computer without opening the API to the Wi-Fi network. For Wi-Fi instead, connect both devices to the same network and use the computer's reachable LAN address, for example `BRAIN_URL=http://192.168.1.20:5000`; allow port 5000 through the firewall if needed. The Android manifest permits cleartext HTTP for local development. Set `HTTPS=1` when starting `./run.sh server` only when HTTPS is needed.

To serve a web build from Python, run `cd flutter && flutter build web -t lib/main_web.dart --base-href /app/`, then open `/app/` from the same computer. Browsers require HTTPS for camera access on non-localhost network addresses.

---

## 3. Arduino controller (C++)

The controller uses three SG90 servo motors, one for each bin. The Uno has no Wi-Fi, so Flask sends USB serial commands after YOLO confidently identifies an item.

### Wiring

| Part | Connection |
|---|---|
| Biodegradable servo signal (orange/yellow) | Arduino D9 |
| Non-biodegradable servo signal (orange/yellow) | Arduino D10 |
| Residual/special waste servo signal (orange/yellow) | Arduino D11 |
| All servo power wires (red) | Separate regulated 5 V supply; do not use the Uno 5 V pin |
| All servo ground wires (brown/black) | Supply GND and Arduino GND connected together |

Size the 5 V supply for the combined stall current of all three servos.

### Upload

```bash
./run.sh arduino upload
# or manually:
arduino-cli compile --fqbn arduino:avr:uno arduino
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno arduino
```

The folder and the `.ino` file must share a name (`arduino/arduino.ino`). Compile from the repo root, or use `.` if you are inside `arduino/`. Change `--fqbn` (or `FQBN=...`) if you are not using an Uno.

### Serial protocol

Text commands, one per line, at **9600 baud**.

| Direction | Message | Meaning |
|---|---|---|
| Arduino → Brain | `READY` | Sent at power-on |
| Brain → Arduino | `PING` | Connection check. Reply: `PONG` |
| Brain → Arduino | `OPEN:BIO` | Open biodegradable lid; auto-closes after 1.8 seconds. Reply: `OK:OPEN:BIO` |
| Brain → Arduino | `OPEN:NONBIO` | Open non-biodegradable lid; reply: `OK:OPEN:NONBIO` |
| Brain → Arduino | `OPEN:RESIDUAL` | Open residual/special-waste lid; reply: `OK:OPEN:RESIDUAL` |
| Brain → Arduino | `CLOSE:BIO`, `CLOSE:NONBIO`, `CLOSE:RESIDUAL` | Close the selected lid |
| Brain → Arduino | `CLOSE:ALL` / `OFF` | Close all lids. Reply: `OK:CLOSE:ALL` |
| Arduino → Brain | `ERR:BAD_CMD` / `ERR:TOO_LONG` | Unknown or oversized command |

### Test by hand

```bash
./run.sh arduino monitor
```

Type `PING` (expect `PONG`), then `OPEN:BIO`, `OPEN:NONBIO`, and `OPEN:RESIDUAL` to exercise each lid. Close the monitor before running Python, because only one program can hold the port.

### Python API and automatic servo trigger

The Arduino Uno does not make HTTP requests itself. Flutter sends each camera frame to `POST /predict`; Flask runs YOLO and sends the matching `OPEN:*` command over USB serial when a bin detection is at least 70% confident for three consecutive predictions. Each bin is tracked independently. It requires eight consecutive predictions without a qualifying detection for that bin before re-arming, and applies an 8-second cooldown per bin.

Configure the serial port before starting the Python server:

```bash
WASTE_ARDUINO_PORT=/dev/ttyACM0 ./run.sh server
```

On Arch, a clone may appear as `/dev/ttyUSB0`. The Uno resets when its serial port opens, so the server waits for it to start before sending a command. Lids open to 90 degrees and close after 1.8 seconds; adjust `SERVO_OPEN_ANGLE`, `SERVO_CLOSED_ANGLE`, and `SERVO_OPEN_MS` in `arduino/arduino.ino` to fit the mechanisms.

Check the controller configuration and last action with:

```bash
curl http://127.0.0.1:5000/api/arduino/status
```

Threshold and timing can be configured with `WASTE_SERVO_CONFIDENCE`, `WASTE_SERVO_CONFIRM_FRAMES`, `WASTE_SERVO_REARM_FRAMES`, and `WASTE_SERVO_COOLDOWN`.

Linux usually exposes the board as `/dev/ttyACM0` (or `/dev/ttyUSB0` for clones). On Arch your user must be in the `uucp` group: `sudo usermod -aG uucp $USER`, then log out and back in.

---

## CI/CD

GitHub Actions workflows live in `.github/workflows/`. Each one only runs when its own folder changes.

| Workflow | Runs when | What it does |
|---|---|---|
| `python.yml` | `.py` files change | Lints for real errors (syntax, undefined names) and byte-compiles the scripts |
| `flutter.yml` | `flutter/` changes | `pub get`, `analyze`, `test` (if tests exist), builds a release APK and uploads it as an artifact |
| `arduino.yml` | `arduino/` changes | Compiles the sketch for the Uno |
| `release.yml` | you push a tag like `v0.1.0` | Builds the APK and attaches it, plus `brain.zip` and `firmware.zip`, to a GitHub Release |

Publish a release:

```bash
git tag v0.1.0 && git push origin v0.1.0
```

Limits to know about:

- **No model training in CI.** Runners have no GPU, and the dataset and weights are not committed. Train locally and attach `best.pt` to a release by hand.
- **The release APK is debug-signed.** That is fine for testing. For store distribution, add a keystore through GitHub secrets.
- The Python lint is intentionally lenient. Tighten it as the code settles.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `no kernel image is available for execution on the device` | Your PyTorch build does not support your GPU. Reinstall from the `cu126` index and check `get_arch_list()` |
| `detection_dataset/data.yaml` does not exist | Run `./run.sh dataset` and check that labeled images exist under `public/` with matching labels under `annotations_detailed/` |
| `ConnectionResetError` during training on Python 3.14 | Wrap training in `def main()` and `if __name__ == "__main__":`, or set `workers=0`, or use Python 3.12 |
| CUDA out of memory | Lower `batch` or `imgsz` |
| Flutter camera does not open on Arch | Install `gstreamer`, `gst-plugins-base`, and `gst-plugins-good`; check `ls -l /dev/video*` and that your user can read the camera device; run `flutter pub get` and rebuild |
| Flutter says “Python detector unavailable” | Start `./run.sh server`, check `http://127.0.0.1:5000/health`, and set the Python address in app settings if the server is on another device |
| `/predict` returns 400 | Flutter must send JPEG bytes as the request body with `Content-Type: image/jpeg` |
| Flutter cannot reach the server from a phone | Use the laptop's LAN IP instead of `localhost`, keep both on the same Wi-Fi, and allow port 5000 through the firewall |
| Android app cannot load `http://` URLs, or release APK is offline | Add the `INTERNET` permission and `android:usesCleartextTraffic="true"` to the manifest |
| `Can't open sketch: no such file or directory` | Run the compile from the repo root with `arduino`, or from inside `arduino/` with `.` |
| `arduino-cli board list` says `No boards found` | No board connected, or a charge-only USB cable. Use a data cable and check `ls /dev/ttyACM* /dev/ttyUSB*` |
| `Permission denied: /dev/ttyUSB0` (or `ttyACM0`) | Add your user to the `uucp` group on Arch and log in again |
| `Servo.h: No such file or directory` | Install the Servo library with `arduino-cli lib install Servo` |
| Predictions are inaccurate on the live camera | Not enough data from your own camera. Capture more varied frames and retrain |

---

## Roadmap

- [x] Flutter camera with Python YOLO frame analysis (`POST /predict`)
- [x] Arduino SG90 controller with a serial protocol
- [x] CI/CD workflows and `setup.sh` / `run.sh`
- [ ] Add images for `residual_special_waste` and balance the three classes (100+ each)
- [ ] Retrain with more varied frames from the real camera setup
- [ ] Test camera capture on Linux, Chrome over HTTPS, and a phone
- [x] Add confidence-gated lid servo control for all three bins through Python → Arduino USB serial
- [ ] Add a presence sensor so the controller only sorts when an item is there
- [ ] Add a low-confidence rejection path in the hardware (send the item to a "check manually" bin)

---

## Team

| Role | Name |
|---|---|
| Flutter front end | _add name_ |
| Python / AI brain | _add name_ |
| Arduino / C++ controller | _add name_ |

## License

_Add a license (for example MIT). If you use third-party datasets, follow their licenses._
