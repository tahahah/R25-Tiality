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
# Use the system Python managed by apt so system site-packages are compatible
PYTHON_BIN="/usr/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3)"
fi

echo "--- Installing system packages (requires sudo) ---"
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv python3-numpy \
    libportaudio2 portaudio19-dev \
    libopus0 libopusfile0 libopusenc0 \
    libogg0 libvorbis0a libvorbisfile3 libvorbisenc2 \
    python3-av \
    python3-aiortc \
    python3-cffi python3-pycparser \
    python3-rpi.gpio \
     --no-install-recommends

echo "--- Creating virtual environment with system site packages ---"
if [ -d "$VENV_DIR" ]; then
    echo "Removing existing virtual environment at $VENV_DIR..."
    rm -rf "$VENV_DIR"
fi
echo "Using Python interpreter: $($PYTHON_BIN -V 2>/dev/null || echo "$PYTHON_BIN")"
$PYTHON_BIN -m venv "$VENV_DIR" --system-site-packages
. "$VENV_DIR/bin/activate"

echo "--- Installing uv (fast pip) if needed ---"
if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found; installing locally..."
    curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH="$HOME/.local/bin:$PATH"
fi

install_with_uv() {
    # Install Python packages using uv if available; otherwise fall back to pip.
    if command -v uv >/dev/null 2>&1; then
        echo "Using uv to install: $*"
        if ! uv pip install "$@"; then
            echo "uv installation failed; falling back to pip..."
            pip install "$@"
        fi
    else
        pip install "$@"
    fi
}

echo "--- Installing Python packages into the venv ---"
# Intentionally omit numpy/opencv to avoid conflicts; rely on system packages
if ! command -v uv >/dev/null 2>&1; then
    pip install --upgrade pip
fi
# Use apt-provided RPi.GPIO, aiortc, and av; avoid building via pip
PI_REQ_TMP="$(mktemp)"
grep -v -E '^\s*(RPi\.GPIO|aiortc|av)(==.*)?\s*$' "$SCRIPT_DIR/requirements.txt" > "$PI_REQ_TMP"
install_with_uv -r "$PI_REQ_TMP"
rm -f "$PI_REQ_TMP"

cd ..
pwd
cd ALSA_Capture_Stream
echo "--- Installing ALSA_Capture_Stream dependencies ---"
pwd
ALSA_REQ_TMP="$(mktemp)"
# Exclude numpy here to ensure we use the system-provided NumPy from apt
grep -v -E '^\s*numpy(==.*)?\s*$' requirements.txt > "$ALSA_REQ_TMP"
install_with_uv -r "$ALSA_REQ_TMP"
rm -f "$ALSA_REQ_TMP"
cd "$SCRIPT_DIR"


echo "--- Starting pigpio daemon ---"
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
echo "pigpio daemon started and enabled for auto-start"

echo "--- Verifying picamera2 availability ---"
if python3 -c "from picamera2 import Picamera2" 2>/dev/null; then
    echo "picamera2 accessible in virtual environment"
else
    echo "WARNING: picamera2 not accessible in virtual environment"
fi

echo
echo "Initialization complete. To run services, use:"
echo "  ./run_tiality.sh"
