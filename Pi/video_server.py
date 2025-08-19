import logging
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import grpc

import video_stream_pb2 as pb2
import video_stream_pb2_grpc as pb2g

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class VideoStreamer(pb2g.VideoStreamServicer):
    """Provides a gRPC service to stream video frames from a camera."""

    def __init__(self):
        # TODO: Add any necessary initialization here.
        pass

    def StreamFrames(self, request, context):
        """Reads frames from the camera, encodes them as JPEG, and streams them."""
        logging.info("Client connected, starting video stream.")

        # Use a fixed device index 0 (/dev/video0) as requested.
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logging.error("Could not open video device /dev/video0.")
            context.abort(grpc.StatusCode.NOT_FOUND, "Camera not found.")
            return
        logging.info("Successfully opened camera /dev/video0.")

        try:
            while context.is_active():
                ret, frame = cap.read()
                if not ret:
                    logging.warning("Failed to grab frame, stopping stream.")
                    break

                # Encode the frame as JPEG
                ret, buffer = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                )
                if not ret:
                    logging.warning("Failed to encode frame.")
                    continue

                yield pb2.Frame(
                    jpeg_data=buffer.tobytes(),
                    timestamp_ms=int(time.time() * 1000),
                )
        except Exception as e:
            logging.error(f"An error occurred during streaming: {e}")
        finally:
            cap.release()
            logging.info("Client disconnected, released camera.")

def serve():
    """Starts the gRPC server and waits for connections."""
    server = grpc.server(ThreadPoolExecutor(max_workers=10))
    pb2g.add_VideoStreamServicer_to_server(VideoStreamer(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    logging.info("gRPC video server started on port 50051.")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logging.info("Server shutting down.")
        server.stop(0)


if __name__ == "__main__":
    serve()
