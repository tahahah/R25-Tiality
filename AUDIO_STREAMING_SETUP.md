# MQTT Audio Streaming Setup

This document describes how to use the MQTT audio streaming feature between your Raspberry Pi (ALSA capture) and the GUI.

## Overview

The system streams Opus-encoded audio packets from the Raspberry Pi to the GUI via MQTT:
- **Pi Side**: Captures audio from ALSA device → Encodes with Opus → Publishes via MQTT
- **GUI Side**: Subscribes to MQTT topic → Decodes Opus packets → Plays audio via pygame

## Architecture

```
[Pi: ALSA Capture] → [Opus Encoder] → [MQTT Publisher] 
                                              ↓
                                    [MQTT Broker (Mosquitto)]
                                              ↓
[GUI: MQTT Subscriber] → [Opus Decoder] → [Pygame Audio Playback]
```

## Setup Instructions

### 1. Install Dependencies

#### On Raspberry Pi (ALSA_Capture_Stream):
```bash
cd ALSA_Capture_Stream
pip install -r requirements.txt
```

#### On GUI Machine:
```bash
# Install main requirements
pip install -r requirements.txt

# Install PyOgg (required for Opus decoding)
cd ALSA_Capture_Stream/PyOgg
pip install -e .
cd ../..
```

### 2. Start MQTT Broker

Make sure you have Mosquitto or another MQTT broker running. On macOS/Linux:
```bash
# Install mosquitto if needed
brew install mosquitto  # macOS
# or
sudo apt-get install mosquitto  # Linux

# Start broker
mosquitto
```

### 3. Run Audio Streaming

#### On Raspberry Pi:
```bash
cd ALSA_Capture_Stream
python main.py -c 1 -e 1 -d 3,0 --stream --broker <BROKER_IP> --port 1883
```

**Arguments:**
- `-c 1`: Capture 1 channel
- `-e 1`: Encode 1 channel
- `-d 3,0`: ALSA device card 3, device 0
- `--stream`: Enable MQTT streaming
- `--broker`: MQTT broker IP (default: localhost)
- `--port`: MQTT broker port (default: 1883)

#### On GUI Machine:
```bash
python GUI/gui.py --robot --broker <BROKER_IP> --broker_port 1883 --audio
```

**Arguments:**
- `--robot`: Run in robot mode
- `--broker`: MQTT broker IP address
- `--broker_port`: MQTT broker port
- `--audio`: Enable MQTT audio streaming reception

## MQTT Topics

- **Audio Stream**: `robot/audio/tx` (Pi → GUI)
- **Vehicle Commands**: `robot/tx` (GUI → Pi)
- **Gimbal Commands**: `robot/gimbal/tx` (GUI → Pi)

## Packet Format

Audio packets are sent as binary with the following structure:
```
[4 bytes: header_length][JSON header][Opus encoded audio data]
```

**Header fields:**
- `timestamp`: Epoch milliseconds when encoded
- `sequence_number`: Monotonically increasing packet counter
- `packet_length`: Length of encoded audio data
- `algorithm_delay`: Opus encoder algorithmic delay

## Audio Settings

Default configuration (defined in `ALSA_Capture_Stream/settings.py`):
- **Sample Rate**: 48000 Hz
- **Frame Duration**: 20 ms (960 samples per frame)
- **Format**: int16
- **Codec**: Opus
- **MQTT QoS**: 0 (lowest latency, no acknowledgment)

## Troubleshooting

### No audio playback in GUI:
1. Check that MQTT broker is running and accessible
2. Verify PyOgg is installed correctly
3. Check firewall settings for MQTT port 1883
4. Enable debug logging in GUI to see packet reception

### Audio dropouts or latency:
1. Reduce buffer_size in `AudioMQTTSubscriber` (currently 10 packets)
2. Check network bandwidth and latency
3. Verify Pi can encode faster than real-time (check "Wall-to-wall time" warnings)

### Connection issues:
1. Ensure broker IP is correct on both sides
2. Check MQTT broker logs for connection attempts
3. Verify network connectivity between Pi and GUI machine

## Performance Notes

- **Latency**: Typically 200-500ms depending on network and buffer size
- **Bandwidth**: ~20-40 kbps for mono audio at 48kHz
- **CPU Usage**: Minimal (Opus is highly efficient)

## File Locations

### Raspberry Pi (ALSA_Capture_Stream):
- `main.py`: Modified to add MQTT streaming
- `audio_mqtt_publisher.py`: MQTT publisher module
- `requirements.txt`: Updated with paho-mqtt

### GUI:
- `gui.py`: Modified to integrate audio subscriber
- `audio_mqtt_subscriber.py`: MQTT subscriber and decoder module
- `requirements.txt`: Updated with audio codec dependencies
