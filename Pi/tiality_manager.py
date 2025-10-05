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
from audio import pi_audio_manager_worker, packet_generator_alsa


def main():
    parser = argparse.ArgumentParser(description="Pi Tiality Manager")
    parser.add_argument("--video_server", type=str, default="localhost:50051", help="Address of the video manager broker (default: localhost:50051)")
    parser.add_argument("--audio_server", type=str, default=None, help="Address of the audio manager broker (default: derived from video_server)")
    args = parser.parse_args()

    # Derive audio server address from video server if not specified
    if args.audio_server is None:
        # Extract host from video_server and use port 50052
        gui_ip = args.video_server.split(':')[0]
        args.audio_server = f"{gui_ip}:50052"

    # Start audio thread
    audio_thread = threading.Thread(
        target=pi_audio_manager_worker,
        args=(args.audio_server, packet_generator_alsa, {"card": 3, "device": 0}),
        daemon=True
    )
    audio_thread.start()
    print(f"Audio thread started, streaming to {args.audio_server}")

    # Start video manager worker function
    pi_video_manager_worker(args.video_server, frame_generator_picamera2)

    

if __name__ == "__main__":
    main()