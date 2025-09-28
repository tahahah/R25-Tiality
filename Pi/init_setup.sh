#!/bin/bash
#
# One-time initialization for the Pi environment.
# - Installs required system packages
# - Creates a Python virtual environment in Pi/.venv_pi using system site packages
# - Installs required Python packages into the virtual environment
#
# Usage: ./init_setup.sh

set -e

# Resolve the directory of this script so paths work regardless of CWD (POSIX)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv_pi"

echo "--- Installing system packages (requires sudo) ---"
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv python3-numpy --no-install-recommends

echo "--- Ensuring uv is available (optional) ---"
if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found; attempting install to \$HOME/.local/bin ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh || echo "uv install failed; continuing without uv"
    export PATH="$HOME/.local/bin:$PATH"
fi
if command -v uv >/dev/null 2>&1; then
    echo "uv available: $(uv --version 2>/dev/null || echo present)"
    USE_UV=1
else
    USE_UV=0
fi

echo "--- Creating virtual environment ---"
if [ "$USE_UV" -eq 1 ]; then
    echo "--- Creating virtual environment with uv ---"
    if uv venv --system-site-packages "$VENV_DIR"; then
        :
    else
        echo "uv venv failed; falling back to python venv"
        python3 -m venv "$VENV_DIR" --system-site-packages
    fi
else
    echo "--- Creating virtual environment with python venv ---"
    python3 -m venv "$VENV_DIR" --system-site-packages
fi
. "$VENV_DIR/bin/activate"

echo "--- Installing Python packages into the venv ---"
# Intentionally omit numpy/opencv to avoid conflicts; rely on system packages
if [ "$USE_UV" -eq 1 ]; then
    uv pip install paho-mqtt pyserial RPi.GPIO aiortc av grpcio grpcio-tools protobuf pillow pygame
else
    pip install --upgrade pip
    pip install paho-mqtt pyserial RPi.GPIO aiortc av grpcio grpcio-tools protobuf pillow pygame
fi

echo "--- Verifying picamera2 availability ---"
if python3 -c "from picamera2 import Picamera2" 2>/dev/null; then
    echo "picamera2 accessible in virtual environment"
else
    echo "WARNING: picamera2 not accessible in virtual environment"
fi

echo
echo "Initialization complete. To run services, use:"
echo "  ./run_tiality.sh"

