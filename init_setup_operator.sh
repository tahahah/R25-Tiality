#!/bin/bash
#
# Operator PC Setup Script for R25-Tiality GUI with Audio Streaming
# This script sets up the Python environment and installs all dependencies
# including the Opus codec library required for audio streaming.
#
# Supports: macOS (Intel & Apple Silicon) and Linux (Debian/Ubuntu)
#
# Usage: ./init_setup_operator.sh
#

set -e  # Exit on any error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}R25-Tiality Operator PC Setup${NC}"
echo -e "${GREEN}========================================${NC}"

# Resolve the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    echo -e "${GREEN}Detected OS: macOS${NC}"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    echo -e "${GREEN}Detected OS: Linux${NC}"
else
    echo -e "${RED}Unsupported OS: $OSTYPE${NC}"
    exit 1
fi

# ============================================
# Step 1: Install System Dependencies
# ============================================

echo -e "\n${GREEN}--- Step 1: Installing System Dependencies ---${NC}"

if [[ "$OS" == "macos" ]]; then
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        echo -e "${YELLOW}Homebrew not found. Installing Homebrew...${NC}"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        
        # Add Homebrew to PATH for Apple Silicon
        if [[ $(uname -m) == "arm64" ]]; then
            echo -e "${YELLOW}Adding Homebrew to PATH for Apple Silicon...${NC}"
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    else
        echo -e "${GREEN}✓ Homebrew already installed${NC}"
    fi
    
    # Install Opus codec library
    echo -e "${YELLOW}Installing Opus codec library...${NC}"
    if brew list opus &> /dev/null; then
        echo -e "${GREEN}✓ Opus already installed${NC}"
    else
        brew install opus
        echo -e "${GREEN}✓ Opus installed successfully${NC}"
    fi
    
    # Verify Opus installation
    if [[ $(uname -m) == "arm64" ]]; then
        OPUS_PATH="/opt/homebrew/lib/libopus.dylib"
    else
        OPUS_PATH="/usr/local/lib/libopus.dylib"
    fi
    
    if [[ -f "$OPUS_PATH" ]]; then
        echo -e "${GREEN}✓ Opus library found at: $OPUS_PATH${NC}"
    else
        echo -e "${YELLOW}⚠ Opus library not found at expected location${NC}"
        echo -e "${YELLOW}  Searching for Opus library...${NC}"
        find /opt/homebrew/lib /usr/local/lib -name "libopus*" 2>/dev/null || true
    fi
    
elif [[ "$OS" == "linux" ]]; then
    # Install Opus on Linux
    echo -e "${YELLOW}Installing Opus codec library...${NC}"
    sudo apt-get update
    sudo apt-get install -y libopus0 libopus-dev portaudio19-dev
    echo -e "${GREEN}✓ Opus and PortAudio installed successfully${NC}"
fi

# ============================================
# Step 2: Create Python Virtual Environment
# ============================================

echo -e "\n${GREEN}--- Step 2: Creating Python Virtual Environment ---${NC}"

VENV_DIR="$SCRIPT_DIR/.venv_operator"

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ERROR: python3 not found. Please install Python 3.8 or higher.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}Python version: $PYTHON_VERSION${NC}"

# Create virtual environment with system-site-packages
# This allows access to system Opus libraries
if [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}Virtual environment already exists. Removing old one...${NC}"
    rm -rf "$VENV_DIR"
fi

echo -e "${YELLOW}Creating virtual environment with system-site-packages...${NC}"
python3 -m venv "$VENV_DIR" --system-site-packages

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo -e "${YELLOW}Upgrading pip...${NC}"
pip install --upgrade pip

# ============================================
# Step 3: Install Python Dependencies
# ============================================

echo -e "\n${GREEN}--- Step 3: Installing Python Dependencies ---${NC}"

# Install audio-specific dependencies first
echo -e "${YELLOW}Installing audio streaming dependencies...${NC}"
pip install sounddevice numpy

# Install main requirements
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    echo -e "${YELLOW}Installing requirements from requirements.txt...${NC}"
    pip install -r "$SCRIPT_DIR/requirements.txt"
    echo -e "${GREEN}✓ Requirements installed${NC}"
else
    echo -e "${RED}ERROR: requirements.txt not found in $SCRIPT_DIR${NC}"
    exit 1
fi

# ============================================
# Step 4: Verify Installation
# ============================================

echo -e "\n${GREEN}--- Step 4: Verifying Installation ---${NC}"

# Test Opus library access from Python
echo -e "${YELLOW}Testing Opus library access...${NC}"
python3 << 'VERIFY_SCRIPT'
import ctypes.util
import os
import sys

