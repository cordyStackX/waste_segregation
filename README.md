# Waste Segregation

An AI-assisted waste segregation system made of three parts that work together:

| Part | Tech | Role |
|---|---|---|
| **Front end** | Flutter | Shows the live camera view, the detected class, and the target bin |
| **Brain** | Python + Ultralytics YOLO + Flask | Classifies the waste item from the camera and serves the results |
| **Controller** | C++ (Arduino) | Receives sort commands and drives the hardware (LEDs now, servos later) |

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

The model sorts each item into one of three categories:

| Category | Examples |
|---|---|
| `biodegradable` | food scraps, fruit peels |
| `non_biodegradable` | cans, glass, paper, plastic, plastic bottles |
| `residual_special_waste` | items that fit neither of the other two |

---

## Quick start

Tested on Arch Linux. Run the setup once, then use `run.sh` for everything else.

```bash
chmod +x setup.sh run.sh
./setup.sh              # virtual env, PyTorch, packages, Arduino core, Flutter deps
./run.sh server         # start the camera + model + web API
```

| Command | What it does |
|---|---|
| `./setup.sh` | One-time setup. Use `./setup.sh --cpu` for a CPU-only PyTorch build |
| `./run.sh server` | Start the Python brain (default command) and print its URL |
| `./run.sh camera` | Local OpenCV window with live predictions |
| `./run.sh dataset` | Build `dataset/` from `public/` |
| `./run.sh train` | Build the dataset, then train the model |
| `./run.sh test photo.jpg` | Classify image files |
| `./run.sh app` | Run the Flutter app, pointed at this machine |
| `./run.sh all` | Server and Flutter app together (Ctrl+C stops both) |
| `./run.sh arduino compile` | Compile the sketch |
| `./run.sh arduino upload` | Compile and upload (auto-detects the port) |
| `./run.sh arduino monitor` | Serial monitor at 9600 baud |

Overrides go before the command, for example `DEVICE=chrome ./run.sh app` or `PORT=/dev/ttyUSB0 ./run.sh arduino upload`. Run `./run.sh help` for the full list.

---

## How it works

1. The Python brain reads frames from the camera.
2. It runs a YOLO11 **classification** model on the frames (about 5 predictions per second) and gets a class with a confidence score.
3. The predicted class is the target bin: `biodegradable`, `non_biodegradable`, or `residual_special_waste`.
4. The brain serves the annotated live video at `/video` and the latest result as JSON at `/api/result`.
5. The Flutter app shows the video and displays the class, confidence, and bin.
6. For a confident, stable prediction the brain sends a sort command to the Arduino, which lights the matching LED (later, moves the sorting mechanism) and replies `OK`.

