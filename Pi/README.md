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
pip install -r app/requirements.txt   # includes paho-mqtt, pyserial
```

### Run on the Pi
```bash
python3 app/mqtt_to_serial.py \
        --broker <LAPTOP_IP>          # e.g. 192.168.0.127
```
Leave this terminal open; the script prints connection / error logs.

### Run on the laptop
Robot code should use `robot.port=mqtt://<laptop_ip>` (already handled by `MQTTSerial`).

---

## 2  Camera → gRPC Stream

`video_server.py` opens `/dev/video0` (USB camera) and streams JPEG frames over a gRPC bi-directional stream.

### Requirements
All dependencies for both MQTT and gRPC services are already listed in `app/requirements.txt`, so no extra installation steps are needed.

### Run on the Pi
```bash
python3 app/video_server.py   # listens on :50051
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
| MQTT timeout | Check broker IP, `docker run -p 1883:1883 eclipse-mosquitto`, open firewall port 1883 |
| gRPC timeout | Ensure `video_server.py` is running and port 50051 reachable |
