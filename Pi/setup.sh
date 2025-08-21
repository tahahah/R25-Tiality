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

# Start Mosquitto broker in the background
echo "Starting local Mosquitto MQTT broker..."
mosquitto -d
MOSQUITTO_PID=$(pgrep mosquitto)
echo "Mosquitto broker started with PID $MOSQUITTO_PID."

# Start gRPC video server in the background
echo "Starting gRPC video server..."
python3 "$SCRIPT_DIR/video_server.py" &
VIDEO_PID=$!
echo "Video server started with PID $VIDEO_PID."

# Start MQTT->PWM controller in the foreground (it will block here)
echo "Starting MQTT->PWM controller... (Press Ctrl+C to stop all)"
python3 "$SCRIPT_DIR/mqtt_to_pwm.py" --broker "localhost"

# The script will only reach here if the mqtt bridge exits without Ctrl+C
wait $VIDEO_PID