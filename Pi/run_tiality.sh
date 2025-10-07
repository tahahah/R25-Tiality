#!/bin/bash
#
# This script sets up the environment and starts video, MQTT, and audio streaming services.
# The Pi will run the MQTT broker locally.
# Example: ./run_tiality.sh --video_server HOST:PORT --broker HOST --audio_host HOST

set -e # Exit on any error

# Resolve the directory of this script so paths work regardless of CWD
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to clean up background processes on exit
cleanup() {
    echo "\nShutting down services..."
    if [ -n "$VIDEO_PID" ]; then
        kill $VIDEO_PID 2>/dev/null
        echo "gRPC video server (PID: $VIDEO_PID) stopped."
    fi
    if [ -n "$GIMBAL_PID" ]; then
        kill $GIMBAL_PID 2>/dev/null
        echo "Gimbal MQTT controller (PID: $GIMBAL_PID) stopped."
    fi
    if [ -n "$MQTT_PID" ]; then
        kill $MQTT_PID 2>/dev/null
        echo "MQTT->PWM controller (PID: $MQTT_PID) stopped."
    fi
    if [ -n "$AUDIO_PID" ]; then
        kill $AUDIO_PID 2>/dev/null
        echo "Audio streaming service (PID: $AUDIO_PID) stopped."
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
AUDIO_HOST=""
AUDIO_PORT="5005"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  --video_server HOST:PORT    gRPC video server address"
    echo "  --broker HOST               MQTT broker address"
    echo "  --broker_port PORT          MQTT broker port (default: 1883)"
    echo "  --audio_host HOST           Target host for audio streaming"
    echo "  --audio_port PORT           Target UDP port for audio (default: 5005)"
    echo "  -h, --help                  Show this help message"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --video_server)
            VIDEO_SERVER="$2"; shift 2;;
        --broker)
            BROKER="$2"; shift 2;;
        --broker_port)
            BROKER_PORT="$2"; shift 2;;
        --audio_host)
            AUDIO_HOST="$2"; shift 2;;
        --audio_port)
            AUDIO_PORT="$2"; shift 2;;
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
if [ -n "$AUDIO_HOST" ]; then
    echo "Using audio streaming: $AUDIO_HOST:$AUDIO_PORT"
else
    echo "audio_host not supplied; audio streaming will not start"
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

# Function to start Gimbal MQTT controller
start_gimbal_mqtt() {
    echo "Starting Gimbal MQTT controller..."
    cd "$SCRIPT_DIR/MotorMoving"
    python3 gimbal_mqtt.py --broker "$BROKER" &
    GIMBAL_PID=$!
    cd "$SCRIPT_DIR"
    echo "Gimbal MQTT controller started with PID $GIMBAL_PID."
}

# Function to start Audio Streaming service
start_audio_stream() {
    echo "Starting Audio Streaming service..."
    cd "$SCRIPT_DIR/../ALSA_Capture_Stream"
    python3 main.py -c 1 -e 1 -d 3,0 --stream --host "$AUDIO_HOST" --port "$AUDIO_PORT" &
    AUDIO_PID=$!
    cd "$SCRIPT_DIR"
    echo "Audio Streaming service started with PID $AUDIO_PID."
}

# Start requested services initially
if [ -n "$VIDEO_SERVER" ]; then
    start_video_manager
fi
if [ -n "$BROKER" ]; then
    start_mqtt_pwm
    start_gimbal_mqtt
fi
if [ -n "$AUDIO_HOST" ]; then
    start_audio_stream
fi

# If no service requested, print usage and exit
if [ -z "$VIDEO_SERVER" ] && [ -z "$BROKER" ] && [ -z "$AUDIO_HOST" ]; then
    echo "No services requested. Provide --video_server and/or --broker and/or --audio_host."
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

    # Check if Gimbal MQTT controller is running (only if started)
    if [ -n "$GIMBAL_PID" ]; then
        if ! kill -0 $GIMBAL_PID 2>/dev/null; then
            echo "Gimbal MQTT controller (PID $GIMBAL_PID) not running. Restarting..."
            start_gimbal_mqtt
        fi
    fi

    # Check if Audio Streaming service is running (only if started)
    if [ -n "$AUDIO_PID" ]; then
        if ! kill -0 $AUDIO_PID 2>/dev/null; then
            echo "Audio Streaming service (PID $AUDIO_PID) not running. Restarting..."
            start_audio_stream
        fi
    fi

    sleep 2
done

# The script will only reach here if the mqtt bridge exits without Ctrl+C
wait $VIDEO_PID