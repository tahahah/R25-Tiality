import sys
import os
import threading
import argparse
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
original_cwd = os.getcwd()
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from video import pi_video_manager_worker, frame_generator_picamera2
from audio import pi_audio_manager_worker, audio_packet_generator


def main():
    parser = argparse.ArgumentParser(description="Pi Tiality Manager")
    parser.add_argument("--video_server", type=str, default="localhost:50051", 
                       help="Address of the video server (default: localhost:50051)")
    parser.add_argument("--audio_server", type=str, default="localhost:50052",
                       help="Address of the audio server (default: localhost:50052)")
    parser.add_argument("--enable_audio", action='store_true',
                       help="Enable audio streaming")
    args = parser.parse_args()

    # Start video manager worker
    video_thread = threading.Thread(
        target=pi_video_manager_worker,
        args=(args.video_server, frame_generator_picamera2),
        daemon=True
    )
    video_thread.start()
    
    # Start audio manager worker if enabled
    if args.enable_audio:
        audio_thread = threading.Thread(
            target=pi_audio_manager_worker,
            args=(args.audio_server, audio_packet_generator),
            daemon=True
        )
        audio_thread.start()
        print("Audio streaming enabled")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")


if __name__ == "__main__":
    main()