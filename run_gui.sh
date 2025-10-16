#!/bin/bash
# Run the R25-Tiality GUI with audio support
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Read the last selected target IP, if it exists
if [ -f "$SCRIPT_DIR/.target_pi_ip" ]; then
    DEFAULT_BROKER_HOST=$(cat "$SCRIPT_DIR/.target_pi_ip")
else
    DEFAULT_BROKER_HOST=""
fi

# Parse arguments
BROKER_HOST=""
BROKER_PORT="2883"
AUDIO_PORT="5005"
NO_AUDIO=false

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  --broker HOST          MQTT broker hostname/IP"
    echo "  --broker_port PORT     MQTT broker port (default: 2883)"
    echo "  --audio_port PORT      UDP audio port (default: 5005)"
    echo "  --video_server HOST    Host for Pi to reach video server (default: operator IP)"
    echo "  --video_server_port P  Port for video server (default: 50051)"
    echo "  --no-audio             Disable audio receiver"
    echo "  -h, --help             Show this help message"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --broker)
            BROKER_HOST="$2"; shift 2;;
        --broker_port)
            BROKER_PORT="$2"; shift 2;;
        --audio_port)
            AUDIO_PORT="$2"; shift 2;;
        --video_server)
            VIDEO_SERVER_HOST="$2"; shift 2;;
        --video_server_port)
            VIDEO_SERVER_PORT="$2"; shift 2;;
        --no-audio)
            NO_AUDIO=true; shift;;
        -h|--help)
            usage; exit 0;;
        *)
            echo "Unknown argument: $1"; usage; exit 1;;
    esac
done

# Check if mosquitto broker is running on the specified port
echo "Checking for MQTT broker on port $BROKER_PORT..."
if lsof -Pi :$BROKER_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "✓ MQTT broker already running on port $BROKER_PORT"
else
    echo "MQTT broker not found. Starting mosquitto..."
    
    # Check if mosquitto is installed
    if ! command -v mosquitto &> /dev/null; then
        echo "ERROR: mosquitto not found. Install with: brew install mosquitto"
        exit 1
    fi
    
    # Create temporary MQTT config
    cat > /tmp/mqtt-test.conf <<'MQTT_EOF'
allow_anonymous true
socket_domain ipv4
listener 2883 0.0.0.0
MQTT_EOF
    
    # Start mosquitto in background
    echo "Starting mosquitto broker on port $BROKER_PORT..."
    mosquitto -c /tmp/mqtt-test.conf &
    MOSQUITTO_PID=$!
    
    # Wait a moment for broker to start
    sleep 1
    
    # Verify it started
    if lsof -Pi :$BROKER_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "✓ MQTT broker started successfully (PID: $MOSQUITTO_PID)"
    else
        echo "ERROR: Failed to start MQTT broker"
        exit 1
    fi
fi

# Activate virtual environment
source "$SCRIPT_DIR/.venv_operator/bin/activate"

# Build command
CMD="python3 GUI/gui.py --robot --broker_port $BROKER_PORT --audio_port $AUDIO_PORT"

if [ "$NO_AUDIO" = true ]; then
    CMD="$CMD --no-audio"
else
    CMD="$CMD --audio"
fi

if [ -n "$BROKER_HOST" ]; then
    CMD="$CMD --broker $BROKER_HOST"
fi

echo "Starting GUI..."
echo "Command: $CMD"
cd "$SCRIPT_DIR"
$CMD

# Determine operator IP (used by Pi to connect to broker/video server)
if [[ "$OSTYPE" == "darwin"* ]]; then
    OP_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || ifconfig | awk '/inet / && $2 != "127.0.0.1"{print $2; exit}')
else
    OP_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi

# Video server defaults to operator IP and gRPC default port
VIDEO_SERVER_HOST=${VIDEO_SERVER_HOST:-$OP_IP}
VIDEO_SERVER_PORT=${VIDEO_SERVER_PORT:-50051}

# Also print the Pi command for convenience
echo ""
echo "Pi command (run on the Pi):"
echo "bash run_tiality.sh --video_server ${VIDEO_SERVER_HOST}:${VIDEO_SERVER_PORT} --broker ${VIDEO_SERVER_HOST} --broker_port ${BROKER_PORT}"
