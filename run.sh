#!/usr/bin/env bash
# Day-to-day commands for waste_segregation. Run ./setup.sh once first.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SERVER_PORT="${SERVER_PORT:-5000}"
FQBN="${FQBN:-arduino:avr:uno}"   # change for other boards
DEVICE="${DEVICE:-linux}"         # Flutter device: linux, chrome, or a phone id

usage() {
  cat <<'USAGE'
Usage: ./run.sh <command>

  server            start the Python brain (camera stream + /api/result)   [default]
  camera            local OpenCV window with live predictions
  dataset           build dataset/ from public/
  train             build dataset/, then train the model
  test <images...>  classify image files
  app               run the Flutter app, pointed at this machine
  all               server + Flutter app together (Ctrl+C stops both)
  arduino compile   compile the sketch
  arduino upload    compile and upload (auto-detects the port)
  arduino monitor   serial monitor at 9600 baud
  help              show this message

Environment overrides:
  PORT=/dev/ttyACM0   Arduino serial port
  FQBN=arduino:avr:uno   Arduino board
  DEVICE=chrome       Flutter device
  SERVER_PORT=5000    web server port
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
  echo "No Arduino found. Plug it in (data cable) or set PORT=/dev/ttyACM0" >&2
  return 1
}

cmd="${1:-server}"
if [[ $# -gt 0 ]]; then shift; fi

case "$cmd" in
  server)
    use_venv
    echo "Open: http://$(host_ip):${SERVER_PORT}/"
    exec python iframe_embeded.py
    ;;
  camera)
    use_venv
    exec python camera.py "$@"
    ;;
  dataset)
    use_venv
    exec python build_dataset.py
    ;;
  train)
    use_venv
    python build_dataset.py
    exec python main.py
    ;;
  test)
    use_venv
    exec python test.py "$@"
    ;;
  app)
    cd flutter
    exec flutter run -d "$DEVICE" --dart-define=BRAIN_URL="http://$(host_ip):${SERVER_PORT}" "$@"
    ;;
  all)
    use_venv
    python iframe_embeded.py &
    server_pid=$!
    trap 'kill "$server_pid" 2>/dev/null || true' EXIT INT TERM
    sleep 3
    cd flutter
    flutter run -d "$DEVICE" --dart-define=BRAIN_URL="http://$(host_ip):${SERVER_PORT}"
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