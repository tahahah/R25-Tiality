#!/bin/bash
#
# This script sets up the environment and starts both the video and MQTT services.
# The Pi will run the MQTT broker locally.
# Example: ./setup.sh

set -e # Exit on any error

# Resolve the directory of this script so paths work regardless of CWD
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to clean up background processes on exit
cleanup() {
    echo "\nShutting down services..."
    if [ -n "$VIDEO_PID" ]; then
        kill $VIDEO_PID
        echo "WebRTC video server (PID: $VIDEO_PID) stopped."
    fi
    if [ -n "$MOSQUITTO_PID" ]; then
        kill $MOSQUITTO_PID
        echo "Mosquitto broker (PID: $MOSQUITTO_PID) stopped."
    fi
    exit 0
}

# Trap Ctrl+C and other exit signals to run the cleanup function
trap cleanup SIGINT SIGTERM

# --- Main Script ---

echo "--- Pulling latest changes ---"
git pull

echo "--- Installing system packages ---"
# Update system first
sudo apt update

# Install Mosquitto if not already installed
if ! command -v mosquitto &> /dev/null; then
    echo "Installing Mosquitto MQTT broker..."
    sudo apt install -y mosquitto mosquitto-clients
fi

# Install required system packages
echo "Installing required system packages..."
sudo apt install -y python3-picamera2 python3-opencv python3-numpy --no-install-recommends

# Ensure Mosquitto is enabled but not started as a service (we'll run it manually)
sudo systemctl stop mosquitto 2>/dev/null || true
sudo systemctl disable mosquitto 2>/dev/null || true

echo "--- Setting up Python environment ---"
# Remove existing venv to ensure --system-site-packages takes effect
if [ -d "$SCRIPT_DIR/../.venv" ]; then
    echo "Removing existing virtual environment to recreate with system packages..."
    rm -rf "$SCRIPT_DIR/../.venv"
fi

# Create new venv with system site packages
python3 -m venv "$SCRIPT_DIR/../.venv" --system-site-packages
source "$SCRIPT_DIR/../.venv/bin/activate"

# Use system numpy and opencv to avoid conflicts with picamera2
echo "Using system numpy and opencv for picamera2 compatibility..."

# Verify picamera2 is accessible
if python3 -c "import picamera2" 2>/dev/null; then
    echo "picamera2 successfully accessible in virtual environment"
else
    echo "WARNING: picamera2 not accessible in virtual environment"
fi

# Install only the packages we need, avoiding opencv and numpy conflicts
pip install paho-mqtt pyserial RPi.GPIO aiortc av

echo "--- Starting services ---"

# Start Mosquitto broker in the background with external access
echo "Starting local Mosquitto MQTT broker with external access..."
# Create a temporary config file
echo "listener 1883 0.0.0.0" > /tmp/mosquitto.conf
echo "allow_anonymous true" >> /tmp/mosquitto.conf
mosquitto -c /tmp/mosquitto.conf -d
MOSQUITTO_PID=$(pgrep mosquitto)
echo "Mosquitto broker started with PID $MOSQUITTO_PID."

# Start WebRTC video server in the background
echo "Starting WebRTC video server..."
python3 "$SCRIPT_DIR/webrtc_server.py" &
VIDEO_PID=$!
echo "WebRTC video server started with PID $VIDEO_PID."

# Start MQTT->PWM controller in the foreground (it will block here)
echo "Starting MQTT->PWM controller... (Press Ctrl+C to stop all)"
python3 "$SCRIPT_DIR/mqtt_to_pwm.py" --broker "localhost"

# The script will only reach here if the mqtt bridge exits without Ctrl+C
wait $VIDEO_PID