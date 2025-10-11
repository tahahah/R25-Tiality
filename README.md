# R25-Tiality


## Operating Instructions
The code has been designed so that the servers for the robot sits on the operating PC. The mosquitto broker will also sit on the operating PC.

### Auto Update -

### One Command Setup

```bash
./init_setup_operator.sh
```

This script will:
- Install deps + venv 
- Start the MQTT Broker on your machine 
- Display your IP addresses for Pi configuration
- Create helper scripts for easy operation

## Running the GUI
```bash
./run_gui.sh
```

Two other scripts are created.

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

#### Audio Classification Duration
To change the duration of audio classification (e.g., from 5 seconds to 10 seconds), edit the `AUDIO_CLASSIFICATION_DURATION` parameter in `GUI/gui_config.py`:

```python
@dataclass
class AudioInferenceConfig:
    """Audio inference state."""
    AUDIO_INFERENCE_AVAILABLE: bool = True
    AUDIO_MODEL_NAME: str = "audio_weights.ckpt"
    AUDIO_CLASSIFICATION_DURATION: float = 10.0  # Change this value
```

This single parameter controls:
- Audio buffer size (how much audio history is stored)
- Classification duration (how many seconds are analyzed when pressing 'R')
- Help text display (automatically updates to show current duration)

### Pi
The robot requires an initial setup of the virtual environment, ENSURE NO SUDO IS USED. All the following commands are operated from the R25-Tiality directory:

Note: Pi script does not have the auto update and for audio there are a few more args that you need to pass:

--audio_host 


```
chmod +x Pi/init_setup.sh
./Pi/init_setup.sh
```
To run the tiality pi operating script, here is an example script:
```
./Pi/run_tiality.sh --broker 10.1.1.78 --broker_port 2883 --video_server 10.1.1.78:50051

bash run_tiality.sh --broker 10.1.1.78  --broker_port 2883 --video_server 10.1.1.78:50051 --audio_host 10.1.1.78
```

