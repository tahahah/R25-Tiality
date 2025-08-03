import logging
import sys

import cv2
import grpc
import numpy as np

# Add the 'app' directory to the Python path to find the generated gRPC files
sys.path.append("app")
import video_stream_pb2 as pb2
import video_stream_pb2_grpc as pb2g

# --- Configuration ---
# IMPORTANT: Change this to the IP address of your Raspberry Pi
PI_IP_ADDRESS = "192.168.0.151"  # Replace with your Pi's actual IP
GRPC_PORT = 50051

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def run():
    """Connects to the gRPC server and displays the video stream."""
    channel_address = f"{PI_IP_ADDRESS}:{GRPC_PORT}"
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


if __name__ == "__main__":
    run()
