import logging
import sys
import argparse
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

def publish_commands_worker(mqtt_port: int, broker_host_ip: str, command_queue: queue.Queue, tx_topic: str, shutdown_event):

    def publish_command(command: str, mqtt_client: mqtt.Client, tx_topic: str):
        """Publish command via MQTT."""
        try:
            mqtt_client.publish(tx_topic, payload=command, qos=0)
        except Exception as exc:
            print(f"Failed to publish MQTT message: {exc}", exc)
    
    mqtt_client = connect_mqtt(mqtt_port, broker_host_ip)
    topic = tx_topic
    
    try:
        while not shutdown_event.is_set():
            try:            
                # Attempt to retrieve new command
                command = command_queue.get_nowait()

                # Send command when available
                publish_command(command, mqtt_client, topic)

            except queue.Empty:
                # No command in queue
                continue

    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("Commands Worker Thread shutting down")




