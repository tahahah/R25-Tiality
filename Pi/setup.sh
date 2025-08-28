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
        echo "Video server (PID: $VIDEO_PID) stopped."
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

echo "--- Installing and configuring MQTT broker ---"
# Install Mosquitto if not already installed
if ! command -v mosquitto &> /dev/null; then
    echo "Installing Mosquitto MQTT broker..."
    sudo apt update
    sudo apt install -y mosquitto mosquitto-clients
fi

echo "--- Ensuring Pi 5 GPIO backend is installed (python3-lgpio) ---"
if ! dpkg -s python3-lgpio >/dev/null 2>&1; then
    echo "Installing python3-lgpio (RPi.GPIO-compatible backend on Pi 5)..."
    sudo apt update
    sudo apt install -y python3-lgpio
fi

# Ensure Mosquitto is enabled but not started as a service (we'll run it manually)
sudo systemctl stop mosquitto 2>/dev/null || true
sudo systemctl disable mosquitto 2>/dev/null || true

echo "--- Setting up Python environment ---"
if [ ! -d "$SCRIPT_DIR/../.venv" ]; then
    python3 -m venv "$SCRIPT_DIR/../.venv"
fi
source "$SCRIPT_DIR/../.venv/bin/activate"
pip install -r "$SCRIPT_DIR/requirements.txt"

echo "--- Starting services ---"

# Start Mosquitto broker in the background with external access
echo "Starting local Mosquitto MQTT broker with external access..."
# Create a temporary config file
echo "listener 1883 0.0.0.0" > /tmp/mosquitto.conf
echo "allow_anonymous true" >> /tmp/mosquitto.conf
echo "" >> /tmp/mosquitto.conf
echo "# WebSockets listener for React Native client" >> /tmp/mosquitto.conf
echo "listener 9001 0.0.0.0" >> /tmp/mosquitto.conf
echo "protocol websockets" >> /tmp/mosquitto.conf
mosquitto -c /tmp/mosquitto.conf -d
MOSQUITTO_PID=$(pgrep mosquitto)
echo "Mosquitto broker started with PID $MOSQUITTO_PID."

# Start gRPC video server in the background
echo "Starting gRPC video server..."
# Allow selecting camera device via env var (default to 0)
# Example: VIDEO_DEVICE=/dev/video1 ./setup.sh
VIDEO_DEVICE_ARG="--device ${VIDEO_DEVICE:-0}"
python3 "$SCRIPT_DIR/video_server.py" $VIDEO_DEVICE_ARG &
VIDEO_PID=$!
echo "Video server started with PID $VIDEO_PID."

# Start MQTT->PWM controller in the foreground (it will block here)
echo "Starting MQTT->PWM controller... (Press Ctrl+C to stop all)"
sudo "$SCRIPT_DIR/../.venv/bin/python3" "$SCRIPT_DIR/mqtt_to_pwm.py" --broker "localhost"

# The script will only reach here if the mqtt bridge exits without Ctrl+C
wait $VIDEO_PID