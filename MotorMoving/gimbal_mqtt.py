#!/usr/bin/env python3
"""
Simple MQTT to PWM Gimbal Controller for Raspberry Pi
Controls 3-axis gimbal using SG90 servos on GPIO pins 18, 22, 27
Receives commands from GUI via MQTT
"""
import argparse
import json
import logging
import threading
import time
import sys
import os

import paho.mqtt.client as mqtt

# Import config
from config import PI_IP, MQTT_TOPIC_TX, MQTT_TOPIC_RX, PI_MQTT_PORT, GIMBAL_PIN_X, GIMBAL_PIN_Y, GIMBAL_PIN_C

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except (ImportError, RuntimeError):
    print("Warning: RPi.GPIO not available. Motor control will not work on this system.")
    GPIO_AVAILABLE = False
    GPIO = None

# Import gimbal controller
from gimbalcode import GimbalController


def main():
    parser = argparse.ArgumentParser(description="MQTT -> Gimbal PWM controller")
    parser.add_argument("--broker", default=PI_IP, help="MQTT broker host")
    parser.add_argument("--loglevel", default="info", choices=["debug", "info", "warning", "error", "critical"], help="Logging level")
    args = parser.parse_args()

    log_level = getattr(logging, args.loglevel.upper())
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    # Initialize GPIO once
    if GPIO_AVAILABLE and GPIO:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        logging.info("GPIO initialized for gimbal controller")

    # Initialize gimbal controller
    try:
        gimbal = GimbalController(x_pin=GIMBAL_PIN_X, y_pin=GIMBAL_PIN_Y, c_pin=GIMBAL_PIN_C)
        logging.info(f"Gimbal initialized on pins X:{GIMBAL_PIN_X}, Y:{GIMBAL_PIN_Y}, C:{GIMBAL_PIN_C}")
    except Exception as e:
        logging.error(f"Failed to initialize gimbal: {e}")
        return

    # MQTT client
    client = mqtt.Client()

    def on_connect(cli, _userdata, _flags, rc):
        if rc == 0:
            logging.info("Connected to MQTT broker at %s", args.broker)
            cli.subscribe(MQTT_TOPIC_TX)
            logging.info("Subscribed to %s", MQTT_TOPIC_TX)
        else:
            logging.error("Failed to connect to MQTT broker rc=%s", rc)

    def on_message(cli, _userdata, msg):
        payload = msg.payload.decode("utf-8", errors="ignore")
        logging.info("RX %s: %s", msg.topic, payload)
        
        try:
            cmd = json.loads(payload)
            if not isinstance(cmd, dict):
                return
                
            # Handle gimbal commands
            if cmd.get("type") == "gimbal":
                action = cmd.get("action", "")
                degrees = float(cmd.get("degrees", 2))  # Default 2 degrees
                
                try:
                    if action == "x_left":
                        gimbal.x_left(degrees)
                        cli.publish(MQTT_TOPIC_RX, json.dumps({"status": "gimbal", "action": "x_left", "degrees": degrees}))
                    elif action == "x_right":
                        gimbal.x_right(degrees)
                        cli.publish(MQTT_TOPIC_RX, json.dumps({"status": "gimbal", "action": "x_right", "degrees": degrees}))
                    elif action == "y_up":
                        gimbal.y_up(degrees)
                        cli.publish(MQTT_TOPIC_RX, json.dumps({"status": "gimbal", "action": "y_up", "degrees": degrees}))
                    elif action == "y_down":
                        gimbal.y_down(degrees)
                        cli.publish(MQTT_TOPIC_RX, json.dumps({"status": "gimbal", "action": "y_down", "degrees": degrees}))
                    elif action == "c_up":
                        gimbal.c_up(degrees)
                        cli.publish(MQTT_TOPIC_RX, json.dumps({"status": "gimbal", "action": "c_up", "degrees": degrees}))
                    elif action == "c_down":
                        gimbal.c_down(degrees)
                        cli.publish(MQTT_TOPIC_RX, json.dumps({"status": "gimbal", "action": "c_down", "degrees": degrees}))
                    elif action == "center":
                        gimbal.center_gimbal()
                        cli.publish(MQTT_TOPIC_RX, json.dumps({"status": "gimbal", "action": "center"}))
                    else:
                        cli.publish(MQTT_TOPIC_RX, json.dumps({"status": "error", "message": f"Unknown gimbal action: {action}"}))
                        
                except Exception as e:
                    logging.error(f"Error handling gimbal command: {e}")
                    cli.publish(MQTT_TOPIC_RX, json.dumps({"status": "error", "message": str(e)}))
            else:
                logging.warning("Non-gimbal command ignored: %s", cmd)
                
        except json.JSONDecodeError:
            logging.warning("Invalid JSON command: %s", payload)
        except Exception as e:
            logging.exception("Error processing command: %s", e)

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.broker, 1883, 60)
    except Exception as e:
        logging.error("Could not connect to MQTT broker: %s", e)
        return

    client.loop_start()
    logging.info("Gimbal MQTT controller running. Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        logging.info("Shutting down")
    finally:
        client.loop_stop()
        client.disconnect()
        try:
            gimbal.cleanup()
        except Exception as e:
            logging.error(f"Error cleaning up gimbal: {e}")
        if GPIO_AVAILABLE and GPIO:
            GPIO.cleanup()


if __name__ == "__main__":
    main()
