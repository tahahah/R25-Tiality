# Operator PC Setup Guide

This guide covers the setup process for the operator PC (Mac/Linux) that will run the R25-Tiality GUI with audio streaming support.

## Quick Setup (Automated)

### One Command Setup

```bash
./init_setup_operator.sh
```

This script will:
- ✅ Install Homebrew (if needed on macOS)
- ✅ Install Opus codec library (system-level)
- ✅ Create Python virtual environment with system-site-packages
- ✅ Install all Python dependencies (pygame, sounddevice, opencv, etc.)
- ✅ Verify installation and test Opus library access
- ✅ Display your IP addresses for Pi configuration
- ✅ Create helper scripts for easy operation

## Running the GUI

### Option 1: Using the Helper Script (Recommended)

```bash
./run_gui.sh
```

**With custom options:**
```bash
# Connect to specific broker
./run_gui.sh --broker 192.168.1.50

# Use custom ports
./run_gui.sh --broker_port 2883 --audio_port 5010

# Disable audio
./run_gui.sh --no-audio
```

### Option 2: Manual Activation

```bash
# Activate virtual environment
source .venv_operator/bin/activate

# Run GUI with audio
python3 GUI/gui.py --robot --broker_port 2883 --audio --audio_port 5005
```

## System Requirements

### macOS
- macOS 10.15 or later
- Homebrew (will be installed automatically if missing)
- Python 3.8 or higher
- Apple Silicon (M1/M2) or Intel Mac

### Linux
- Ubuntu 20.04+ or Debian 11+
- Python 3.8 or higher
- sudo access for installing system packages

## What Gets Installed

### System-Level (macOS)
- **Homebrew** - Package manager (if not already installed)
- **Opus codec library** - For audio decoding (`brew install opus`)

### System-Level (Linux)
- **libopus0** - Opus codec library
- **libopus-dev** - Opus development headers
- **portaudio19-dev** - Audio I/O library

### Python Packages (in virtual environment)
See `requirements.txt` for full list. Key packages:
- **pygame** - GUI framework
- **sounddevice** - Audio playback
- **opencv-python-headless** - Video processing
- **numpy** - Numerical operations
- **paho-mqtt** - MQTT client
- **grpcio** - gRPC communication

## Configuration

### Getting Your IP Address

Your IP address(es) will be displayed at the end of the setup script.

**Manually check:**
```bash
# macOS
ifconfig | grep "inet " | grep -v 127.0.0.1

# Linux
hostname -I
```

### Configure the Pi

On the Raspberry Pi, when running the audio streaming service, use your operator PC's IP:

```bash
# Using integrated run_tiality.sh script
./run_tiality.sh --audio_host 192.168.1.100 --audio_port 5005

# Or manually
python main.py -c 1 -e 1 -d 3,0 --stream --host 192.168.1.100 --port 5005
```

## Firewall Configuration

### macOS

The firewall may block incoming UDP audio packets. Allow Python through:

```bash
# Allow Python
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add $(which python3)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp $(which python3)

# Or temporarily disable firewall for testing
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
```

### Linux

```bash
# Allow UDP port 5005 (or your custom port)
sudo ufw allow 5005/udp
```

## Verification

### Test Opus Installation

```bash
# Activate environment first
source .venv_operator/bin/activate

# Test Opus library
python3 -c "import ctypes.util; print('Opus:', ctypes.util.find_library('opus'))"
```

Expected output:
- **macOS Apple Silicon**: `/opt/homebrew/lib/libopus.dylib`
- **macOS Intel**: `/usr/local/lib/libopus.dylib`
- **Linux**: `/usr/lib/x86_64-linux-gnu/libopus.so.0` (or similar)

### Test Audio System

```bash
# List audio devices
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

### Test GUI Dependencies

```bash
python3 -c "import pygame, cv2, numpy; print('All imports successful!')"
```

## Troubleshooting

### "Opus library not found"

**macOS:**
```bash
# Reinstall Opus
brew reinstall opus

# Check installation
ls -la /opt/homebrew/lib/libopus*  # Apple Silicon
ls -la /usr/local/lib/libopus*     # Intel Mac
```

**Linux:**
```bash
# Reinstall Opus
sudo apt-get install --reinstall libopus0 libopus-dev
```

### "No module named 'pygame'"

The virtual environment might not be activated:
```bash
source .venv_operator/bin/activate
```

Or reinstall:
```bash
source .venv_operator/bin/activate
pip install -r requirements.txt
```

### "No audio output" / "Audio crackling"

1. **Check audio device selection:**
   ```bash
   python3 -c "import sounddevice as sd; print(sd.query_devices())"
   ```

2. **Adjust jitter buffer** - Edit `GUI/udp_audio_receiver.py`:
   ```python
   jitter_buffer_size=20  # Increase from default 10
   ```

3. **Check network connectivity:**
   ```bash
   ping <PI_IP>
   ```

### "Permission denied" when running scripts

Make scripts executable:
```bash
chmod +x init_setup_operator.sh
chmod +x run_gui.sh
chmod +x activate_operator.sh
```

## Directory Structure

After setup, your directory will contain:

```
R25-Tiality2/
├── .venv_operator/              # Virtual environment
├── init_setup_operator.sh       # Setup script (run once)
├── activate_operator.sh         # Quick activate helper
├── run_gui.sh                   # GUI launcher
├── requirements.txt             # Python dependencies
├── GUI/
│   ├── gui.py                   # Main GUI application
│   ├── udp_audio_receiver.py    # Audio receiver
│   └── gui_config.py            # GUI configuration
└── ...
```

## Command Reference

### Setup Commands
```bash
# Initial setup (run once)
./init_setup_operator.sh

# Activate environment
source activate_operator.sh
# or
source .venv_operator/bin/activate
```

### Running Commands
```bash
# Start GUI with defaults
./run_gui.sh

# Start with custom settings
./run_gui.sh --broker 192.168.1.50 --audio_port 5010

# Manual start
python3 GUI/gui.py --robot --broker_port 2883 --audio
```

### Testing Commands
```bash
# Test Opus
python3 -c "import ctypes.util; print(ctypes.util.find_library('opus'))"

# Test sounddevice
python3 -c "import sounddevice as sd; print(sd.query_devices())"

# Test all imports
python3 -c "import pygame, cv2, numpy, sounddevice; print('OK')"
```

## Updating

To update dependencies:

```bash
# Activate environment
source .venv_operator/bin/activate

# Pull latest code
git pull

# Update dependencies
pip install --upgrade -r requirements.txt
```

## Uninstalling

To remove the virtual environment:

```bash
rm -rf .venv_operator
rm activate_operator.sh
rm run_gui.sh
```

To remove system packages:
```bash
# macOS - Opus only (keep Homebrew for other uses)
brew uninstall opus

# Linux
sudo apt-get remove libopus0 libopus-dev portaudio19-dev
```

## Additional Resources

- **Complete Audio Setup Guide**: [SETUP_AUDIO_STREAMING.md](SETUP_AUDIO_STREAMING.md)
- **Quick Audio Reference**: [AUDIO_STREAMING_SUMMARY.md](AUDIO_STREAMING_SUMMARY.md)
- **Main Project README**: [README.md](README.md)

## Support

If you encounter issues:
1. Check this guide's troubleshooting section
2. Review `SETUP_AUDIO_STREAMING.md` for detailed audio troubleshooting
3. Verify all system requirements are met
4. Check firewall and network settings

---

**Happy Operating! 🎮🚁**