If the confidence is below the threshold (default 60%), the item is reported as `unsure` and no sort command is sent.

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
│   │   ├── paper/
│   │   ├── plastic/
│   │   └── Plastic bottles/
│   ├── residual_special_waste/
│   └── captured/            # Optional: frames saved from your own camera
├── build_dataset.py         # Builds dataset/ (train/val split) from public/
├── main.py                  # Trains the YOLO classifier
├── test.py                  # Classifies one or more image files
├── camera.py                # Live webcam classification (local window)
├── iframe_embeded.py        # Flask server: /video stream + /api/result for Flutter
├── setup.sh                 # One-time setup
├── run.sh                   # Day-to-day commands
├── dataset/                 # Generated, not committed
├── runs/                    # Training output, not committed
└── README.md
```

`dataset/`, `runs/`, and `*.pt` should be listed in `.gitignore`.

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

### Prepare the dataset

The raw images in `public/` are grouped as `group/class/`. YOLO classification needs a flat `train/` and `val/` layout, which `build_dataset.py` creates:

```bash
python build_dataset.py
```

What it does:

- **`MODE = "group"` (default):** the three top-level folders are the classes (`biodegradable`, `non_biodegradable`, `residual_special_waste`). Loose images sitting directly in a group folder are included.
- **`MODE = "leaf"`:** uses the detailed folders (cans, plastic, organic, ...) as classes. In this mode `Plastic bottles` merges into `plastic`, and `Food scraps` and `fruit peels` merge into `organic`. Edit the `merge` dictionary to change this, and map the result to a bin in code.
- **Captured frames:** images saved under `public/captured/<class>/` are mapped to a group through the `captured_map` dictionary.
- Skips classes with fewer than 10 images (a class with no images, like an empty `residual_special_waste`, is skipped with a message).
- Splits 80% train / 20% validation into `dataset/`.

Make sure each class has images in the right folder. For example, residual items such as `rsw-*.jpg` belong in `public/residual_special_waste/`.

### Train

```bash
python main.py
```

Default settings (see `main.py`): `yolo11n-cls.pt`, 50 epochs with `patience=20`, image size 224, batch 16, 2 workers, GPU 0. If you run out of VRAM, lower `batch`.

The model is saved to `runs/waste/groups/weights/best.pt` (the script uses an absolute `project` path, because Ultralytics prepends `runs/classify/` to a relative one). Older runs under `runs/classify/` can be deleted.

### Reading the training results

- **`top1_acc`** is the share of validation images the model got right.
- **`top5_acc`** is meaningless with 3 classes, because it is always 1.0.
- With a small validation set (about 20 images), one image changes the score by about 5 points, so the curves jump around. Do not trust the numbers much. Judge the model on the live camera.
- Avoid near-duplicate photos on both sides of the split, because they make validation look better than it is.

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

`iframe_embeded.py` is a small Flask app that keeps the camera and the model in Python and exposes them over HTTP, so the front end never touches the camera.

```bash
./run.sh server        # or: python iframe_embeded.py
```

It listens on `0.0.0.0:5000`.

| Endpoint | Returns | Used for |
|---|---|---|
| `GET /` | Simple test page with the video, the live JSON, and capture buttons | Checking everything in a browser |
| `GET /video` | MJPEG stream (`multipart/x-mixed-replace`) with the predicted label drawn on each frame | Showing the live camera in Flutter |
| `GET /api/result` | JSON with the latest prediction | Showing the class and bin in Flutter, and driving the Arduino |
| `GET /capture/<class>` | Saves the current raw frame to `public/captured/<class>/` | Collecting your own training photos |

Example `/api/result` response:

```json
{ "label": "non_biodegradable", "conf": 0.91, "bin": "non_biodegradable" }
```

When the confidence is under 60%, `label` is `"unsure"` and `bin` is `null`.

Notes:

- Only one program can open the camera at a time. Do not run `camera.py` while the server is running.
- Use the laptop's LAN IP (not `localhost`) when connecting from a phone, and keep both devices on the same Wi-Fi.
- The bin mapping lives in the `BIN` dictionary in `iframe_embeded.py`.
- The model path is set by `MODEL` near the top of the file.

### Improving accuracy

- Collect at least 100 images per class, and keep the classes balanced
- Capture frames from your own camera and setup (`/capture/<class>`), because they match what the system sees in use. Vary the angle, distance, lighting, and background, and use many different examples of each type
- Consider an `empty` class (camera pointing at the empty bin), so the model has an answer when there is no item
- Add public datasets (for example TrashNet or other waste-classification sets). Check each license first
- Retrain after adding data, and test on the live camera

---

## 2. Flutter front end

The app shows the live stream and a result card (bin, detected label, confidence bar). A wifi icon shows whether the server is reachable, and a settings button changes the server address inside the app.

The app does **not** open the camera. All camera access and inference stay in Python.

### Create the project (first time only)

```bash
cd flutter
flutter create --project-name waste_app --org com.cordystackx --platforms=android,linux,web --empty .
flutter pub add flutter_mjpeg http
```

Then use `lib/main.dart` from the repo for the app code.

### Android permissions

In `flutter/android/app/src/main/AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET"/>
<application
    android:usesCleartextTraffic="true"
    ...>
```

`INTERNET` is missing from the main manifest by default, so release APKs would have no network without it. The cleartext flag allows plain `http://` during development.

### Run

Start the Python server first, then:

```bash
./run.sh app                                              # Linux desktop, address filled in for you
DEVICE=chrome ./run.sh app                                # Chrome
flutter run --dart-define=BRAIN_URL=http://192.168.x.x:5000   # phone on the same Wi-Fi
```

### How it talks to the brain

- **Video:** the `flutter_mjpeg` package reads `BRAIN_URL/video`
- **Result:** the app polls `BRAIN_URL/api/result` every 300 ms and updates the UI

Do not use `localhost` from a phone or emulator. Use the laptop's LAN IP, with both devices on the same Wi-Fi. (The Android emulator reaches the host machine at `10.0.2.2`.)

### Development notes

- **Android blocks plain `http://` by default.** Use the cleartext flag above for development.
- **Flutter Web served over https cannot load an http stream** (mixed content). Serve both over http during development, or put both behind https later.
- **Flutter Web may buffer the MJPEG stream.** If the video looks stuck in Chrome, test on Linux desktop or Android.
- CORS is enabled on the Flask server through `flask-cors`.

---

## 3. Arduino controller (C++)

The controller currently uses **one LED per bin** so the whole pipeline can be tested without moving parts. Servos can come later without changing the serial commands.

### Wiring

Wire each LED the same way:

```
Arduino pin → 220Ω resistor → LED long leg (+) → LED short leg (−) → GND
```

