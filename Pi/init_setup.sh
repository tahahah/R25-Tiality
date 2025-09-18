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

echo "--- Creating virtual environment with system site packages ---"
if [ -d "$VENV_DIR" ]; then
    echo "Removing existing virtual environment at $VENV_DIR..."
    rm -rf "$VENV_DIR"
fi
python3 -m venv "$VENV_DIR" --system-site-packages
. "$VENV_DIR/bin/activate"

echo "--- Installing Python packages into the venv ---"
# Intentionally omit numpy/opencv to avoid conflicts; rely on system packages
pip install --upgrade pip
pip install paho-mqtt pyserial RPi.GPIO aiortc av grpcio grpcio-tools protobuf pillow pygame

echo "--- Verifying picamera2 availability ---"
if python3 -c "from picamera2 import Picamera2" 2>/dev/null; then
    echo "picamera2 accessible in virtual environment"
else
    echo "WARNING: picamera2 not accessible in virtual environment"
fi

echo
echo "Initialization complete. To run services, use:"
echo "  ./run_tiality.sh"

