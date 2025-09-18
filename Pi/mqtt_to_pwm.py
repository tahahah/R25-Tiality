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

# Motor compensation factors for omnidirectional wheels
# Adjust these values to make the robot move in a straight line
# Values < 1.0 reduce motor speed, > 1.0 increase motor speed
MOTOR_COMPENSATION = {
    "forward": [1.0, 0.85, 1.0, 0.85],  # [motor1, motor2, motor3, motor4]
    "reverse": [1.0, 0.85, 1.0, 0.85],  # Adjust these based on testing
}

# Wheel layout mapping and polarity for mecanum/omni drive
# Positions order: [FL, FR, RL, RR] -> maps to indices in self.motors
# Adjust MOTOR_ORDER if your wiring order does not match [front-left, front-right, rear-left, rear-right]
# Set MOTOR_POLARITY element to -1 to invert a wheel if its "forward" is electrically reversed
MOTOR_ORDER = [0, 1, 2, 3]
MOTOR_POLARITY = [1, 1, 1, 1]

MQTT_BROKER_HOST = "localhost"
TX_TOPIC = "robot/tx"

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
        # Apply compensation factors for each motor based on direction
        comp_factors = MOTOR_COMPENSATION.get(direction, [1.0, 1.0, 1.0, 1.0])
        
        for i, m in enumerate(self.motors):
            m.set_direction(direction)
            # Apply compensation factor to this specific motor
            comp_speed = speed * comp_factors[i]
            m.set_duty(comp_speed)

    def set_vector(self, vx: float, vy: float, omega: float = 0.0):
        """Mecanum mixing for true crab-walk (lateral) and forward motion.
        Inputs are percentages in range [-100..100].
          - vy: forward is positive
          - vx: right (lateral) is positive
          - omega: rotate clockwise is positive (optional; default 0)

        Standard mecanum formula (see referenced blog):
          FL = vy + vx + omega
          FR = vy - vx - omega
          RL = vy - vx + omega
          RR = vy + vx - omega

        Results are then mapped through MOTOR_ORDER and MOTOR_POLARITY to match wiring.
        """
        # Clamp inputs
        vx = max(-100.0, min(100.0, float(vx)))
        vy = max(-100.0, min(100.0, float(vy)))
        omega = max(-100.0, min(100.0, float(omega)))

        # Compute theoretical wheel commands in [FL, FR, RL, RR]
        wheel_cmds = [
            vy + vx + omega,  # FL
            vy - vx - omega,  # FR
            vy - vx + omega,  # RL
            vy + vx - omega,  # RR
        ]

        # Normalize to keep within [-100, 100]
        max_mag = max(abs(val) for val in wheel_cmds) or 1.0
        if max_mag > 100.0:
            scale = 100.0 / max_mag
            wheel_cmds = [val * scale for val in wheel_cmds]

        logging.debug(
            "Mecanum mix (vx=%.1f, vy=%.1f, w=%.1f) -> FL=%.1f FR=%.1f RL=%.1f RR=%.1f",
            vx, vy, omega, wheel_cmds[0], wheel_cmds[1], wheel_cmds[2], wheel_cmds[3]
        )

        # Apply mapping to physical motors and compensation/polarity
        for pos_idx, base_cmd in enumerate(wheel_cmds):
            motor_idx = MOTOR_ORDER[pos_idx]
            m = self.motors[motor_idx]
            cmd = base_cmd * (1 if MOTOR_POLARITY[pos_idx] >= 0 else -1)
            direction = "forward" if cmd >= 0 else "reverse"
            comp = MOTOR_COMPENSATION.get(direction, [1.0, 1.0, 1.0, 1.0])[motor_idx]
            m.set_direction(direction)
            m.set_duty(abs(cmd) * comp)

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
                
            # Apply compensation factors for each motor based on direction
            comp_factors = MOTOR_COMPENSATION.get(direction, [1.0, 1.0, 1.0, 1.0])
            comp_targets = [target * factor for factor in comp_factors]
            
            step_time = 0.02  # 50 Hz
            steps = max(1, int(ramp_ms / (step_time * 1000)))
            
            # Calculate ramp for each motor with its compensation factor
            for i, m in enumerate(self.motors):
                start = m.get_duty()
                delta = comp_targets[i] - start
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
      {"type":"vector","action":"set","vx":25,"vy":-40}
      {"type":"config","action":"set_compensation","direction":"forward","factors":[1.0, 0.8, 1.0, 0.8]}
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
    if payload.lower() in ("left", "a"):
        return {"type": "vector", "action": "set", "vx": -50, "vy": 0}
    if payload.lower() in ("right", "d"):
        return {"type": "vector", "action": "set", "vx": 50, "vy": 0}
    if payload.lower() in ("space", "stop"):
        return {"type": "all", "action": "stop"}
    return None


def handle_command(ctrl: MotorController, cmd: dict, client: mqtt.Client):
    t = cmd.get("type", "all")
    action = cmd.get("action")
    if action == "stop":
        ctrl.stop_all()
        return

    if t == "all":
        if action == "spool":
            direction = cmd.get("direction", "forward")
            target = float(cmd.get("target", 100))
            ramp_ms = int(cmd.get("ramp_ms", DEFAULT_RAMP_MS))
            ctrl.spool_all(direction, target, ramp_ms)
            return
        if action == "set":
            direction = cmd.get("direction", "forward")
            speed = float(cmd.get("speed", 0))
            ctrl.set_all(direction, speed)
            return
    elif t == "vector":
        if action == "set":
            vx = float(cmd.get("vx", 0))
            vy = float(cmd.get("vy", 0))
            omega = float(cmd.get("w", cmd.get("omega", 0)))
            ctrl.set_vector(vx, vy, omega)
            return
    
    elif t == "config":
        if action == "set_compensation":
            direction = cmd.get("direction")
            factors = cmd.get("factors")
            if direction and factors and isinstance(factors, list) and len(factors) == 4:
                # Update the compensation factors
                MOTOR_COMPENSATION[direction] = factors
                logging.info(f"Updated compensation factors for {direction}: {factors}")
                return
            else:
                logging.warning(f"Invalid compensation factors: {factors}")
                return

    # TODO: per-motor control if needed later


def main():
    parser = argparse.ArgumentParser(description="MQTT -> GPIO PWM motor controller")
    parser.add_argument("--broker", default=MQTT_BROKER_HOST, help="MQTT broker host")
    parser.add_argument("--broker_port", type=int, default=1883, help="MQTT broker TCP port (default: 1883)")
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
        client.connect(args.broker, args.broker_port, 60)
    except Exception as e:
        logging.error("Could not connect to MQTT broker: %s\n at: %s; at port: %s", e, str(args.broker), str(args.broker_port))
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