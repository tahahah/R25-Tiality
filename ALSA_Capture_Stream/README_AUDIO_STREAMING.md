# UDP Audio Streaming for R25-Tiality

This document describes how to use the UDP audio streaming feature to send real-time audio from the Raspberry Pi to the GUI.

## Overview

The audio streaming system consists of two main components:

1. **UDP Audio Sender** (Pi side) - Captures, encodes, and sends audio via UDP
2. **UDP Audio Receiver** (GUI side) - Receives, decodes, and plays audio in real-time

### Architecture

```
Pi (ALSA Capture) → Opus Encoder → UDP Sender → Network → UDP Receiver → Opus Decoder → Audio Playback (GUI)
```

## Features

- **Low Latency**: UDP streaming with minimal buffering
- **Efficient Encoding**: Opus codec for high-quality, low-bitrate audio
- **Packet Loss Handling**: Automatic detection and statistics tracking
- **Jitter Buffering**: Compensates for network timing variations
- **Real-time Stats**: Monitor packet counts, data rates, and dropped packets

## Setup

### Pi Side Requirements

Already installed via `requirements.txt`:
- `sounddevice` - ALSA audio capture
- `PyOgg` - Opus encoding
- `numpy` - Audio processing

### GUI Side Requirements

Add to GUI requirements (if not already present):
```bash
pip install sounddevice numpy
```

You'll also need PyOgg on the GUI machine for decoding. Copy the PyOgg directory from `ALSA_Capture_Stream/PyOgg` to your GUI environment or install it separately.

## Usage

### 1. Start the GUI (Receiver)

On your GUI machine (laptop/desktop):

```bash
# With audio streaming enabled (default)
python GUI/gui.py --robot --broker <PI_IP> --audio --audio_port 5005

# Disable audio streaming
python GUI/gui.py --robot --broker <PI_IP> --no-audio
```

**Arguments**:
- `--audio` - Enable audio streaming (default: True)
- `--no-audio` - Disable audio streaming
- `--audio_port` - UDP port to listen on (default: 5005)

### 2. Start Audio Streaming on Pi

On your Raspberry Pi:

```bash
# Stream audio to GUI
python main.py -c 1 -e 1 -d 3,0 --stream --host <GUI_IP> --port 5005

# Test mode (record and playback locally, no streaming)
python main.py -c 1 -e 1 -d 3,0
```

**Arguments**:
- `-c, --capch` - Number of capture channels (1, 2, or 4)
- `-e, --encch` - Number of encoded channels (1 or 2)
- `-d, --device` - ALSA device as `<card>,<device>` (e.g., `3,0`)
- `-s, --stream` - Enable UDP streaming mode
- `--host` - Target IP address for streaming (default: localhost)
- `--port` - Target UDP port (default: 5005)
- `--duration` - Recording duration in test mode (default: 5 seconds)

### 3. Example: Complete Setup

**On GUI machine (192.168.1.100):**
```bash
python GUI/gui.py --robot --broker 192.168.1.50 --audio --audio_port 5005
```

**On Pi (192.168.1.50):**
```bash
python main.py -c 1 -e 1 -d 3,0 --stream --host 192.168.1.100 --port 5005
```

## Audio Configuration

### Sample Rate
- Default: **48000 Hz**
- Configured in `settings.py`

### Frame Duration
- Default: **20 ms** packets
- Configured in `settings.py`

### Encoding
- Codec: **Opus**
- Quality: Adaptive bitrate based on audio complexity
- Channels: Mono (1) or Stereo (2)

### Network Settings

**UDP Packet Size**:
- Maximum: 1400 bytes (to avoid IP fragmentation)
- Typical encoded packet: 100-400 bytes

**Jitter Buffer**:
- Default: 10 packets (~200ms buffering)
- Configurable in `UDPAudioReceiver` constructor

## Monitoring & Debugging

### Pi Side Statistics

The sender prints statistics every 100 packets:
```
Sent 100 packets, 35420 bytes
Sent 200 packets, 70840 bytes
...
```

### GUI Side Statistics

