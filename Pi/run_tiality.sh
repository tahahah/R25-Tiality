#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() {
    echo "\nShutting down services..."
    if [ -n "$VIDEO_PID" ]; then
        kill $VIDEO_PID
        echo "Tiality manager (PID: $VIDEO_PID) stopped."
    fi
    if [ -n "$GIMBAL_PID" ]; then
        kill $GIMBAL_PID
        echo "Gimbal MQTT controller (PID: $GIMBAL_PID) stopped."
    fi
    if [ -n "$MQTT_PID" ]; then
        kill $MQTT_PID
        echo "MQTT->PWM controller (PID: $MQTT_PID) stopped."
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

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
AUDIO_SERVER=""
BROKER=""
BROKER_PORT="1883"
ENABLE_AUDIO=""

usage() {
    echo "Usage: $0 [--video_server HOST:PORT] [--audio_server HOST:PORT] [--broker HOST] [--broker_port PORT] [--enable_audio]"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --video_server)
            VIDEO_SERVER="$2"; shift 2;;
        --audio_server)
            AUDIO_SERVER="$2"; shift 2;;
        --broker)
            BROKER="$2"; shift 2;;
        --broker_port)
            BROKER_PORT="$2"; shift 2;;
        --enable_audio)
            ENABLE_AUDIO="--enable_audio"; shift;;
        -h|--help)
            usage; exit 0;;
        *)
            echo "Unknown argument: $1"; usage; exit 1;;
    esac
done

# Start Pi Tiality Manager (video + audio)
start_tiality_manager() {
    echo "Starting Pi Tiality Manager (Video + Audio)..."
    CMD="python3 $SCRIPT_DIR/tiality_manager.py --video_server $VIDEO_SERVER"
    
    # Add audio_server if provided
    if [ -n "$AUDIO_SERVER" ]; then
        CMD="$CMD --audio_server $AUDIO_SERVER"
    fi
    
    # Add enable_audio flag if set
    if [ -n "$ENABLE_AUDIO" ]; then
        CMD="$CMD $ENABLE_AUDIO"
    fi
    
    $CMD &
    VIDEO_PID=$!
    echo "Tiality Manager started with PID $VIDEO_PID."
}

# Start MQTT->PWM controller
start_mqtt_pwm() {
    echo "Starting MQTT->PWM controller..."
    python3 "$SCRIPT_DIR/mqtt_to_pwm.py" --broker "$BROKER" --broker_port "$BROKER_PORT" &
    MQTT_PID=$!
    echo "MQTT->PWM controller started with PID $MQTT_PID."
}

# Start Gimbal MQTT controller
start_gimbal_mqtt() {
    echo "Starting Gimbal MQTT controller..."
    cd "$SCRIPT_DIR/MotorMoving"
    python3 gimbal_mqtt.py --broker "$BROKER" &
    GIMBAL_PID=$!
    cd "$SCRIPT_DIR"
    echo "Gimbal MQTT controller started with PID $GIMBAL_PID."
}

# Start services
if [ -n "$VIDEO_SERVER" ]; then
    start_tiality_manager
fi
if [ -n "$BROKER" ]; then
    start_mqtt_pwm
    start_gimbal_mqtt
fi

if [ -z "$VIDEO_SERVER" ] && [ -z "$BROKER" ]; then
    echo "No services requested."
    usage
    exit 1
fi

# Monitor and restart loop
while true; do
    if [ -n "$VIDEO_PID" ]; then
        if ! kill -0 $VIDEO_PID 2>/dev/null; then
            echo "Tiality Manager not running. Restarting..."
            start_tiality_manager
        fi
    fi

    if [ -n "$MQTT_PID" ]; then
        if ! kill -0 $MQTT_PID 2>/dev/null; then
            echo "MQTT->PWM controller not running. Restarting..."
            start_mqtt_pwm
        fi
    fi

    if [ -n "$GIMBAL_PID" ]; then
        if ! kill -0 $GIMBAL_PID 2>/dev/null; then
            echo "Gimbal MQTT controller not running. Restarting..."
            start_gimbal_mqtt
        fi
    fi

    sleep 2
done