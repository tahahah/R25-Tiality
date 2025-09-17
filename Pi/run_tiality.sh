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
        echo "gRPC video server (PID: $VIDEO_PID) stopped."
    fi
    exit 0
}

# Trap Ctrl+C and other exit signals to run the cleanup function
trap cleanup SIGINT SIGTERM

# --- Main Script ---
echo "--- Pulling latest changes ---"
git pull

echo "--- Activating Python environment ---"
VENV_DIR="$SCRIPT_DIR/.venv_pi"
if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: $VENV_DIR not found. Run ./init_setup.sh first."
    exit 1
fi
source "$VENV_DIR/bin/activate"

echo "--- Parsing arguments ---"
VIDEO_SERVER=""
BROKER=""
BROKER_PORT="1883"

usage() {
    echo "Usage: $0 [--video_server HOST:PORT] [--broker HOST] [--broker_port PORT]"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --video_server)
            VIDEO_SERVER="$2"; shift 2;;
        --broker)
            BROKER="$2"; shift 2;;
        --broker_port)
            BROKER_PORT="$2"; shift 2;;
        -h|--help)
            usage; exit 0;;
        *)
            echo "Unknown argument: $1"; usage; exit 1;;
    esac
done

if [ -n "$VIDEO_SERVER" ]; then
    echo "Using video_server: $VIDEO_SERVER"
else
    echo "video_server not supplied; video manager will not start"
fi
if [ -n "$BROKER" ]; then
    echo "Using broker: $BROKER:$BROKER_PORT"
else
    echo "broker not supplied; MQTT->PWM controller will not start"
fi

echo "--- Starting services ---"


# Function to start Pi Video Manager
start_video_manager() {
    echo "Starting Pi Video Manager..."
    python3 "$SCRIPT_DIR/tiality_manager.py" --video_server "$VIDEO_SERVER" &
    VIDEO_PID=$!
    echo "Pi Video Manager started with PID $VIDEO_PID."
}

# Function to start MQTT->PWM controller
start_mqtt_pwm() {
    echo "Starting MQTT->PWM controller... (Press Ctrl+C to stop all)"
    python3 "$SCRIPT_DIR/mqtt_to_pwm.py" --broker "$BROKER" --broker_port "$BROKER_PORT" &
    MQTT_PID=$!
    echo "MQTT->PWM controller started with PID $MQTT_PID."
}

# Start requested services initially
if [ -n "$VIDEO_SERVER" ]; then
    start_video_manager
fi
if [ -n "$BROKER" ]; then
    start_mqtt_pwm
fi

# If neither service requested, print usage and exit
if [ -z "$VIDEO_SERVER" ] && [ -z "$BROKER" ]; then
    echo "No services requested. Provide --video_server and/or --broker."
    usage
    exit 1
fi

# Loop to monitor and restart if needed
while true; do
    # Check if Pi Video Manager is running (only if started)
    if [ -n "$VIDEO_PID" ]; then
        if ! kill -0 $VIDEO_PID 2>/dev/null; then
            echo "Pi Video Manager (PID $VIDEO_PID) not running. Restarting..."
            start_video_manager
        fi
    fi

    # Check if MQTT->PWM controller is running (only if started)
    if [ -n "$MQTT_PID" ]; then
        if ! kill -0 $MQTT_PID 2>/dev/null; then
            echo "MQTT->PWM controller (PID $MQTT_PID) not running. Restarting..."
            start_mqtt_pwm
        fi
    fi

    sleep 2
done

# Start Pi Video Viewer in the background

# # Start WebRTC video server in the background
# echo "Starting WebRTC video server..."
# python3 "$SCRIPT_DIR/webrtc_server.py" &
# VIDEO_PID=$!
# echo "WebRTC video server started with PID $VIDEO_PID."


# The script will only reach here if the mqtt bridge exits without Ctrl+C
wait $VIDEO_PID