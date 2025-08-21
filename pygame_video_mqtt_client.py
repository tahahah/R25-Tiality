import logging
import sys
import argparse
from typing import Optional

import cv2
import grpc
import numpy as np
import time
import paho.mqtt.client as mqtt
import pygame
import json

# Allow importing generated gRPC stubs no matter where they live
sys.path.extend(["Pi", "app"])  # 'app' for historical reasons
import video_stream_pb2 as pb2
import video_stream_pb2_grpc as pb2g

# ------------------------ Default Configuration ------------------------
PI_IP_ADDRESS = "192.168.0.114"  # Change to your Raspberry Pi's IP
GRPC_PORT = 50051
MQTT_BROKER_HOST = "192.168.0.114"  # Pi now runs the MQTT broker (same as PI_IP_ADDRESS)
TX_TOPIC = "robot/tx"

# Client-side adjustable motor compensation (mirrors Pi defaults)
# Used to send config updates to the Pi at runtime
COMPENSATION = {
    "forward": [1.0, 0.85, 1.0, 0.85],
    "reverse": [1.0, 0.85, 1.0, 0.85],
}
COMP_DIR = "forward"   # which set we are editing: "forward" or "reverse"
COMP_SELECTED = 0       # selected motor index [0..3]
COMP_STEP = 0.05        # adjustment step per keypress
COMP_MIN, COMP_MAX = 0.5, 1.5


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


def format_joystick_axes(joystick: "pygame.joystick.Joystick", deadzone: float = 0.1) -> Optional[str]:
    """Return a human-readable direction string from axes 0 (x) and 1 (y).

    Examples: "right: 0.62, up: 0.98" or "left: 0.32, down: 0.54".
    Returns None if both axes are within the deadzone.
    """
    try:
        x_input = joystick.get_axis(0)  # Left/Right
        y_input = joystick.get_axis(1)  # Up/Down (often inverted)
    except Exception:
        return None

    parts = []
    # X axis -> left/right
    if x_input > deadzone:
        parts.append(f"right: {x_input:.2f}")
    elif x_input < -deadzone:
        parts.append(f"left: {abs(x_input):.2f}")

    # Y axis -> up/down (note: many controllers report up as negative)
    if y_input < -deadzone:
        parts.append(f"up: {abs(y_input):.2f}")
    elif y_input > deadzone:
        parts.append(f"down: {y_input:.2f}")

    if not parts:
        return None
    return ", ".join(parts)


# ----------------------------- Main Loop ------------------------------

