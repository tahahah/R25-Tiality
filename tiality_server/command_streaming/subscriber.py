#!/usr/bin/env python3
import logging
import argparse
import serial
import paho.mqtt.client as mq
import time
import queue
from dataclasses import dataclass
from typing import Callable

@dataclass
class mqtt_subscriber_dataclass():
    """
    Dataclass

    Args:
        mqtt_broker_host_ip (str): _description_
        mqtt_port (int): _description_
        mqtt_topic (str): _description_
        mqtt_command_queue (queue.Queue()): Queue to read commands off of
        mqtt_command_decoding_func (Callable[[str], dict]): Decoding function to decode command messages to a dictionary.
    """
        
    mqtt_broker_host_ip: str
    mqtt_port: int
    mqtt_topic: str
    mqtt_command_queue: queue.Queue
    mqtt_command_decoding_func: Callable[[str], dict]

    

def on_connect(client, userdata, flags, rc):
    """Callback for when the client connects to the broker."""
    if rc == 0:
        client.subscribe(userdata.mqtt_topic) 
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
    # # Log the received message first for debugging.
    command_str = msg.payload
    try:
        # Clear any old command that hasn't been used yet.
        userdata.mqtt_command_queue.get_nowait() 
    except queue.Empty:
        # This is normal, the queue was already empty.
        pass

    try:
        # Put the newest, most relevant command into the queue.
        command = userdata.mqtt_command_decoding_func(command_str)
        userdata.mqtt_command_queue.put_nowait(command)
    except queue.Full:
        # Sender is processing a command already.
        pass
    except Exception as e:
        print(f"Unknown Exception: {e}")


def setup_command_subscriber(mqtt_port: int, broker_host_ip: str, command_queue: queue.Queue, tx_topic: str, connection_established_event, message_decode_func: Callable[[str], dict]) -> mq.Client:
    """
    RUN IN SEPERATE THREAD
    Run method 
    """

    # Setup subscriber client
    sub_client = mq.Client()
    sub_client_data = mqtt_subscriber_dataclass(
        mqtt_broker_host_ip=broker_host_ip,
        mqtt_port=mqtt_port,
        mqtt_topic=tx_topic,
        mqtt_command_queue = command_queue,
        mqtt_command_decoding_func = message_decode_func
        )
    sub_client.user_data_set(sub_client_data)
    sub_client.on_connect = on_connect
    sub_client.on_message = on_message

    # Attempt to connect to the broker host
    try:
        sub_client.connect(
            sub_client_data.mqtt_broker_host_ip,
            sub_client_data.mqtt_port,
            60
            )
        connection_established_event.set()
    except Exception as e:
        print(f"Could not connect to MQTT broker at {sub_client_data.mqtt_broker_host_ip}: {e}") 

    if connection_established_event.is_set():
        sub_client.loop_start()
        
    return sub_client
