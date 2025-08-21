#!/usr/bin/env python3
import argparse
import json
import logging
import threading
import time
from typing import List, Tuple, Optional

import paho.mqtt.client as mqtt
try:
    import RPi.GPIO as GPIO
except RuntimeError:
    # Allow import-time failure messaging when run off-Pi
    raise

# ---------------- Configuration ----------------
# BCM pin numbers
ENABLE_PINS: List[int] = [22, 27, 19, 26]
INPUT_PINS: List[int] = [2, 3, 4, 17, 6, 13, 5, 11]  # 8 pins -> 4 pairs
PWM_FREQUENCY_HZ = 1000
DEFAULT_RAMP_MS = 2000

MQTT_BROKER_HOST = "localhost"
TX_TOPIC = "robot/tx"
RX_TOPIC = "robot/rx"

assert len(INPUT_PINS) == 8, "Expect 8 input pins (2 per motor)"
MOTOR_PAIRS: List[Tuple[int, int]] = [
    (INPUT_PINS[0], INPUT_PINS[1]),
    (INPUT_PINS[2], INPUT_PINS[3]),
    (INPUT_PINS[4], INPUT_PINS[5]),
    (INPUT_PINS[6], INPUT_PINS[7]),
]
assert len(ENABLE_PINS) == 4, "Expect 4 enable pins (one per motor)"


class Motor:
    def __init__(self, en_pin: int, in_a: int, in_b: int, freq_hz: int):
        self.en_pin = en_pin
        self.in_a = in_a
        self.in_b = in_b
        self.pwm = GPIO.PWM(en_pin, freq_hz)
        self.pwm.start(0)
        self._duty = 0.0
        self._dir = "stop"  # forward | reverse | stop
        self._lock = threading.Lock()

    def set_direction(self, direction: str):
        # forward -> A=1, B=0; reverse -> A=0, B=1; stop (coast) -> A=0, B=0
        with self._lock:
            self._dir = direction
            if direction == "forward":
                GPIO.output(self.in_a, GPIO.HIGH)
                GPIO.output(self.in_b, GPIO.LOW)
            elif direction == "reverse":
                GPIO.output(self.in_a, GPIO.LOW)
                GPIO.output(self.in_b, GPIO.HIGH)
            else:  # stop/coast
                GPIO.output(self.in_a, GPIO.LOW)
                GPIO.output(self.in_b, GPIO.LOW)

    def set_duty(self, duty: float):
        # duty: 0..100
        duty = max(0.0, min(100.0, float(duty)))
        with self._lock:
            self._duty = duty
            self.pwm.ChangeDutyCycle(duty)

    def get_duty(self) -> float:
        with self._lock:
            return self._duty

    def stop(self):
        self.set_duty(0)
        self.set_direction("stop")


class MotorController:
    def __init__(self, enable_pins: List[int], motor_pairs: List[Tuple[int, int]], freq_hz: int):
        GPIO.setmode(GPIO.BCM)
        # Setup pins
        for pin in enable_pins:
            GPIO.setup(pin, GPIO.OUT)
        for a, b in motor_pairs:
            GPIO.setup(a, GPIO.OUT)
            GPIO.setup(b, GPIO.OUT)

        self.motors: List[Motor] = [
            Motor(en, a, b, freq_hz) for en, (a, b) in zip(enable_pins, motor_pairs)
        ]
        self._spool_thread: Optional[threading.Thread] = None
        self._spool_cancel = threading.Event()

    def cleanup(self):
        for m in self.motors:
            try:
                m.stop()
            except Exception:
                pass
        GPIO.cleanup()

    def set_all(self, direction: str, speed: float):
        for m in self.motors:
            m.set_direction(direction)
            m.set_duty(speed)

    def stop_all(self):
        for m in self.motors:
            m.stop()

    def spool_all(self, direction: str, target: float, ramp_ms: int):
        # Cancel existing spool if any
        self._spool_cancel.set()
        if self._spool_thread and self._spool_thread.is_alive():
            self._spool_thread.join(timeout=0.5)
        self._spool_cancel.clear()

        def _run():
            # Set direction at start
            for m in self.motors:
                m.set_direction(direction)
            step_time = 0.02  # 50 Hz
            steps = max(1, int(ramp_ms / (step_time * 1000)))
            for m in self.motors:
                start = m.get_duty()
                delta = target - start
                m._ramp = (start, delta)  # for debug
            for i in range(1, steps + 1):
                if self._spool_cancel.is_set():
                    return
                s = i / steps
                for m in self.motors:
                    start, delta = m._ramp
                    m.set_duty(start + delta * s)
                time.sleep(step_time)

        self._spool_thread = threading.Thread(target=_run, daemon=True)
        self._spool_thread.start()


