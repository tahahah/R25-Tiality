# Audio Streaming Integration Guide

## Overview

This document explains how audio streaming has been implemented using gRPC, following the same architectural pattern as the existing video streaming service.

---

## Architecture Comparison

### Video Streaming (Existing)
```
Pi Camera → JPEG Encode → gRPC Client → GUI Server → Decoder → Display
```

### Audio Streaming (New)
```
Pi Microphone (ALSA) → Opus Encode → gRPC Client → GUI Server → Decoder → Playback
```

Both follow the **same pattern**:
1. **Capture** raw data on Pi
2. **Encode** to compressed format
3. **Stream** via gRPC client-streaming RPC
4. **Receive** on GUI server
5. **Decode** in worker thread
6. **Output** to user

---

## Implementation Details

### 1. gRPC Service Definition

**Location:** `tiality_server/grpc_audio_streaming/audio_streaming.proto`

```protobuf
service AudioStreaming {
  rpc StreamAudio (stream AudioPacket) returns (StreamResponse) {}
}

message AudioPacket {
  bytes packet_data = 1;          // Opus-encoded audio (20ms packets)
  int64 timestamp = 2;             // Epoch time in milliseconds
  int32 sequence_number = 3;       // For packet ordering
  int32 algorithm_delay = 4;       // Opus decoder delay compensation
}
```

**Key Design Decisions:**
- **Client-streaming RPC**: Pi sends continuous stream of packets
- **20ms packet size**: Balances latency vs compression efficiency
- **Opus codec**: Industry-standard, low-latency audio compression
- **Metadata included**: Timestamp and sequence for synchronization

### 2. Pi-Side Implementation

**Location:** `Pi/audio.py`

**Components:**

#### Audio Capture (`ALSA_Capture_Stream/capture_object.py`)
- Captures from USB microphone via ALSA
- Sample rate: 48kHz
- Channels: 4 (microphone array) → 2 (encoded stereo)
- Format: 16-bit signed PCM

#### Audio Encoding (`ALSA_Capture_Stream/encoder_object.py`)
- Uses Opus codec via PyOgg library
- Produces 20ms packets (~960 samples at 48kHz)
- Includes metadata: timestamp, sequence number, algorithm delay

#### gRPC Client (`tiality_server/grpc_audio_streaming/client.py`)
- Streams packets to GUI server
- Auto-reconnection on disconnect (5s backoff)
- Queue-based buffering (maxsize=5 packets)

**Usage:**
```python
import tiality_server
from Pi.audio import pi_audio_manager_worker, packet_generator_alsa

# Start audio streaming
server_addr = "gui_ip_address:50052"  # Note: different port from video
device_config = {"card": 1, "device": 0}  # ALSA device

pi_audio_manager_worker(server_addr, packet_generator_alsa, device_config)
```

### 3. GUI-Side Implementation

**Location:** `tiality_server/grpc_audio_streaming/`

**Components:**

#### gRPC Server (`server.py`)
- Receives audio packets from Pi
- Runs on separate port (e.g., 50052)
- Thread-safe queue for incoming packets
- Graceful reconnection handling

#### Decoder Worker (`decoder_worker.py`)
- Decodes Opus packets to PCM
- Runs in separate thread
- Outputs to decoded audio queue

**Server Setup:**
```python
import queue
import threading
from tiality_server.grpc_audio_streaming import server as audio_server

# Create queues
incoming_audio_queue = queue.Queue(maxsize=1)
decoded_audio_queue = queue.Queue(maxsize=1)

# Start server
audio_server_thread = threading.Thread(
    target=audio_server.serve,
    args=(50052, incoming_audio_queue, connection_event, shutdown_event)
)
audio_server_thread.start()
```

### 4. Audio Decoding & Playback

**Decoder Function Example:**
```python
from ALSA_Capture_Stream.decoder_object import DecoderObject
import settings

# Initialize settings
settings.init()
settings.encoded_channels = 2
decoder = DecoderObject()

def decode_audio_packet(packet_data):
    """Decode Opus packet to PCM bytes"""
    return decoder.decode(packet_data)
```

