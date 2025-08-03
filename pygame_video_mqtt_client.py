import logging
import sys
import argparse
from typing import Optional

import cv2
import grpc
import numpy as np
import paho.mqtt.client as mqtt
import pygame

# Allow importing generated gRPC stubs no matter where they live
sys.path.extend(["Pi", "app"])  # 'app' for historical reasons
import video_stream_pb2 as pb2
import video_stream_pb2_grpc as pb2g

# ------------------------ Default Configuration ------------------------
PI_IP_ADDRESS = "192.168.0.151"  # Change to your Raspberry Pi's IP
GRPC_PORT = 50051
MQTT_BROKER_HOST = "192.168.0.209"  # Change to your laptop/host running Mosquitto
TX_TOPIC = "robot/tx"


# ----------------------------- Functions ------------------------------

def connect_grpc(pi_ip: str, port: int) -> Optional[pb2g.VideoStreamStub]:
    """Create a gRPC channel and return a VideoStreamStub if successful."""
    channel_address = f"{pi_ip}:{port}"
    logging.info("Connecting to gRPC server at %s", channel_address)

    channel = grpc.insecure_channel(channel_address)
    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        logging.error("Timeout connecting to gRPC server at %s", channel_address)
        return None
    return pb2g.VideoStreamStub(channel)


def connect_mqtt(broker_host: str) -> mqtt.Client:
    """Initialise and connect an MQTT client (loop runs in background)."""
    client = mqtt.Client()

    def _on_connect(cli, _userdata, _flags, rc):
        if rc == 0:
            logging.info("Connected to MQTT broker at %s", broker_host)
        else:
            logging.error("Failed to connect to MQTT broker (rc=%s)", rc)

    client.on_connect = _on_connect
    client.connect(broker_host, 1883, 60)
    client.loop_start()
    return client


# ----------------------------- Main Loop ------------------------------

def stream_and_display(pi_ip: str, grpc_port: int, broker_host: str):
    stub = connect_grpc(pi_ip, grpc_port)
    if stub is None:
        return

    mqtt_client = connect_mqtt(broker_host)

    # Request video stream
    stream = stub.StreamFrames(pb2.Empty())

    pygame.init()
    screen: Optional[pygame.Surface] = None
    clock = pygame.time.Clock()

    try:
        for frame_data in stream:
            # Decode JPEG -> ndarray (BGR)
            frame_bgr = cv2.imdecode(
                np.frombuffer(frame_data.jpeg_data, dtype=np.uint8), cv2.IMREAD_COLOR
            )
            if frame_bgr is None:
                logging.warning("Received empty frame; skipping")
                continue

            # Convert to RGB for pygame
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w, _ = frame_rgb.shape

            # Create the window the first time we know the frame size
            if screen is None:
                screen = pygame.display.set_mode((w, h))
                pygame.display.set_caption("Pi Camera Stream (pygame)")

            # Convert to Surface and blit
            surface = pygame.image.frombuffer(frame_rgb.tobytes(), (w, h), "RGB")
            screen.blit(surface, (0, 0))
            pygame.display.flip()

            # Handle pygame events (keyboard, quit, etc.)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt
                elif event.type == pygame.KEYDOWN:
                    handle_key_event(event, mqtt_client)

            # Aim for ~30 Hz UI refresh independent of incoming frames
            clock.tick(30)
    except KeyboardInterrupt:
        logging.info("User requested shutdown.")
    except grpc.RpcError as e:
        logging.error("gRPC error: %s - %s", e.code(), e.details())
    finally:
        pygame.quit()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


def handle_key_event(event: pygame.event.Event, mqtt_client: mqtt.Client):
    """Publish KEYDOWN events to MQTT so that they are printed on the Pi side."""
    # Use pygame's key name for readability (e.g. "up", "a", etc.)
    key_name = pygame.key.name(event.key)
    logging.debug("Key pressed: %s", key_name)

    try:
        mqtt_client.publish(TX_TOPIC, payload=key_name.encode(), qos=0)
    except Exception as exc:
        logging.error("Failed to publish MQTT message: %s", exc)


# ----------------------------- Entrypoint -----------------------------


def parse_args():
    parser = argparse.ArgumentParser(description="Pygame video client with MQTT keyboard input")
    parser.add_argument("--pi_ip", default=PI_IP_ADDRESS, help="Raspberry Pi IP address hosting gRPC server")
    parser.add_argument("--grpc_port", type=int, default=GRPC_PORT, help="gRPC port")
    parser.add_argument("--broker", default=MQTT_BROKER_HOST, help="MQTT broker host (laptop/host IP)")
    parser.add_argument("--loglevel", default="info", choices=["debug", "info", "warning", "error", "critical"], help="Logging level")
    return parser.parse_args()


def main():
    args = parse_args()
    log_level = getattr(logging, args.loglevel.upper())
    logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")

    stream_and_display(args.pi_ip, args.grpc_port, args.broker)


if __name__ == "__main__":
    main()
