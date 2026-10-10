#!/usr/bin/env bash
# One-time setup for waste_segregation (written for Arch Linux).
#
# Usage:
#   ./setup.sh          # NVIDIA GPU build of PyTorch (cu126, works on old cards like the GTX 960M)
#   ./setup.sh --cpu    # CPU-only PyTorch
#
# To start over from scratch, delete .venv and run it again.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PYTHON="${PYTHON:-python3}"
TORCH_INDEX="cu126"
if [[ "${1:-}" == "--cpu" ]]; then
  TORCH_INDEX="cpu"
fi

say()  { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }

# ---------- Python ----------
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python not found. Install it with: sudo pacman -S python" >&2
  exit 1
fi

if [[ "$TORCH_INDEX" == "cu126" ]] && ! command -v nvidia-smi >/dev/null 2>&1; then
  warn "nvidia-smi not found, installing the CPU build of PyTorch instead"
  TORCH_INDEX="cpu"
fi

say "Python virtual environment (.venv)"
if [[ ! -d .venv ]]; then
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python --version
pip install --upgrade pip

# PyTorch goes first and from its own index, so pip does not pull a build
# that lacks kernels for older GPUs.
say "PyTorch ($TORCH_INDEX)"
pip install torch torchvision --index-url "https://download.pytorch.org/whl/${TORCH_INDEX}"

say "Python packages"
pip install ultralytics flask flask-cors pyserial

say "Checking PyTorch"
python - <<'PY'
import torch

print("torch", torch.__version__)
if torch.cuda.is_available():
    cap = torch.cuda.get_device_capability(0)
    arch = f"sm_{cap[0]}{cap[1]}"
    archs = torch.cuda.get_arch_list()
    print("GPU:", torch.cuda.get_device_name(0), arch)
    print("This build has kernels for:", archs)
    try:
        print("GPU test (expect 2.0):", (torch.ones(1).cuda() * 2).item())
    except Exception as e:
        print("WARNING: GPU test failed:", e)
    else:
        if arch not in archs:
            print("WARNING:", arch, "is not in the list above, training may fail with 'no kernel image'")
else:
    print("CUDA not available, training will run on the CPU")
PY

# ---------- Arduino ----------
say "Arduino"
if command -v arduino-cli >/dev/null 2>&1; then
  arduino-cli core update-index
  arduino-cli core install arduino:avr
else
  warn "arduino-cli not found. Install it with: sudo pacman -S arduino-cli"
fi

if [[ " $(id -nG) " != *" uucp "* ]]; then
  warn "your user is not in the 'uucp' group, so uploading may fail with 'permission denied'."
  warn "fix: sudo usermod -aG uucp \$USER   (then log out and back in)"
fi

# ---------- Flutter ----------
say "Flutter"
if ! command -v flutter >/dev/null 2>&1; then
  warn "flutter not found, skipping the app setup"
elif [[ ! -f flutter/pubspec.yaml ]]; then
  warn "flutter/pubspec.yaml not found. Create the project first:"
  warn "  cd flutter && flutter create --project-name waste_app --org com.cordystackx --platforms=android,linux,web --empty ."
else
  (cd flutter && flutter pub get)
fi

say "Done"
echo "Next:"
echo "  ./run.sh server     # camera + model + web API"
echo "  ./run.sh help       # all commands"