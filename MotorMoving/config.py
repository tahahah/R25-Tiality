"""
Centralized configuration for R25-Tiality project
All IP addresses, network settings, and hardware pin configurations
"""
# Raspberry Pi Configuration
PI_IP = "10.1.1.178"
PI_MQTT_PORT = 1883

# MQTT Topics
MQTT_TOPIC_TX = "robot/tx"  # Commands to Pi
MQTT_TOPIC_RX = "robot/rx"  # Responses from Pi

# Network Settings
MQTT_KEEPALIVE = 60
MQTT_TIMEOUT = 5

# GUI Settings
DEFAULT_BACKGROUND_IMAGE = "wildlife_explorer.png"

# Motor Settings
DEFAULT_GIMBAL_DEGREES = 10
DEFAULT_MOTOR_SPEED = 0.5

# Gimbal Pin Configuration
GIMBAL_PIN_X = 18  # X-axis servo pin (left/right) - uses pigpio
GIMBAL_PIN_Y = 19  # Y-axis servo pin (up/down) - uses pigpio
GIMBAL_PIN_C = 22  # C-axis servo pin (crane up/down) - uses RPi.GPIO

# Servo Library Configuration
USE_PIGPIO_FOR_XY = True   # Use pigpio for X and Y axes (better performance)
USE_RPIGPIO_FOR_C = True   # Use RPi.GPIO for C axis (crane)
