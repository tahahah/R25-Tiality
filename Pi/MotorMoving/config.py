"""
Centralized configuration for R25-Tiality project
All IP addresses, network settings, and hardware pin configurations
"""
# MQTT Configuration
OPERATOR_IP = "10.1.1.71"
PI_IP = "10.1.1.228"
PI_MQTT_PORT = 2883

# MQTT Topics
MQTT_TOPIC_TX = "robot/tx"  # Vehicle commands to Pi
MQTT_TOPIC_RX = "robot/rx"  # Vehicle responses from Pi

# Gimbal-specific MQTT topics
GIMBAL_TOPIC_TX = "robot/gimbal/tx"  # Gimbal commands to Pi
GIMBAL_TOPIC_RX = "robot/gimbal/rx"  # Gimbal responses from Pi

# Network Settings
MQTT_KEEPALIVE = 60
MQTT_TIMEOUT = 5

# GUI Settings
DEFAULT_BACKGROUND_IMAGE = "wildlife_explorer.png"

# Motor Settings
DEFAULT_GIMBAL_DEGREES = 10
DEFAULT_MOTOR_SPEED = 0.5

# Gimbal Pin Configuration
GIMBAL_PIN_X = 12  # X-axis servo pin (left/right) - uses pigpio
GIMBAL_PIN_Y = 25  # Y-axis servo pin (up/down) - uses pigpio
GIMBAL_PIN_C = 24  # C-axis servo pin (crane up/down) - uses RPi.GPIO

# Servo Library Configuration
USE_PIGPIO_FOR_XY = True   # Use pigpio for X and Y axes (better performance)
USE_RPIGPIO_FOR_C = True   # Use RPi.GPIO for C axis (crane)