def stream_and_display(pi_ip: str, grpc_port: int, broker_host: str, use_video: bool):
    mqtt_client = connect_mqtt(broker_host)

    pygame.init()
    # Joystick setup
    pygame.joystick.init()
    joystick = pygame.joystick.Joystick(0) if pygame.joystick.get_count() > 0 else None
    if joystick is not None:
        joystick.init()
        logging.info("Joystick detected: %s", joystick.get_name())
    else:
        logging.warning("No joystick detected. Only keyboard MQTT events will be sent.")

    screen: Optional[pygame.Surface] = None
    clock = pygame.time.Clock()
    # Throttle joystick MQTT publishes and avoid duplicates
    DEADZONE = 0.10
    SEND_INTERVAL = 0.10  # seconds
    last_send_time = 0.0
    last_payload: Optional[str] = None
    # Ramp time for spool commands (ms)
    SPOOL_RAMP_MS = 2000

    try:
        if use_video:
            stub = connect_grpc(pi_ip, grpc_port)
            if stub is None:
                logging.error("Video disabled due to gRPC connection failure; continuing with joystick-only mode.")
                # Fall through to joystick-only loop below
                use_video = False
            else:
                # Request video stream
                stream = stub.StreamFrames(pb2.Empty())

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

                    # Read joystick axes and publish direction string to MQTT
                    if joystick is not None:
                        msg = format_joystick_axes(joystick, DEADZONE)
                        now = time.time()
                        if msg and (now - last_send_time >= SEND_INTERVAL) and msg != last_payload:
                            try:
                                mqtt_client.publish(TX_TOPIC, payload=msg.encode(), qos=0)
                            except Exception as exc:
                                logging.error("Failed to publish joystick MQTT message: %s", exc)
                            last_payload = msg
                            last_send_time = now

                    # Aim for ~30 Hz UI refresh independent of incoming frames
                    clock.tick(30)

        # Joystick-only loop (runs if use_video is False, or if video failed above)
        while not use_video:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt
                elif event.type == pygame.KEYDOWN:
                    handle_key_event(event, mqtt_client)

            if joystick is not None:
                msg = format_joystick_axes(joystick, DEADZONE)
                now = time.time()
                if msg and (now - last_send_time >= SEND_INTERVAL):
                    try:
                        mqtt_client.publish(TX_TOPIC, payload=msg.encode(), qos=0)
                    except Exception as exc:
                        logging.error("Failed to publish joystick MQTT message: %s", exc)
                    last_payload = msg
                    last_send_time = now

            clock.tick(60)
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
    # Map certain keys to structured JSON commands for precise motor control
    cmd = None
    if key_name in ("up", "w"):
        cmd = {"type": "all", "action": "spool", "direction": "forward", "target": 100, "ramp_ms": 2000}
    elif key_name in ("down", "s", "x"):
        cmd = {"type": "all", "action": "spool", "direction": "reverse", "target": 100, "ramp_ms": 2000}
    elif key_name in ("space",):
        cmd = {"type": "all", "action": "stop"}

    # --- Compensation editing shortcuts ---
    # 1-4: select motor index
    # f/r: choose which direction set to edit
    # +/-: increase/decrease selected factor
    # c:   send current factors for the active direction to the Pi
    # z:   reset active direction factors to [1,1,1,1]
    global COMP_SELECTED, COMP_DIR, COMPENSATION
    if key_name in ("1", "2", "3", "4"):
        COMP_SELECTED = int(key_name) - 1
        logging.info("Selected motor index: %d", COMP_SELECTED)
    elif key_name == "f":
        COMP_DIR = "forward"
        logging.info("Editing compensation set: forward -> %s", COMPENSATION[COMP_DIR])
    elif key_name == "r":
        COMP_DIR = "reverse"
        logging.info("Editing compensation set: reverse -> %s", COMPENSATION[COMP_DIR])
    elif key_name in ("+", "="):
        vals = COMPENSATION[COMP_DIR]
        vals[COMP_SELECTED] = max(COMP_MIN, min(COMP_MAX, vals[COMP_SELECTED] + COMP_STEP))
        logging.info("Compensation %s[%d] increased -> %.2f", COMP_DIR, COMP_SELECTED, vals[COMP_SELECTED])
    elif key_name in ("-", "_"):
        vals = COMPENSATION[COMP_DIR]
        vals[COMP_SELECTED] = max(COMP_MIN, min(COMP_MAX, vals[COMP_SELECTED] - COMP_STEP))
        logging.info("Compensation %s[%d] decreased -> %.2f", COMP_DIR, COMP_SELECTED, vals[COMP_SELECTED])
    elif key_name == "z":
        COMPENSATION[COMP_DIR] = [1.0, 1.0, 1.0, 1.0]
        logging.info("Compensation %s reset -> %s", COMP_DIR, COMPENSATION[COMP_DIR])
    elif key_name == "c":
        # Send the updated factors for the current direction
        try:
            payload_bytes = json.dumps({
                "type": "config",
                "action": "set_compensation",
                "direction": COMP_DIR,
                "factors": COMPENSATION[COMP_DIR],
            }).encode()
            mqtt_client.publish(TX_TOPIC, payload=payload_bytes, qos=0)
            logging.info("Sent compensation update for %s: %s", COMP_DIR, COMPENSATION[COMP_DIR])
        except Exception as exc:
            logging.error("Failed to publish compensation update: %s", exc)
        return

    payload_bytes: bytes
    if cmd is not None:
        payload_bytes = json.dumps(cmd).encode()
    else:
        # Fallback to publishing raw key name
        payload_bytes = key_name.encode()

    try:
        mqtt_client.publish(TX_TOPIC, payload=payload_bytes, qos=0)
    except Exception as exc:
        logging.error("Failed to publish MQTT message: %s", exc)


# ----------------------------- Entrypoint -----------------------------


def parse_args():
    parser = argparse.ArgumentParser(description="Pygame video client with MQTT keyboard input")
    parser.add_argument("--pi_ip", default=PI_IP_ADDRESS, help="Raspberry Pi IP address hosting gRPC server")
    parser.add_argument("--grpc_port", type=int, default=GRPC_PORT, help="gRPC port")
    parser.add_argument("--broker", default=MQTT_BROKER_HOST, help="MQTT broker host (Pi IP address)")
    parser.add_argument("--loglevel", default="info", choices=["debug", "info", "warning", "error", "critical"], help="Logging level")
    parser.add_argument("--no-video", action="store_true", help="Disable video; run joystick→MQTT only")
    return parser.parse_args()


def main():
    args = parse_args()
    log_level = getattr(logging, args.loglevel.upper())
    logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")

    use_video = not args.no_video
    stream_and_display(args.pi_ip, args.grpc_port, args.broker, use_video)


if __name__ == "__main__":
    main()
