# Raspberry Pi Bridge Services

This directory contains two lightweight services that run on the Raspberry Pi next to the robot's motor controller:

| Purpose | Transport | Script |
|---------|-----------|--------|
| Motor-bus serial bridge (command / telemetry) | **MQTT** | `mqtt_to_serial.py` |
| Camera video stream | **WebRTC** | `webrtc_server.py` |

Running both at the same time lets you tele-operate the robot while viewing a live camera feed, each over the protocol that best suits the data type.

---

## 1  Serial ⇄ MQTT Bridge

`mqtt_to_serial.py` connects the Feetech bus (`/dev/ttyAMA0`, 1 Mbps) to two MQTT topics:

* **`robot/tx`** – bytes from laptop → Pi → serial bus
* **`robot/rx`** – bytes from serial bus → Pi → laptop

### Install requirements
```bash
pip install -r requirements.txt   # includes paho-mqtt, pyserial
```

### Run on the Pi
The setup script will automatically install and start a local Mosquitto MQTT broker on the Pi:
```bash
./setup.sh
```
This will start both the WebRTC video server and MQTT-to-serial bridge with a local broker.

Alternatively, run manually:
```bash
# Start local MQTT broker
mosquitto -d

# Start the bridge (uses localhost by default)
python3 mqtt_to_serial.py
```
Leave this terminal open; the script prints connection / error logs.

### Run on the laptop
Robot code should connect to the Pi's MQTT broker using `robot.port=mqtt://<PI_IP>` (handled by `MQTTSerial`).

---

## 2  Camera → WebRTC Stream

`webrtc_server.py` captures video from the Raspberry Pi camera (using `picamera2`) or USB camera and streams it over WebRTC. It uses MQTT for signaling to establish the WebRTC connection.

### How WebRTC + MQTT Signaling Works

The system uses a hybrid approach where **MQTT handles signaling** and **WebRTC handles video streaming**:

#### MQTT Signaling Topics:
* **`webrtc/offer`** – Client sends WebRTC connection offer
* **`webrtc/answer`** – Pi responds with WebRTC connection answer
* **`webrtc/ice`** – ICE candidates for connection establishment

#### Connection Flow:
1. **Client connects** to Pi's MQTT broker
2. **Client sends offer** via `webrtc/offer` topic containing WebRTC session description
3. **Pi receives offer**, creates peer connection, adds camera track
4. **Pi sends answer** via `webrtc/answer` topic with session response
5. **WebRTC connection established** - video flows directly peer-to-peer
6. **Client displays video** using OpenCV in real-time

### Camera Support

The server automatically detects and uses the best available camera:

* **Primary**: Raspberry Pi Camera via `picamera2` (recommended)
* **Fallback**: USB camera via OpenCV (`/dev/video0`)

### Requirements

All dependencies are handled by the setup script:
* System packages: `python3-picamera2`, `python3-opencv`, `python3-numpy`  
* Python packages: `paho-mqtt`, `aiortc`, `av`

### Run on the Pi

```bash
./setup.sh
```

This automatically:
* Installs system dependencies (`picamera2`, `opencv`, `mosquitto`)
* Creates virtual environment with system package access
* Starts MQTT broker and WebRTC server
* Starts MQTT-to-serial bridge

### Run on the laptop

```bash
python webrtc_client.py        # Update PI_IP_ADDRESS in the file first
```

The client will:
* Connect to Pi's MQTT broker
* Initiate WebRTC connection via MQTT signaling
* Display live video stream in OpenCV window
* Press **`q`** to close the video window

### Code Architecture

#### Server (`webrtc_server.py`):
```python
class CameraVideoTrack(VideoStreamTrack):
    # Captures frames from Pi camera or USB camera
    # Converts to WebRTC video frames with proper timestamps
    
class WebRTCServer:
    # Handles MQTT signaling (offer/answer/ICE)
    # Manages WebRTC peer connections
    # Adds camera track to connections
```

#### Client (`webrtc_client.py`):
```python
class WebRTCClient:
    # Connects to MQTT broker for signaling
    # Creates WebRTC peer connection  
    # Sends offers and handles answers via MQTT
    # Receives video track and displays with OpenCV
```

---

## Why MQTT **and** WebRTC?

| Requirement                       | Best fit | Why |
|-----------------------------------|----------|-----|
| Motor commands & telemetry (<1 kB/s) must survive brief Wi-Fi drops | **MQTT** | Built-in QoS & broker buffering keep state while either side reconnects. Low header overhead suits bursty bytes. |
| Live video (hundreds kB/s) needs low-latency, direct flow | **WebRTC** | Peer-to-peer streaming with adaptive bitrate and built-in error correction. No server bottleneck. |
| WebRTC connection setup | **MQTT** | Reliable signaling channel for offer/answer exchange. Simple pub/sub model for connection negotiation. |

Using MQTT for signaling and WebRTC for video gives the robot:
* **Robust control** - MQTT ensures commands get through even with network hiccups
* **Low-latency video** - WebRTC provides real-time video with automatic quality adaptation  
* **Local network optimized** - No external STUN/TURN servers needed
* **Simple setup** - Single MQTT broker handles both control and video signaling

---

## Troubleshooting Cheatsheet

| Symptom | Fix |
|---------|-----|
| `Permission denied /dev/ttyAMA0` | `sudo usermod -a -G dialout $USER` (reboot) |
| `Could not open camera /dev/video0` | Ensure user is in `video` group; verify with `v4l2-ctl --list-devices` |
| `picamera2 import error` | Run `sudo apt install python3-picamera2` and recreate venv with `--system-site-packages` |
| `numpy.dtype size changed` error | Use system packages: remove venv and re-run `./setup.sh` |
| MQTT timeout | Ensure Mosquitto is running on Pi: `pgrep mosquitto`. Check firewall for port 1883. |
| WebRTC connection fails | Check MQTT broker connectivity and ensure both client/server can access broker |
| No video frames | Verify camera permissions and that camera is not in use by other processes |