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
    parser.add_argument("--video_server", type=str, default="localhost:50051", help="Address of the video manager broker (default: localhost:50051)")
    args = parser.parse_args()

    # Start video manager worker function
    pi_video_manager_worker(args.video_server, frame_generator_picamera2)

    

if __name__ == "__main__":
    main()