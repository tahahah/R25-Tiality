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

**For audio support on the GUI machine:**

On **macOS**, first install native libraries:
```bash
brew install opus libogg opusfile
```

Then install Python packages:
```bash
pip install -r requirements.txt
```

On **Linux**:
```bash
sudo apt-get install libopus0 libogg0 libopusfile0
pip install -r requirements.txt
```

This will install PyOgg and sounddevice required for audio decoding and playback.

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

To enable audio streaming, add the `--enable_audio` flag and optionally specify the audio server:
```
./Pi/run_tiality.sh --broker 10.1.1.78 --broker_port 2883 --video_server 10.1.1.78:50051 --audio_server 10.1.1.78:50052 --enable_audio
```

If `--audio_server` is not specified, it defaults to `localhost:50052`.

**Note:** Audio streaming requires:
- ALSA audio device configured on the Pi (default: card 3, device 0)
- PyOgg and Opus libraries installed on Pi (handled by init_setup.sh)
- PyOgg installed on GUI machine (install via `pip install -r requirements.txt`)
- Audio server running on the GUI (enabled by default on port 50052)