**Playback Example (using sounddevice):**
```python
import sounddevice as sd
import numpy as np

def play_audio_packet(decoded_packet):
    """Play decoded audio packet"""
    audio_bytes = decoded_packet['audio_data']
    audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
    
    # Reshape for stereo
    if settings.encoded_channels > 1:
        audio_array = audio_array.reshape(-1, settings.encoded_channels)
    
    sd.play(audio_array, samplerate=settings.sample_rate)
```

---

## Integration Steps

### Step 1: Install Dependencies

**On Pi (Raspberry Pi Zero 2):**
```bash
# Navigate to ALSA_Capture_Stream
cd ALSA_Capture_Stream

# Install system dependencies
sudo apt install libasound2-dev libogg-dev libopus-dev libopusfile-dev libopusenc-dev libportaudio2

# Install Python packages
pip3 install -r requirements.txt
```

**On GUI (Operator Computer):**
```bash
# Install audio playback library
pip3 install sounddevice numpy
```

### Step 2: Update Server Manager

Modify `tiality_server/server_manager.py` to include audio server:

```python
class TialityServerManager:
    def __init__(self, grpc_video_port: int, grpc_audio_port: int, ...):
        # Existing video queues
        self.incoming_video_queue = queue.Queue(maxsize=1)
        self.decoded_video_queue = queue.Queue(maxsize=1)
        
        # Add audio queues
        self.incoming_audio_queue = queue.Queue(maxsize=1)
        self.decoded_audio_queue = queue.Queue(maxsize=1)
        
        # Ports
        self.grpc_video_port = grpc_video_port
        self.grpc_audio_port = grpc_audio_port  # NEW
```

### Step 3: Update Connection Manager

Modify `tiality_server/server_utils.py` to start audio server thread alongside video server.

### Step 4: Start Pi Audio Stream

In your Pi startup script (e.g., `Pi/run_tiality.sh`):

```python
import threading
from Pi.video import pi_video_manager_worker, frame_generator_picamera2
from Pi.audio import pi_audio_manager_worker, packet_generator_alsa

# Video streaming
video_thread = threading.Thread(
    target=pi_video_manager_worker,
    args=("gui_ip:50051", frame_generator_picamera2),
    daemon=True
)
video_thread.start()

# Audio streaming (NEW)
audio_thread = threading.Thread(
    target=pi_audio_manager_worker,
    args=("gui_ip:50052", packet_generator_alsa),
    daemon=True
)
audio_thread.start()
```

### Step 5: GUI Audio Playback

Add audio playback to your GUI main loop:

```python
# In GUI main loop
audio_packet = server_manager.get_audio_packet()  # Similar to get_video_frame()
if audio_packet:
    play_audio_packet(audio_packet)
```

---

## Configuration Reference

### Audio Settings

**Default Configuration (from `ALSA_Capture_Stream/settings.py`):**
- **Sample Rate**: 48000 Hz
- **Captured Channels**: 4 (microphone array)
- **Encoded Channels**: 2 (stereo)
- **Frame Duration**: 20ms
- **Frame Samples**: 960 (at 48kHz)
- **Frame Format**: int16 (16-bit PCM)
- **Queue Size**: 100 packets (2 seconds buffer)

### ALSA Device Detection

**Find your microphone:**
```bash
# List all audio devices
arecord -l -L

# Check USB enumeration
sudo lsusb -v -d cafe:  # For MicNode_4_Ch microphone array
```

**Expected device for 4-channel microphone:**
- Card: 1 (or higher, depending on system)
- Device: 0
- ALSA device string: `hw:1,0`

### Port Configuration

| Service | Default Port | Protocol |
|---------|-------------|----------|
| Video Streaming | 50051 | gRPC |
| Audio Streaming | 50052 | gRPC |
| MQTT Commands | 1883 | MQTT |

---

## Troubleshooting

### Pi-Side Issues

**1. Microphone Not Detected**
```bash
# Verify USB connection
sudo lsusb -v

# Check ALSA registration
arecord -l

# Test manual recording
arecord -f S16_LE -r 48000 -c 4 -D hw:1,0 test.wav
```

**2. PyOgg Import Errors**
```bash
# Ensure PyOgg is installed from local directory
cd ALSA_Capture_Stream
pip3 install -e PyOgg/
```

