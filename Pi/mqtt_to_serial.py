#!/usr/bin/env python3
import logging
import argparse
import serial
import paho.mqtt.client as mq
import time

# --- Configuration ---
# The serial port connected to the robot's motor controller on the Pi.
# For Pi 5, this is typically "/dev/ttyAMA0" for GPIO pins 14/15.
SERIAL_PORT = "/dev/ttyAMA0"
# Match the robot's baud rate, often 1,000,000 for these controllers.
BAUD_RATE = 1000000
# The IP address of your laptop running the Mosquitto MQTT broker.
MQTT_BROKER_HOST = "192.168.0.209"  # IMPORTANT: CHANGE THIS TO YOUR LAPTOP'S IP
TX_TOPIC = "robot/tx"  # Topic for messages FROM laptop TO Pi (and then to robot)
RX_TOPIC = "robot/rx"  # Topic for messages FROM Pi (and robot) TO laptop

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
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.01)
        logging.info(f"Opened serial port {SERIAL_PORT} at {BAUD_RATE} baud.")
    except serial.SerialException as e:
        logging.error(f"Could not open serial port {SERIAL_PORT}: {e}")
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
