import sys
import os
import queue
import threading
import argparse
import time
# from command import pi_command_manager_worker
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import tiality_server
original_cwd = os.getcwd()
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from video import pi_video_manager_worker, capture_frame_as_bytes, frame_generator_picamera2


def main():
    parser = argparse.ArgumentParser(description="Pi Tiality Manager")
    parser.add_argument("--broker", type=str, default="localhost:50051", help="Address of the video manager broker (default: localhost:50051)")
    args = parser.parse_args()

    # # Setup threadsafe queue and setup command subscriber
    # commands_queue = queue.Queue(maxsize = 1)
    # broker_ip = "localhost"
    # broker_port = 1883
    # topic = "robot/tx"
    # connection_established_event = threading.Event()
    
    # command_thread = threading.Thread(
    #     target=pi_command_manager_worker,
    #     args=(broker_ip, broker_port, PWM_frequency_hz, ramp_ms, log_level)
    # )
    # command_thread.start()

    

    # Setup thread safe queues, vars  and start gRPC client---
    video_thread = threading.Thread(
        target=pi_video_manager_worker, 
        args=(args.server_addr, frame_generator_picamera2),
        daemon=True  # A daemon thread will exit when the main program exits.
    )
    video_thread.start()
    time.sleep(60)

if __name__ == "__main__":
    main()