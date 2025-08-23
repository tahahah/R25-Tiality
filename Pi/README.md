# Raspberry Pi Bridge Services

This directory contains two lightweight services that run on the Raspberry Pi next to the robot’s motor controller:

| Purpose | Transport | Script |
|---------|-----------|--------|
| Motor-bus serial bridge (command / telemetry) | **MQTT** | `mqtt_to_serial.py` |
| Camera video stream | **gRPC** | `video_server.py` |

Running both at the same time lets you tele-operate the robot while viewing a live camera feed, each over the protocol that best suits the data type.

---

## 1  Serial ⇄ MQTT Bridge

`mqtt_to_serial.py` connects the Feetech bus (`/dev/ttyAMA0`, 1 Mbps) to two MQTT topics:

* **`robot/tx`** – bytes from laptop → Pi → serial bus
* **`robot/rx`** – bytes from serial bus → Pi → laptop

### Install requirements
```bash
pip install -r Pi/requirements.txt   # includes paho-mqtt, pyserial, grpc, OpenCV, GPIO shim
```

### Run on the Pi
The setup script will automatically install and start a local Mosquitto MQTT broker on the Pi:
```bash
./setup.sh
```
This will start both the video server and MQTT-to-serial bridge with a local broker.

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
Use the pygame client to connect:
```bash
python pygame_video_mqtt_client.py --pi_ip <PI_IP>
```

---

## 2  Camera → gRPC Stream

`video_server.py` opens `/dev/video0` (USB camera) and streams JPEG frames over a gRPC bi-directional stream.

### Requirements
All dependencies for both MQTT and gRPC services are already listed in `app/requirements.txt`, so no extra installation steps are needed.

### Run on the Pi
```bash
python3 Pi/video_server.py   # listens on :50051
```

### Run on the laptop
```bash
python video_client.py        # PI_IP is configured inside the file
```
Press **`q`** to close the preview window.

---

## Why MQTT **and** gRPC?

| Requirement                       | Best fit | Why |
|-----------------------------------|----------|-----|
| Motor commands & telemetry (<1 kB/s) must survive brief Wi-Fi drops | **MQTT** | Built-in QoS & broker buffering keep state while either side reconnects. Low header overhead suits bursty bytes. |
| Live video (hundreds kB/s) needs low-latency, direct flow | **gRPC** | HTTP/2 streaming avoids the extra broker hop and supports large continuous payloads. No MQTT topic management needed. |

Using both protocols in parallel gives the robot the **robustness** of MQTT for critical control while getting the **performance** of gRPC for high-bandwidth video, all on a single Wi-Fi link.

---

## Troubleshooting Cheatsheet

| Symptom | Fix |
|---------|-----|
| `Permission denied /dev/ttyAMA0` | `sudo usermod -a -G dialout taha` (reboot) |
| `Could not open camera /dev/video0` | Ensure user is in `video` group or run with sudo; verify with `v4l2-ctl --list-devices` |
| MQTT timeout | Ensure Mosquitto is running on Pi: `pgrep mosquitto`. Check firewall if connecting from other devices. |
| gRPC timeout | Ensure `video_server.py` is running and port 50051 reachable |

---

## Raspberry Pi 5 GPIO notes

On Raspberry Pi 5, the legacy `RPi.GPIO` stack is not provided by default. This repo uses the drop-in compatible shim `rpi-lgpio` backed by `libgpiod`.

Install once on the Pi 5:

```bash
sudo apt update && sudo apt install -y python3-lgpio
pip install rpi-lgpio
```

Then run the motor PWM script as usual:

```bash
python3 Pi/mqtt_to_pwm.py --broker localhost
```

If you see `ImportError: RPi.GPIO module not found`, follow the installation steps above.
