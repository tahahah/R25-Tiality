# R25-Tiality


## Operating Instructions
The code has been designed so that the servers for the robot sits on the operating PC. The mosquitto broker will also sit on the operating PC.

### Mosquitto Broker
If you are running the mosquitto broker on macos (not on the Pi), you're going to want to setup a config to ensure there are no issues connecting on different ipvx.
A config can be setup as follows
```
cat > /tmp/mqtt-test.conf <<'EOF'
allow_anonymous true
socket_domain ipv4
listener 2883 0.0.0.0
EOF
```
The mosquitto broker host can then be ran as follows:
```
mosquitto -c /tmp/mqtt-test.conf -v
```

### GUI
The gui can be run after packages have been installed from requirements.txt. Ensure the port number for the broker host is added.
```
python3 GUI/gui.py --robot --broker_port=<port_number>
```

### Pi
The robot requires an initial setup of the virtual environment, ENSURE NO SUDO IS USED. All the following commands are operated from the R25-Tiality directory:
```
chmod +x Pi/init_setup.sh
./Pi/init_setup.sh
```
To run the tiality pi operating script, here is an example script:
```
./Pi/run_tiality.sh --broker 10.1.1.78 --broker_port 2883 --video_server 10.1.1.78:50051
```

### One-command local orchestration
Use the helper to auto-discover the MQTT broker and the Pi, then run the Pi setup and start services remotely (tmux if available):
```
scripts/setup_robot.sh \
  --broker-candidates "192.168.0.115,10.1.1.78" \
  --broker-ports "1883,2883" \
  --pi-candidates "192.168.0.114,raspberrypi.local" \
  --pi-user pi \
  --remote-dir "~/R25-Tiality-worktree" \
  --video-port 50051
```

Flags:
- `--no-video`: start only MQTT->PWM on the Pi
- `--identity PATH`: SSH key to use
- `--broker-host-for-pi HOST`: override broker host passed to Pi (useful if local broker is `localhost`)
- `--dry-run`: print actions without executing

After it runs, you can attach on the Pi with:
```
ssh pi@<pi_ip> "tmux ls; tmux attach -t tiality"
```

Run the local pygame client (optional):
```
python3 pygame_video_mqtt_client.py --pi_ip <pi_ip> --grpc_port 50051 --broker <broker_host>
```