Access audio statistics in the GUI:
```python
stats = gui.get_audio_stats()
print(stats)
# Output: {
#   'packets_received': 250,
#   'packets_dropped': 2,
#   'bytes_received': 88550,
#   'packet_queue_size': 3,
#   'playback_queue_size': 5
# }
```

### Common Issues

**No audio on GUI**:
1. Check firewall allows UDP on port 5005
2. Verify Pi and GUI are on same network/reachable
3. Check GUI logs for audio receiver errors
4. Ensure PyOgg is installed on GUI machine

**Audio dropouts/stuttering**:
1. Network congestion - check packet_dropped count
2. Increase jitter buffer size in `udp_audio_receiver.py`
3. Reduce network traffic or improve connection quality

**High latency**:
1. Reduce jitter buffer size (trade-off with stability)
2. Check for network bottlenecks
3. Ensure Pi isn't overloaded (check CPU usage)

## File Reference

### Pi Side
- `main.py` - Main capture/streaming script
- `udp_audio_sender.py` - UDP sender implementation
- `encoder_object.py` - Opus encoder wrapper
- `capture_object.py` - ALSA audio capture
- `settings.py` - Audio configuration

### GUI Side
- `gui.py` - Main GUI with integrated audio receiver
- `udp_audio_receiver.py` - UDP receiver with playback
- `decoder_object.py` - Opus decoder (copy from Pi)

## Advanced Configuration

### Changing Audio Quality

Edit `encoder_object.py` to adjust Opus settings:
```python
# Lower latency, lower quality
self.encoder.set_application("audio")  # or "voip" for voice
self.encoder.set_bitrate(32000)  # bits per second

# Higher quality
self.encoder.set_bitrate(96000)
```

### Network Optimization

For WiFi networks with high packet loss:
```python
# In udp_audio_receiver.py, increase buffer
self.audio_receiver = UDPAudioReceiver(
    jitter_buffer_size=20,  # More buffering (higher latency)
    ...
)
```

For wired/low-latency networks:
```python
self.audio_receiver = UDPAudioReceiver(
    jitter_buffer_size=5,  # Less buffering (lower latency)
    ...
)
```

## Performance Metrics

Typical performance on Raspberry Pi 4:

- **Capture + Encode**: ~2-5ms per 20ms frame
- **Network transmission**: <1ms on local network
- **Decode + Playback**: ~2-5ms per frame
- **Total latency**: ~100-200ms (including jitter buffer)

## Testing

### Standalone Receiver Test
```bash
cd GUI
python udp_audio_receiver.py
```

### Standalone Sender Test
```bash
cd ALSA_Capture_Stream
python udp_audio_sender.py
```

### Loopback Test (Same Machine)
```bash
# Terminal 1: Start receiver
cd GUI
python udp_audio_receiver.py

# Terminal 2: Start sender to localhost
cd ALSA_Capture_Stream
python main.py -c 1 -e 1 -d 3,0 --stream --host localhost --port 5005
```

## Troubleshooting

### Import Errors on GUI

If you get `ImportError: No module named 'pyogg'`:
```bash
# Copy PyOgg from Pi or install separately
pip install pyogg  # May require system libraries
```

Or copy the entire PyOgg directory:
```bash
cp -r ALSA_Capture_Stream/PyOgg/ GUI/
```

### Permission Errors on Pi

If you get audio device permission errors:
```bash
# Add user to audio group
sudo usermod -a -G audio $USER
# Log out and back in
```

### Socket Binding Errors

If port 5005 is already in use:
```bash
# Find process using port
sudo netstat -tulpn | grep 5005
# Kill process or use different port
python main.py ... --port 5006
python gui.py ... --audio_port 5006
```

## Future Enhancements

Potential improvements:
- [ ] Automatic network discovery (mDNS/Bonjour)
- [ ] Adaptive jitter buffering based on network conditions
- [ ] Audio visualization in GUI
- [ ] Multiple audio stream support (stereo separation)
- [ ] Encryption for secure transmission
- [ ] Automatic reconnection on network failure

## License

Part of the R25-Tiality project.
