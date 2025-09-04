# 🎯 Gimbal Control System Setup Guide

This guide explains how to set up and use the integrated gimbal control system with your existing MQTT infrastructure.

## 📋 What's Been Added

Your existing `mqtt_to_pwm.py` has been enhanced with gimbal control capabilities:

- **Gimbal Controller Class**: Integrates with your existing `gimbalcode.py`
- **MQTT Command Handling**: Processes gimbal commands alongside motor commands
- **Pin Configuration**: Uses pins 12 (X-axis) and 13 (Y-axis) as requested
- **Error Handling**: Robust error handling and logging

## 🔧 Hardware Setup

### Servo Connections
- **X-axis servo (left/right)**: Connect to GPIO pin 12
- **Y-axis servo (up/down)**: Connect to GPIO pin 13
- **Power**: 5V supply for servos
- **Ground**: Common ground with Raspberry Pi

### Pin Layout
```
Raspberry Pi GPIO:
┌─────────┬─────────┐
│ Pin 12 │ Pin 13 │  ← Gimbal servos
│  (X)   │  (Y)   │
└─────────┴─────────┘
```

## 🚀 Setup Instructions

### 1. On Raspberry Pi

#### Install Dependencies
```bash
# Your existing setup.sh should handle this, but if needed:
sudo apt update
sudo apt install mosquitto mosquitto-clients
pip3 install paho-mqtt
```

#### Run the Enhanced Controller
```bash
# Navigate to MotorMoving folder
cd MotorMoving

# Run the enhanced mqtt_to_pwm.py (now with gimbal support)
python3 mqtt_to_pwm.py --broker localhost
```

#### Test Gimbal Locally (Optional)
```bash
# Test gimbal without MQTT
python3 test_gimbal.py
```

### 2. On Your Computer

#### Install Python Dependencies
```bash
pip install paho-mqtt pynput
```

#### Edit IP Address
Open `gimbal_remote.py` and change:
```python
PI_IP = "192.168.1.100"  # Change to your Pi's actual IP
```

#### Run Remote Control
```bash
python gimbal_remote.py
```

## 🎮 Control Commands

### MQTT Command Format
All gimbal commands use this JSON format:
```json
{
  "type": "gimbal",
  "action": "x_left",
  "degrees": 15
}
```

### Available Actions
| Action | Description | Parameters |
|--------|-------------|------------|
| `x_left` | Move left | `degrees` (default: 10) |
| `x_right` | Move right | `degrees` (default: 10) |
| `y_up` | Move up | `degrees` (default: 10) |
| `y_down` | Move down | `degrees` (default: 10) |
| `center` | Center both axes | None |
| `position` | Get current position | None |
| `set_angle` | Set specific angles | `x_angle`, `y_angle` |

### Keyboard Controls (Remote Client)
- **Arrow Keys**: Move gimbal in corresponding direction
- **Space**: Center gimbal
- **1-9**: Set movement degrees (5-45°)
- **0**: Get current position
- **ESC**: Exit

## 🔍 Testing & Troubleshooting

### Test Commands via MQTT
You can test using any MQTT client (like Mosquitto):

```bash
# Move left 20 degrees
mosquitto_pub -h YOUR_PI_IP -t "robot/tx" -m '{"type":"gimbal","action":"x_left","degrees":20}'

# Center gimbal
mosquitto_pub -h YOUR_PI_IP -t "robot/tx" -m '{"type":"gimbal","action":"center"}'

# Get position
mosquitto_pub -h YOUR_PI_IP -t "robot/tx" -m '{"type":"gimbal","action":"position"}'
```

### Common Issues

#### 1. Servos Not Moving
- Check power supply (servos need 5V)
- Verify GPIO pins (12 and 13)
- Check servo connections

#### 2. MQTT Connection Failed
- Verify Pi's IP address
- Check network connectivity
- Ensure Mosquitto is running

#### 3. Import Errors
- Make sure `gimbalcode.py` and `ServoClass.py` are in the same folder
- Check Python dependencies are installed

### Debug Mode
Run with debug logging:
```bash
python3 mqtt_to_pwm.py --loglevel debug
```

## 📁 File Structure
```
MotorMoving/
├── mqtt_to_pwm.py          # Enhanced with gimbal support
├── gimbalcode.py           # Your gimbal control logic
├── ServoClass.py           # Low-level servo control
├── gimbal_remote.py        # Remote control client
├── test_gimbal.py          # Local test script
├── setup.sh                # Your existing setup script
└── GIMBAL_SETUP.md         # This guide
```

## 🔄 Integration with Existing System

Your enhanced `mqtt_to_pwm.py` now handles both motor and gimbal commands:

- **Motor commands**: `{"type": "all", "action": "spool", ...}`
- **Gimbal commands**: `{"type": "gimbal", "action": "x_left", ...}`
- **Vector commands**: `{"type": "vector", "action": "set", ...}`

All commands go through the same MQTT topics (`robot/tx` and `robot/rx`).

## 🎯 Next Steps

1. **Test locally** on Pi with `test_gimbal.py`
2. **Run enhanced controller** with `python3 mqtt_to_pwm.py`
3. **Test remote control** from your computer
4. **Integrate with your GUI** if desired

## 🆘 Need Help?

If you encounter issues:
1. Check the logs for error messages
2. Verify hardware connections
3. Test with the local test script first
4. Ensure MQTT broker is running

Your gimbal should now be fully integrated with your existing MQTT infrastructure! 🎉
