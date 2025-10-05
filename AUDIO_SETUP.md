# Audio Streaming Setup Guide

## Overview
The Tiality system supports real-time audio streaming from the Raspberry Pi to the GUI using Opus codec over gRPC.

## Architecture
- **Pi Side**: Captures audio from ALSA device → Encodes with Opus → Streams via gRPC
- **GUI Side**: Receives Opus packets via gRPC → Decodes → Plays through sounddevice

## Prerequisites

### On Raspberry Pi
1. ALSA audio device (microphone) configured
2. Python packages installed via `init_setup.sh`:
   - PyOgg (for Opus encoding)
   - sounddevice
   - System libraries: libasound2-dev, libogg-dev, libopus-dev, etc.

### On GUI Machine (Your Computer)

#### macOS
1. Install native Opus libraries via Homebrew:
   ```bash
   brew install opus libogg opusfile
   ```

2. Install Python packages:
   ```bash
   pip install -r requirements.txt
   ```
   This installs:
   - PyOgg (for Opus decoding)
   - sounddevice (for audio playback)
   - cffi and pycparser (PyOgg dependencies)

#### Linux
1. Install native libraries:
   ```bash
   sudo apt-get install libopus0 libogg0 libopusfile0
   ```

2. Install Python packages:
   ```bash
   pip install -r requirements.txt
   ```

#### Windows
1. PyOgg includes DLLs for Windows - just install Python packages:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

### Audio Device Configuration (Pi)
Default audio device is set in `/Pi/audio.py`:
```python
interface = {"card": 3, "device": 0}
```

To find your audio device:
```bash
arecord -l
```
This lists available capture devices. Update `card` and `device` accordingly.

### Audio Settings
Configured in `/Pi/audio.py`:
- **Sample Rate**: 48000 Hz
- **Channels**: 1 (mono) or 2 (stereo)
- **Frame Duration**: 20ms per packet
- **Codec**: Opus

## Usage

### Start GUI with Audio Support
```bash
python3 GUI/gui.py --robot --broker_port=2883
```
Audio is enabled by default on port 50052.

### Start Pi with Audio Streaming
```bash
./Pi/run_tiality.sh \
  --broker 10.1.1.78 \
  --broker_port 2883 \
  --video_server 10.1.1.78:50051 \
  --audio_server 10.1.1.78:50052 \
  --enable_audio
```

**Important**: Replace `10.1.1.78` with your GUI machine's IP address.

## Troubleshooting

### "AUDIO DISABLED: Required Opus components not available"
**Cause**: PyOgg is not installed on the GUI machine.

**Solution**:
```bash
pip install -r requirements.txt
```

### "Connection refused (111)"
**Cause**: GUI is not running or firewall is blocking the port.

**Solution**:
1. Ensure GUI is running first
2. Check firewall allows port 50052
3. Verify IP address is correct

### "module 'settings' has no attribute 'sample_rate'"
**Cause**: Settings module not properly initialized.

**Solution**: This should be fixed in the current version. Ensure you have the latest code.

### Audio Quality Issues
1. **Choppy audio**: Check network latency between Pi and GUI
2. **Delayed audio**: Normal; Opus encoding adds ~20ms algorithmic delay
3. **No audio**: Verify ALSA device is working:
   ```bash
   arecord -D hw:3,0 -f S16_LE -r 48000 test.wav
   ```

## Testing Audio Independently

### Test on Pi (without streaming)
```bash
cd Pi/ALSA_Capture_Stream
python main.py -c 1 -e 1 -d 3,0
```
This captures, encodes, and plays back 5 seconds of audio locally.

## Network Ports
- **Video**: 50051 (default)
- **Audio**: 50052 (default)
- **MQTT**: 2883 or 1883

## Performance Notes
- Audio packets are 20ms each (50 packets/second)
- Queue size: 100 packets (2 seconds buffer)
- Opus provides excellent compression (~32kbps for mono)
- Low latency: ~40-60ms end-to-end (capture to playback)

## Files Modified for Audio Support
- `/Pi/audio.py` - Audio capture and encoding worker
- `/tiality_server/grpc_audio_streaming/` - Audio streaming components
- `/tiality_server/grpc_audio_streaming/opus_decoder.py` - Standalone decoder
- `/tiality_server/server_manager.py` - Audio server integration
- `/tiality_server/server_utils.py` - Connection management
- `/Pi/tiality_manager.py` - Combined video/audio manager
- `/GUI/gui.py` - Audio playback integration