**3. Permission Issues**
```bash
# Add user to audio group
sudo usermod -a -G audio $USER
```

### GUI-Side Issues

**1. No Audio Output**
- Check if `decoded_audio_queue` is receiving packets
- Verify sounddevice backend: `python3 -m sounddevice`
- Test audio output: `sd.play(np.zeros(48000), 48000)`

**2. Audio Latency**
- Reduce buffer sizes in queues (trade stability for latency)
- Ensure decoder worker is running in separate thread
- Check network latency: `ping pi_ip_address`

**3. Audio Choppy/Distorted**
- Verify sample rate matches (48kHz)
- Check for packet loss (monitor sequence numbers)
- Ensure CPU isn't overloaded

---

## Performance Considerations

### Network Bandwidth

**Audio Stream:**
- Opus bitrate: ~64-128 kbps (stereo)
- Packet size: ~200-400 bytes per 20ms
- Total throughput: ~10-20 KB/s

**Combined (Video + Audio):**
- Video: ~500 KB/s (JPEG at 30fps)
- Audio: ~15 KB/s
- **Total: ~515 KB/s** (well within WiFi capabilities)

### CPU Usage (Pi Zero 2)

- **Audio Capture**: <5% CPU
- **Opus Encoding**: ~10-15% CPU
- **gRPC Streaming**: <5% CPU
- **Combined with Video**: ~60-70% total CPU

### Latency Budget

| Component | Latency |
|-----------|---------|
| Audio Capture | ~20ms |
| Opus Encoding | <5ms |
| Network Transfer | 20-50ms (WiFi) |
| Opus Decoding | <5ms |
| Audio Playback | ~20ms (buffer) |
| **Total End-to-End** | **70-100ms** |

---

## Testing

### Unit Test: Audio Capture
```bash
cd ALSA_Capture_Stream
python3 main.py -c 4 -e 2 -d 1,0
# Should record 5 seconds and play back
```

### Integration Test: Pi → GUI Stream

**On GUI:**
```python
# Run audio server
python3 -c "
from tiality_server.grpc_audio_streaming import server
import queue, threading
q = queue.Queue()
e = threading.Event()
server.serve(50052, q, e, e)
"
```

**On Pi:**
```python
# Run audio client
python3 -c "
from Pi.audio import pi_audio_manager_worker, packet_generator_alsa
pi_audio_manager_worker('gui_ip:50052', packet_generator_alsa)
"
```

---

## Next Steps

1. **Integrate into Server Manager**: Modify `server_manager.py` and `server_utils.py` to include audio alongside video
2. **Add GUI Audio Player**: Create audio playback widget in `GUI/gui.py`
3. **Synchronize A/V**: Use timestamps to align audio and video streams
4. **Add Audio Controls**: Volume, mute, channel selection
5. **Monitor Performance**: Add metrics for latency, packet loss, buffer levels

---

## Code Files Summary

### New Files Created
- `tiality_server/grpc_audio_streaming/audio_streaming.proto` - gRPC service definition
- `tiality_server/grpc_audio_streaming/server.py` - Audio server implementation
- `tiality_server/grpc_audio_streaming/client.py` - Audio client implementation
- `tiality_server/grpc_audio_streaming/decoder_worker.py` - Audio decoder thread
- `tiality_server/grpc_audio_streaming/audio_streaming_pb2.py` - Protobuf messages
- `tiality_server/grpc_audio_streaming/audio_streaming_pb2_grpc.py` - gRPC stubs
- `Pi/audio.py` - Pi audio capture and streaming manager

### Modified Files
- `tiality_server/__init__.py` - Added audio streaming imports

### Files To Modify (User Action Required)
- `tiality_server/server_manager.py` - Add audio queues and methods
- `tiality_server/server_utils.py` - Start audio server thread
- `GUI/gui.py` - Add audio playback functionality
- `Pi/run_tiality.sh` - Start audio streaming thread

---

## References

- **Video Streaming Pattern**: `tiality_server/grpc_video_streaming/`
- **ALSA Audio Capture**: `ALSA_Capture_Stream/`
- **Mechatronics Integration**: `Mechatronics Integration (1).md`
- **gRPC Documentation**: https://grpc.io/docs/languages/python/
- **Opus Codec**: https://opus-codec.org/
