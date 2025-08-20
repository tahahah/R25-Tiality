#!/usr/bin/env python3
import logging
import argparse
import serial
import paho.mqtt.client as mq
import time
import glob
import os

# --- Configuration ---
# The serial port connected to the robot's motor controller on the Pi.
POSSIBLE_SERIAL_PORTS = [
    "/dev/ttyAMA0",     # Pi 4/5 primary UART
    "/dev/ttyS0",       # Pi 4/5 mini UART  
    "/dev/ttyAMA1",     # Pi 4/5 secondary UART
    "/dev/ttyUSB0",     # USB serial adapter
    "/dev/ttyUSB1",     # USB serial adapter (second)
]
SERIAL_PORT = "/dev/ttyAMA0"  # Default, will be auto-detected

# Match the robot's baud rate, often 1,000,000 for these controllers.
BAUD_RATE = 1000000

MQTT_BROKER_HOST = "localhost"  # Pi runs the MQTT broker locally
TX_TOPIC = "robot/tx"  # Topic for messages FROM clients TO Pi (and then to robot)
RX_TOPIC = "robot/rx"  # Topic for messages FROM Pi (and robot) TO clients

def find_serial_port():
    """Auto-detect the available serial port from common possibilities."""
    # First try the specified port if it exists
    if os.path.exists(SERIAL_PORT):
        return SERIAL_PORT
    
    # Try other common serial ports
    for port in POSSIBLE_SERIAL_PORTS:
        if os.path.exists(port):
            logging.info(f"Auto-detected serial port: {port}")
            return port
    
    # Try glob patterns for USB devices
    usb_ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
    if usb_ports:
        port = usb_ports[0]
        logging.info(f"Auto-detected USB serial port: {port}")
        return port
    
    # List available ports for troubleshooting
    available = glob.glob('/dev/tty*')
    logging.error(f"No suitable serial port found. Available ports: {available}")
    logging.error("Try enabling UART with: sudo raspi-config -> Interface Options -> Serial Port")
    return None

parser = argparse.ArgumentParser(description="MQTT:left_right_arrow:Serial bridge for Feetech bus")
parser.add_argument("--loglevel", default="info", choices=["debug", "info", "warning", "error", "critical"], help="Set logging level")
parser.add_argument("--serial_port", default=SERIAL_PORT, help="Serial device path e.g. /dev/ttyUSB0")
parser.add_argument("--baud", type=int, default=BAUD_RATE, help="Serial baud rate")
parser.add_argument("--broker", default=MQTT_BROKER_HOST, help="MQTT broker host")
args = parser.parse_args()
SERIAL_PORT = args.serial_port
BAUD_RATE = args.baud
MQTT_BROKER_HOST = args.broker
log_level = getattr(logging, args.loglevel.upper())
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

def on_connect(client, userdata, flags, rc):
    """Callback for when the client connects to the broker."""
    if rc == 0:
        logging.info(f"Successfully connected to MQTT Broker at {MQTT_BROKER_HOST}")
        client.subscribe(TX_TOPIC)
        logging.info(f"Subscribed to topic: '{TX_TOPIC}'")
    else:
        # Provide a more descriptive error message based on the return code.
        err_msg = {
            1: "Connection refused - incorrect protocol version",
            2: "Connection refused - invalid client identifier",
            3: "Connection refused - server unavailable",
            4: "Connection refused - bad username or password",
            5: "Connection refused - not authorised"
        }.get(rc, "Unknown error")
        logging.error(f"Failed to connect to MQTT broker: {err_msg} (rc: {rc})")

def on_message(client, userdata, msg):
    """Callback for when a message is received from the MQTT broker."""
    # Log the received message first for debugging.
    payload_str = msg.payload.decode('utf-8', errors='ignore')
    logging.info(f"MQTT RX on '{msg.topic}': {payload_str}")

    try:
        # Forward the raw payload to the serial port.
        ser.write(msg.payload)
        logging.debug(f"Wrote to serial: {msg.payload.hex()}")
    except Exception as e:
        logging.error(f"Error writing to serial port: {e}")

# --- Main script ---
if __name__ == "__main__":
    # Auto-detect or use specified serial port
    detected_port = find_serial_port()
    if detected_port is None:
        logging.error("No serial port available. Please check your hardware configuration.")
        exit(1)
    
    # Override with command line argument if provided
    if args.serial_port != SERIAL_PORT:
        detected_port = args.serial_port
        logging.info(f"Using command-line specified port: {detected_port}")
    
    try:
        ser = serial.Serial(detected_port, BAUD_RATE, timeout=0.01)
        logging.info(f"Opened serial port {detected_port} at {BAUD_RATE} baud.")
    except serial.SerialException as e:
        logging.error(f"Could not open serial port {detected_port}: {e}")
        logging.error("Common solutions:")
        logging.error("  1. Enable UART: sudo raspi-config -> Interface Options -> Serial Port")
        logging.error("  2. Add user to dialout group: sudo usermod -a -G dialout $USER")
        logging.error("  3. Check hardware connections")
        logging.error("  4. Use --serial_port to specify a different port")
        exit(1)

    client = mq.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER_HOST, 1883, 60)
    except Exception as e:
        logging.error(f"Could not connect to MQTT broker at {MQTT_BROKER_HOST}: {e}")
        exit(1)

    client.loop_start()

    logging.info("Bridge started. Forwarding messages between MQTT and serial.")
    try:
        while True:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                client.publish(RX_TOPIC, data, qos=0)
                logging.debug(f"Read from serial and published to MQTT: {data.hex()}")
            time.sleep(0.001)  # Prevent high CPU usage
    except KeyboardInterrupt:
        logging.info("Shutting down bridge.")
    finally:
        client.loop_stop()
        client.disconnect()
        ser.close()
        logging.info("Bridge stopped.")
