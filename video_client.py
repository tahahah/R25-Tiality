import logging
import sys
import argparse

import cv2
import grpc
import numpy as np

# Allow importing generated gRPC stubs no matter where they live
# Prefer Pi/ (current repo location); also support historical 'app/'
sys.path.extend(["Pi", "app"])
import video_stream_pb2 as pb2
import video_stream_pb2_grpc as pb2g

# --- Defaults ---
# You can override these via CLI flags: --pi_ip and --grpc_port
PI_IP_ADDRESS = "192.168.0.114"
GRPC_PORT = 50051

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def run(pi_ip: str, grpc_port: int):
    """Connects to the gRPC server and displays the video stream."""
    channel_address = f"{pi_ip}:{grpc_port}"
    logging.info(f"Attempting to connect to gRPC server at {channel_address}...")

    try:
        # Set a timeout for the connection attempt
        channel = grpc.insecure_channel(channel_address)
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        logging.error(
            f"Could not connect to the server at {channel_address}. "
            f"Please ensure the server is running on the Pi and the IP is correct."
        )
        return

    logging.info("Successfully connected to the gRPC server.")
    stub = pb2g.VideoStreamStub(channel)

    try:
        # Request the stream from the server
        stream = stub.StreamFrames(pb2.Empty())

        for frame_data in stream:
            # Decode the JPEG image
            frame = cv2.imdecode(
                np.frombuffer(frame_data.jpeg_data, dtype=np.uint8), cv2.IMREAD_COLOR
            )

            # Display the resulting frame
            cv2.imshow("Pi Camera Stream", frame)

            # Press 'q' on the keyboard to exit the stream
            if cv2.waitKey(1) & 0xFF == ord("q"):
                logging.info("'q' pressed, stopping client.")
                break

    except grpc.RpcError as e:
        logging.error(f"An RPC error occurred: {e.code()} - {e.details()}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    finally:
        cv2.destroyAllWindows()
        channel.close()
        logging.info("Connection closed and windows destroyed.")

def parse_args():
    parser = argparse.ArgumentParser(description="Simple gRPC video client")
    parser.add_argument("--pi_ip", default=PI_IP_ADDRESS, help="Raspberry Pi IP address hosting gRPC server")
    parser.add_argument("--grpc_port", type=int, default=GRPC_PORT, help="gRPC port")
    parser.add_argument("--loglevel", default="info", choices=["debug", "info", "warning", "error", "critical"], help="Logging level")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    log_level = getattr(logging, args.loglevel.upper())
    logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")
    run(args.pi_ip, args.grpc_port)
