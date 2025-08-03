#!/bin/bash
#
# This script sets up the environment and starts both the video and MQTT services.
# Pass your laptop's IP address as the first argument.
# Example: ./app/setup.sh 192.168.0.127

set -e # Exit on any error

# Function to clean up background processes on exit
cleanup() {
    echo "\nShutting down services..."
    if [ -n "$VIDEO_PID" ]; then
        kill $VIDEO_PID
        echo "Video server (PID: $VIDEO_PID) stopped."
    fi
    exit 0
}

# Trap Ctrl+C and other exit signals to run the cleanup function
trap cleanup SIGINT SIGTERM

# --- Main Script ---

# Check for laptop IP argument
if [ -z "$1" ]; then
    echo "Error: Please provide your laptop's IP address as the first argument."
    echo "Usage: $0 <LAPTOP_IP>"
    exit 1
fi
LAPTOP_IP=$1

echo "--- Pulling latest changes ---"
git pull

echo "--- Setting up Python environment ---"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r app/requirements.txt

echo "--- Starting services ---"

# Start gRPC video server in the background
echo "Starting gRPC video server..."
python3 app/video_server.py &
VIDEO_PID=$!
echo "Video server started with PID $VIDEO_PID."

# Start MQTT bridge in the foreground (it will block here)
echo "Starting MQTT bridge to broker at $LAPTOP_IP... (Press Ctrl+C to stop all)"
python3 app/mqtt_to_serial.py --broker "$LAPTOP_IP"

# The script will only reach here if the mqtt bridge exits without Ctrl+C
wait $VIDEO_PID