def parse_command(payload: str):
    """Return a normalized command dict or None.
    Expected JSON examples:
      {"type":"all","action":"spool","direction":"forward","target":100,"ramp_ms":2000}
      {"type":"all","action":"stop"}
      {"type":"all","action":"set","direction":"reverse","speed":50}
    Fallback key names (non-JSON): 'up' -> forward spool, 'down' -> reverse spool, 'space' -> stop
    """
    payload = payload.strip()
    try:
        obj = json.loads(payload)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # Fallback mapping from simple keys
    if payload.lower() in ("up", "w"):
        return {"type": "all", "action": "spool", "direction": "forward", "target": 100, "ramp_ms": DEFAULT_RAMP_MS}
    if payload.lower() in ("down", "s", "x"):
        return {"type": "all", "action": "spool", "direction": "reverse", "target": 100, "ramp_ms": DEFAULT_RAMP_MS}
    if payload.lower() in ("space", "stop"):
        return {"type": "all", "action": "stop"}
    return None


def handle_command(ctrl: MotorController, cmd: dict, client: mqtt.Client):
    t = cmd.get("type", "all")
    action = cmd.get("action")
    if action == "stop":
        ctrl.stop_all()
        client.publish(RX_TOPIC, json.dumps({"status": "stopped"}))
        return

    if t == "all":
        if action == "spool":
            direction = cmd.get("direction", "forward")
            target = float(cmd.get("target", 100))
            ramp_ms = int(cmd.get("ramp_ms", DEFAULT_RAMP_MS))
            ctrl.spool_all(direction, target, ramp_ms)
            client.publish(RX_TOPIC, json.dumps({"status": "spooling", "direction": direction, "target": target, "ramp_ms": ramp_ms}))
            return
        if action == "set":
            direction = cmd.get("direction", "forward")
            speed = float(cmd.get("speed", 0))
            ctrl.set_all(direction, speed)
            client.publish(RX_TOPIC, json.dumps({"status": "set", "direction": direction, "speed": speed}))
            return

    # TODO: per-motor control if needed later


def main():
    parser = argparse.ArgumentParser(description="MQTT -> GPIO PWM motor controller")
    parser.add_argument("--broker", default=MQTT_BROKER_HOST, help="MQTT broker host")
    parser.add_argument("--freq", type=int, default=PWM_FREQUENCY_HZ, help="PWM frequency in Hz")
    parser.add_argument("--ramp_ms", type=int, default=DEFAULT_RAMP_MS, help="Default ramp time for spool commands")
    parser.add_argument("--loglevel", default="info", choices=["debug", "info", "warning", "error", "critical"], help="Logging level")
    args = parser.parse_args()

    log_level = getattr(logging, args.loglevel.upper())
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    ctrl = MotorController(ENABLE_PINS, MOTOR_PAIRS, args.freq)

    client = mqtt.Client()

    def on_connect(cli, _userdata, _flags, rc):
        if rc == 0:
            logging.info("Connected to MQTT broker at %s", args.broker)
            cli.subscribe(TX_TOPIC)
            logging.info("Subscribed to %s", TX_TOPIC)
        else:
            logging.error("Failed to connect to MQTT broker rc=%s", rc)

    def on_message(cli, _userdata, msg):
        payload = msg.payload.decode("utf-8", errors="ignore")
        logging.info("RX %s: %s", msg.topic, payload)
        cmd = parse_command(payload)
        if not cmd:
            logging.warning("Unrecognized command payload; ignoring")
            return
        try:
            handle_command(ctrl, cmd, cli)
        except Exception as e:
            logging.exception("Error handling command: %s", e)

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.broker, 1883, 60)
    except Exception as e:
        logging.error("Could not connect to MQTT broker: %s", e)
        ctrl.cleanup()
        return

    client.loop_start()
    logging.info("Motor controller running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        logging.info("Shutting down")
    finally:
        client.loop_stop()
        client.disconnect()
        ctrl.cleanup()


if __name__ == "__main__":
    main()