def find_opus():
    # Try standard library search
    path = ctypes.util.find_library('opus')
    if path:
        return path
    
    # Try common Homebrew paths (macOS)
    homebrew_paths = [
        '/opt/homebrew/lib/libopus.dylib',           # Apple Silicon
        '/usr/local/lib/libopus.dylib',              # Intel Mac
        '/opt/homebrew/opt/opus/lib/libopus.dylib',
        '/usr/local/opt/opus/lib/libopus.dylib',
    ]
    
    for path in homebrew_paths:
        if os.path.exists(path):
            return path
    
    # Try common Linux paths
    linux_paths = [
        '/usr/lib/x86_64-linux-gnu/libopus.so.0',
        '/usr/lib/aarch64-linux-gnu/libopus.so.0',
        '/usr/lib/libopus.so.0',
    ]
    
    for path in linux_paths:
        if os.path.exists(path):
            return path
    
    return None

opus_path = find_opus()
if opus_path:
    print(f"✓ Opus library found: {opus_path}")
    
    # Try loading it
    try:
        libopus = ctypes.CDLL(opus_path)
        print("✓ Opus library loaded successfully")
    except Exception as e:
        print(f"⚠ Opus library found but failed to load: {e}")
        sys.exit(1)
else:
    print("✗ Opus library not found!")
    print("Please install Opus manually:")
    print("  macOS: brew install opus")
    print("  Linux: sudo apt-get install libopus0 libopus-dev")
    sys.exit(1)
VERIFY_SCRIPT

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Opus verification passed${NC}"
else
    echo -e "${RED}✗ Opus verification failed${NC}"
    echo -e "${YELLOW}Please check the error messages above${NC}"
    exit 1
fi

# Test sounddevice
echo -e "${YELLOW}Testing sounddevice...${NC}"
python3 -c "import sounddevice as sd; print('✓ sounddevice imported successfully')" || {
    echo -e "${RED}✗ sounddevice import failed${NC}"
    exit 1
}

# Test other key dependencies
echo -e "${YELLOW}Testing other dependencies...${NC}"
python3 -c "import pygame; print('✓ pygame imported successfully')" || {
    echo -e "${RED}✗ pygame import failed${NC}"
    exit 1
}

python3 -c "import cv2; print('✓ opencv imported successfully')" || {
    echo -e "${RED}✗ opencv import failed${NC}"
    exit 1
}

# ============================================
# Step 5: Display Network Information
# ============================================

echo -e "\n${GREEN}--- Step 5: Network Information ---${NC}"

echo -e "${YELLOW}Your IP address(es):${NC}"
if [[ "$OS" == "macos" ]]; then
    ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print "  " $2}'
elif [[ "$OS" == "linux" ]]; then
    hostname -I | tr ' ' '\n' | grep -v '^$' | awk '{print "  " $1}'
fi

echo -e "\n${YELLOW}Use one of these IP addresses when configuring the Pi to stream audio to this machine.${NC}"

# ============================================
# Step 6: Create Helper Scripts
# ============================================

echo -e "\n${GREEN}--- Step 6: Creating Helper Scripts ---${NC}"

# Create activation script
cat > "$SCRIPT_DIR/activate_operator.sh" << 'EOF'
#!/bin/bash
# Quick script to activate the operator virtual environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv_operator/bin/activate"
echo "Virtual environment activated!"
echo "You can now run: python3 GUI/gui.py --robot --broker_port 2883 --audio"
EOF

chmod +x "$SCRIPT_DIR/activate_operator.sh"
echo -e "${GREEN}✓ Created activation script: activate_operator.sh${NC}"

# Create run script for GUI
cat > "$SCRIPT_DIR/run_gui.sh" << 'EOF'
#!/bin/bash
# Run the R25-Tiality GUI with audio support
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
    mosquitto -c /tmp/mqtt-test.conf -v &
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
EOF

chmod +x "$SCRIPT_DIR/run_gui.sh"
echo -e "${GREEN}✓ Created GUI launcher: run_gui.sh${NC}"

# ============================================
# Setup Complete!
# ============================================

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "\n${YELLOW}Quick Start:${NC}"
echo -e "  1. Run GUI with Audio (Auto Starts MQTT Broker):"
echo -e "     ${GREEN}./run_gui.sh${NC}"
echo -e ""
echo -e "  2. Activate environment only:"
echo -e "     ${GREEN}source activate_operator.sh${NC}"
echo -e ""
echo -e "  Or manually:"
echo -e "     ${GREEN}source .venv_operator/bin/activate${NC}"
echo -e "     ${GREEN}python3 GUI/gui.py --robot --broker_port 2883 --audio${NC}"

echo -e "\n${YELLOW}Audio Streaming:${NC}"
echo -e "  - Your IP addresses are listed above"
echo -e "  - Configure the Pi to stream to one of these addresses"
echo -e "  - Default audio port: 5005"

echo -e "\n${YELLOW}Troubleshooting:${NC}"
echo -e "  - Full setup guide: ${GREEN}SETUP_AUDIO_STREAMING.md${NC}"
echo -e "  - Quick reference: ${GREEN}AUDIO_STREAMING_SUMMARY.md${NC}"

echo -e "\n${GREEN}Happy flying! 🚀${NC}\n"
