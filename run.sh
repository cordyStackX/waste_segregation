#!/usr/bin/env bash
# Day-to-day commands for waste_segregation. Run ./setup.sh once first.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SERVER_PORT="${SERVER_PORT:-5000}"
HTTPS="${HTTPS:-0}"
FQBN="${FQBN:-arduino:avr:uno}"   # change for other boards
DEVICE="${DEVICE:-linux}"         # Flutter device: linux, chrome, or a phone id

usage() {
  cat <<'USAGE'
Usage: ./run.sh <command>

  server            start the Python analysis API                         [default]
  camera            run Python/OpenCV camera preview with live predictions
  dataset [--replace]  build detection_dataset/ from public/ and annotations
  train [--replace]    build the detection dataset, then train YOLO
  report               plot annotation counts without training
  test <images...>  run object detection on image files
  app               run the Flutter app, pointed at this machine
  all               PING Arduino, then start server + Flutter (Ctrl+C stops both)
  arduino compile   compile the sketch
  arduino upload    compile and upload (auto-detects the port)
  arduino monitor   serial monitor at 9600 baud
  help              show this message

Environment overrides:
  PORT=/dev/ttyACM0   Arduino serial port
  FQBN=arduino:avr:uno   Arduino board
  DEVICE=chrome       Flutter device
  BRAIN_URL=http://127.0.0.1:5000   Flutter API URL
  SERVER_PORT=5000    Python analysis API port
  WASTE_DEVICE=cpu    YOLO inference device (auto-selects CUDA or CPU by default)
  HTTPS=1             enable HTTPS for the Python API
  WASTE_ARDUINO_PORT=/dev/ttyUSB0   Arduino port for `all`
USAGE
}

use_venv() {
  if [[ ! -f .venv/bin/activate ]]; then
    echo "No .venv found. Run ./setup.sh first." >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
}

host_ip() {
  local addr
  addr="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit }}' || true)"
  echo "${addr:-localhost}"
}

brain_url() {
  if [[ -n "${BRAIN_URL:-}" ]]; then
    printf '%s' "$BRAIN_URL"
  else
    printf 'http://%s:%s' "$(host_ip)" "$SERVER_PORT"
  fi
}

find_port() {
  if [[ -n "${PORT:-}" ]]; then
    echo "$PORT"
    return 0
  fi
  local p
  for p in /dev/ttyACM* /dev/ttyUSB*; do
    if [[ -e "$p" ]]; then
      echo "$p"
      return 0
    fi
  done
  echo "No Arduino serial port found. Check 'arduino-cli board list'; use PORT=<device> for Arduino commands or WASTE_ARDUINO_PORT=<device> with 'all'." >&2
  return 1
}

cmd="${1:-server}"
if [[ $# -gt 0 ]]; then shift; fi

case "$cmd" in
  server)
    use_venv
    scheme=http
    if [[ "$HTTPS" != "0" ]]; then
      scheme=https
    fi
    echo "Python analysis API: ${scheme}://$(host_ip):${SERVER_PORT}"
    exec env HTTPS="$HTTPS" SSL_CERT="${SSL_CERT:-/tmp/binthere-cert.pem}" \
      SSL_KEY="${SSL_KEY:-/tmp/binthere-key.pem}" WASTE_PORT="$SERVER_PORT" python iframe_embeded.py
    ;;
  camera)
    use_venv
    exec python camera.py "$@"
    ;;
  dataset)
    use_venv
    exec python build_dataset.py "$@"
    ;;
  train)
    use_venv
    python build_dataset.py "$@"
    exec python train_detection.py
    ;;
  report)
    use_venv
    exec python dataset_report.py "$@"
    ;;
  test)
    use_venv
    exec python test.py "$@"
    ;;
  app)
    cd flutter
    exec env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/opt/flutter \
      flutter run -d "$DEVICE" --dart-define=BRAIN_URL="$(brain_url)" "$@"
    ;;
  all)
    use_venv
    arduino_port="${WASTE_ARDUINO_PORT:-${PORT:-}}"
    if [[ -z "$arduino_port" ]]; then
      arduino_port="$(find_port)"
    fi
    if ! python -c 'import serial' >/dev/null 2>&1; then
      echo "pyserial is missing from .venv. Run ./setup.sh or .venv/bin/pip install pyserial." >&2
      exit 1
    fi
    python - "$arduino_port" <<'PY'
import sys
import time

import serial

port = serial.Serial(sys.argv[1], 9600, timeout=0.25, write_timeout=1)
try:
    # Opening an Uno serial port resets it; wait for its setup() to finish.
    time.sleep(2)
    port.reset_input_buffer()
    port.write(b"PING\n")
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if port.readline().decode("ascii", errors="ignore").strip() == "PONG":
            print(f"Arduino response: PONG ({sys.argv[1]})")
            break
    else:
        raise SystemExit(f"Arduino at {sys.argv[1]} did not reply to PING")
finally:
    port.close()
PY
    echo "Using Arduino at $arduino_port"
    env WASTE_PORT="$SERVER_PORT" WASTE_ARDUINO_PORT="$arduino_port" python iframe_embeded.py &
    server_pid=$!
    trap 'kill "$server_pid" 2>/dev/null || true' EXIT INT TERM
    sleep 3
    cd flutter
    env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=/opt/flutter \
      flutter run -d "$DEVICE" --dart-define=BRAIN_URL="$(brain_url)"
    ;;
  arduino)
    sub="${1:-upload}"
    case "$sub" in
      compile)
        arduino-cli compile --fqbn "$FQBN" arduino
        ;;
      upload)
        port="$(find_port)"
        arduino-cli compile --fqbn "$FQBN" arduino
        arduino-cli upload -p "$port" --fqbn "$FQBN" arduino
        ;;
      monitor)
        port="$(find_port)"
        exec arduino-cli monitor -p "$port" -c baudrate=9600
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 1
    ;;
esac
