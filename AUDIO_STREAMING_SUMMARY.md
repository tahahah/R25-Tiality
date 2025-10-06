# Audio Streaming - Quick Reference

## 📖 Documentation

- **[Complete Setup Guide](SETUP_AUDIO_STREAMING.md)** - Full installation and troubleshooting
- **[Technical Details](ALSA_Capture_Stream/README_AUDIO_STREAMING.md)** - Original implementation details

## 🚀 Quick Start

### New Mac Setup (One-Time)
```bash
# Install Opus codec
brew install opus

# Install Python dependencies
pip install sounddevice numpy
```

### Running the System

**1. Start GUI (on Mac):**
```bash
python GUI/gui.py --robot --broker_port 2883 --audio --audio_port 5005
```

**2. Start Streaming (on Pi):**
```bash
python main.py -c 1 -e 1 -d 3,0 --stream --host <YOUR_MAC_IP> --port 5005
```

Replace `<YOUR_MAC_IP>` with your Mac's IP address (find with `ifconfig`).

## 🎯 Key Points

### ✅ What Works
- Real-time audio streaming from Pi to Mac
- Low latency (~250-300ms including jitter buffer)
- Automatic packet loss handling
- Cross-platform architecture (ARM Pi → ARM64/x86_64 Mac)

### 🔧 Architecture
- **Pi**: Uses PyOgg with bundled ARM libraries for encoding
- **Mac**: Uses system Opus library (via Homebrew) for decoding
- **No PyOgg needed on Mac** - avoids architecture conflicts

### 📊 Performance
- **Bandwidth**: ~15-20 KB/s for mono audio
- **Latency**: ~250-300ms total (adjustable)
- **Packet Rate**: ~50 packets/second (20ms frames)
- **CPU**: <5% on both Pi and Mac

## 🐛 Troubleshooting

### No Audio?
```bash
# 1. Check Opus is installed
brew list opus

# 2. Check network
ping <PI_IP>

# 3. Check firewall
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off

# 4. Verify IP addresses match
ifconfig | grep "inet "
```

### Audio Dropouts?
Edit `GUI/udp_audio_receiver.py` and increase buffer:
```python
jitter_buffer_size=20  # Default is 10
```

## 📁 Files Modified

### Created
- `GUI/udp_audio_receiver.py` - UDP receiver with system Opus decoder
- `ALSA_Capture_Stream/udp_audio_sender.py` - UDP sender

### Modified
- `GUI/gui.py` - Integrated audio receiver
- `ALSA_Capture_Stream/main.py` - Added `--stream` mode

## 💡 Why System Opus Instead of PyOgg on Mac?

**The Problem:**
- Pi uses ARM architecture
- Mac uses ARM64 (M1/M2) or x86_64 (Intel)  
- Compiled libraries don't work across architectures

**The Solution:**
- Pi keeps using PyOgg (with ARM libraries)
- Mac uses Homebrew Opus (native to your Mac's architecture)
- Simple `ctypes` wrapper bridges Python to C library
- No cross-platform library conflicts!

## 🔗 Related Commands

### Get Mac IP
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

### Test Opus Installation
```bash
ls -la /opt/homebrew/lib/libopus*  # Apple Silicon
ls -la /usr/local/lib/libopus*     # Intel Mac
```

### Monitor Statistics (in Python)
```python
stats = gui.audio_receiver.get_stats()
print(f"Packets: {stats['packets_received']}, Lost: {stats['packets_lost']}")
```

## ✨ Credits

- **Opus Codec**: xiph.org
- **PyOgg**: TeamPyOgg
- **Streaming Implementation**: Custom for R25-Tiality
