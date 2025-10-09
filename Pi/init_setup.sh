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
# Install system packages, including python3 versions of complex libraries
sudo apt install -y python3-picamera2 python3-opencv python3-numpy \
    python3-pygame python3-av python3-cffi \
    libportaudio2 portaudio19-dev \
    libopus0 libopusfile0 libopusenc0 \
    libogg0 libvorbis0a libvorbisfile3 libvorbisenc2 \
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev libswscale-dev libswresample-dev \
    libsrtp2-dev libssl-dev \
     --no-install-recommends

echo "--- Installing uv and creating virtual environment ---"
# Check for uv, install if not found
if ! command -v uv &> /dev/null; then
    echo "uv not found. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for the current session
    export PATH="$HOME/.local/bin:$PATH"
    echo "✓ uv installed successfully"

    # Add uv to .bashrc to make it available in future sessions
    UV_PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
    if ! grep -qF -- "$UV_PATH_LINE" ~/.bashrc; then
        echo "Adding uv to ~/.bashrc for future sessions..."
        echo "$UV_PATH_LINE" >> ~/.bashrc
    fi
else
    echo "✓ uv already installed"
fi

if [ -d "$VENV_DIR" ]; then
    echo "Removing existing virtual environment at $VENV_DIR..."
    rm -rf "$VENV_DIR"
fi

# Use the system's python3 to create the venv, preserving system site packages
PYTHON_EXE=$(command -v python3)
echo "Creating virtual environment with $PYTHON_EXE..."
uv venv "$VENV_DIR" --python "$PYTHON_EXE" --system-site-packages
. "$VENV_DIR/bin/activate"

echo "--- Installing Python packages using uv (PiWheels first, wheels-only) ---"
# Install requirements for the main Pi components
uv pip install \
  --extra-index-url https://www.piwheels.org/simple \
  --index-url https://pypi.org/simple \
  --only-binary :all: \
  -r "$SCRIPT_DIR/requirements.txt"

# Install requirements for the ALSA Capture Stream utility
echo "--- Installing ALSA_Capture_Stream dependencies ---"
uv pip install \
  --extra-index-url https://www.piwheels.org/simple \
  --index-url https://pypi.org/simple \
  --only-binary :all: \
  -r "$SCRIPT_DIR/../ALSA_Capture_Stream/requirements.txt"


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