| Bin | LED | Pin |
|---|---|---|
| `biodegradable` | green | D2 |
| `non_biodegradable` | blue | D3 |
| `residual_special_waste` | red | D4 |

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
| Arduino → Brain | `READY` | Sent at power-on, after a quick LED self-test |
| Brain → Arduino | `PING` | Connection check. Reply: `PONG` |
| Brain → Arduino | `TEST` | Blink every LED once. Reply: `OK` |
| Brain → Arduino | `OFF` | All LEDs off. Reply: `OK` |
| Brain → Arduino | `SORT:BIO` | Green LED on for 2 seconds. Reply: `OK` |
| Brain → Arduino | `SORT:NONBIO` | Blue LED on for 2 seconds. Reply: `OK` |
| Brain → Arduino | `SORT:RESIDUAL` | Red LED on for 2 seconds. Reply: `OK` |
| Arduino → Brain | `ERR:BAD_CMD` / `ERR:TOO_LONG` | Unknown or oversized command |

### Test by hand

```bash
./run.sh arduino monitor
```

Type `PING` (expect `PONG`), then `SORT:BIO`, `SORT:NONBIO`, and `SORT:RESIDUAL` and watch the LEDs. Close the monitor before running Python, because only one program can hold the port.

### How the brain uses it

The Python brain opens the port with `pyserial` and sends the sort command after a confident prediction:

| Class | Command |
|---|---|
| `biodegradable` | `SORT:BIO` |
| `non_biodegradable` | `SORT:NONBIO` |
| `residual_special_waste` | `SORT:RESIDUAL` |

To avoid false triggers, send a command only when the confidence is high (for example 80% or more), the same class repeats for several predictions in a row, and a cooldown has passed since the last command. Never send a command while the label is `unsure`. The Uno resets when the serial port opens, so wait about 2 seconds after connecting.

Linux usually exposes the board as `/dev/ttyACM0` (or `/dev/ttyUSB0` for clones). On Arch your user must be in the `uucp` group: `sudo usermod -aG uucp $USER`, then log out and back in.

### Later: servos

A servo version (a sorter servo plus a trapdoor servo) can reuse the same commands. It needs a separate 5 V supply for the servos, with a common GND to the Arduino, and the `Servo` library (`arduino-cli lib install Servo`, and add it under `libraries:` in `arduino.yml`).

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
| `dataset/data.yaml does not exist` | You are using the detection config. For classification use `data="dataset"` with `yolo11n-cls.pt` |
| `ConnectionResetError` during training on Python 3.14 | Wrap training in `def main()` and `if __name__ == "__main__":`, or set `workers=0`, or use Python 3.12 |
| CUDA out of memory | Lower `batch` or `imgsz` |
| `skip residual_special_waste (... images, too few)` | That class needs at least 10 images. Add photos to `public/residual_special_waste/` |
| Camera does not open | Try `VideoCapture(1)`, check `ls /dev/video*`, or run with `QT_QPA_PLATFORM=xcb` |
| `/video` is blank, or the server cannot open the camera | Another program (such as `camera.py`) is holding the camera. Close it, or change the index in `VideoCapture(0)` |
| Opening `/` gives 404 | The server needs the `/` route. Open `/video` and `/api/result` directly, or add the index route |
| Flutter cannot reach the server from a phone | Use the laptop's LAN IP instead of `localhost`, keep both on the same Wi-Fi, and allow port 5000 through the firewall |
| Android app cannot load `http://` URLs, or release APK is offline | Add the `INTERNET` permission and `android:usesCleartextTraffic="true"` to the manifest |
| Flutter Web shows nothing from an https page | Browsers block http streams on https pages. Serve both over http, or both over https |
| `Can't open sketch: no such file or directory` | Run the compile from the repo root with `arduino`, or from inside `arduino/` with `.` |
| `arduino-cli board list` says `No boards found` | No board connected, or a charge-only USB cable. Use a data cable and check `ls /dev/ttyACM* /dev/ttyUSB*` |
| `Permission denied: /dev/ttyUSB0` (or `ttyACM0`) | Add your user to the `uucp` group on Arch and log in again |
| `Servo.h: No such file or directory` (servo version only) | `arduino-cli lib install Servo`, and add `Servo` under `libraries:` in `arduino.yml` |
| Predictions are inaccurate on the live camera | Not enough data from your own camera. Capture more varied frames and retrain |

---

## Roadmap

- [x] Choose the Flutter ↔ Python design (MJPEG `/video` plus JSON `/api/result`)
- [x] Arduino LED controller with a serial protocol
- [x] CI/CD workflows and `setup.sh` / `run.sh`
- [ ] Add images for `residual_special_waste` and balance the three classes (100+ each)
- [ ] Retrain with frames captured from the real camera setup, and an `empty` class
- [ ] Test the Flutter app on Linux, Chrome, and a phone
- [ ] Add the Python → Arduino serial sending to `iframe_embeded.py`, with confidence, repeat, and cooldown checks
- [ ] Replace the LEDs with servos (sorter plus trapdoor)
- [ ] Add a presence sensor so the controller only sorts when an item is there
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