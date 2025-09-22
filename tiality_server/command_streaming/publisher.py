import logging
import sys
import argparse
import json
from typing import Optional

import cv2
import grpc
import numpy as np
import paho.mqtt.client as mqtt
import pygame
import queue

def connect_mqtt(mqtt_port: int, broker_host_ip: str) -> mqtt.Client:
    """Initialise and connect an MQTT client (loop runs in background)."""
    client = mqtt.Client()

    def _on_connect(cli, _userdata, _flags, rc):
        if rc == 0:
            logging.info("Connected to MQTT broker at %s", broker_host_ip)
        else:
            logging.error("Failed to connect to MQTT broker (rc=%s)", rc)

    client.on_connect = _on_connect
    client.connect(broker_host_ip, mqtt_port, 60)
    client.loop_start()
    return client

def publish_commands_worker(mqtt_port: int, broker_host_ip: str, command_queue: queue.Queue, vehicle_tx_topic: str, gimbal_tx_topic: str, shutdown_event):

    def determine_topic(command: str) -> str:
        """Determine which topic to use based on command content."""
        try:
            cmd_data = json.loads(command)
            if isinstance(cmd_data, dict) and cmd_data.get("type") == "gimbal":
                return gimbal_tx_topic
            else:
                return vehicle_tx_topic
        except (json.JSONDecodeError, AttributeError):
            # If not valid JSON or no type field, assume vehicle command
            return vehicle_tx_topic
    
    def publish_command(command: str, mqtt_client: mqtt.Client):
        """Publish command to appropriate topic via MQTT."""
        try:
            topic = determine_topic(command)
            mqtt_client.publish(topic, payload=command, qos=0)
            logging.debug(f"Published command to {topic}: {command[:100]}...")  # Log first 100 chars
        except Exception as exc:
            print(f"Failed to publish MQTT message: {exc}", exc)
    
    mqtt_client = connect_mqtt(mqtt_port, broker_host_ip)
    logging.info(f"Command router initialized - Vehicle: {vehicle_tx_topic}, Gimbal: {gimbal_tx_topic}")
    
    try:
        while not shutdown_event.is_set():
            try:            
                # Attempt to retrieve new command
                command = command_queue.get_nowait()

                # Send command when available
                publish_command(command, mqtt_client)

            except queue.Empty:
                # No command in queue
                continue

    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("Commands Worker Thread shutting down")




