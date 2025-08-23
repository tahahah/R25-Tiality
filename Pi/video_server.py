import logging
import argparse
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

    def __init__(self, device=0, width=None, height=None, fps=None):
        """
        device: int index (e.g. 0) or str path (e.g. '/dev/video1' or '/dev/v4l/by-path/...-video-index0')
        width/height/fps: optional capture properties
        """
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps

    def StreamFrames(self, request, context):
        """Reads frames from the camera, encodes them as JPEG, and streams them."""
        logging.info("Client connected, starting video stream.")

        # Open the configured device (int index or str path)
        cap = cv2.VideoCapture(self.device)
        if not cap.isOpened():
            logging.error("Could not open video device: %s", self.device)
            context.abort(grpc.StatusCode.NOT_FOUND, f"Camera not found: {self.device}")
            return
        logging.info("Successfully opened camera: %s", self.device)

        # Apply any requested capture properties
        try:
            if self.width is not None:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.width))
            if self.height is not None:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.height))
            if self.fps is not None:
                cap.set(cv2.CAP_PROP_FPS, float(self.fps))
        except Exception as e:
            logging.warning("Failed setting capture properties: %s", e)

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

def serve(port: int, streamer: VideoStreamer):
    """Starts the gRPC server and waits for connections."""
    server = grpc.server(ThreadPoolExecutor(max_workers=10))
    pb2g.add_VideoStreamServicer_to_server(streamer, server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logging.info("gRPC video server started on port %d.", port)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logging.info("Server shutting down.")
        server.stop(0)


def _parse_device(device_str: str):
    """Return int index if numeric, else the original string path."""
    try:
        # Accept plain integers like "0" or "1" as indices
        return int(device_str)
    except (ValueError, TypeError):
        return device_str


def main():
    parser = argparse.ArgumentParser(description="gRPC video server streaming from a V4L2 camera")
    parser.add_argument("--port", type=int, default=50051, help="gRPC listen port")
    parser.add_argument(
        "--device",
        default="0",
        help="Camera device index or path (e.g. 0, /dev/video1, or /dev/v4l/by-path/...-video-index0)",
    )
    parser.add_argument("--width", type=int, default=None, help="Capture width (optional)")
    parser.add_argument("--height", type=int, default=None, help="Capture height (optional)")
    parser.add_argument("--fps", type=float, default=None, help="Capture FPS (optional)")
    args = parser.parse_args()

    device = _parse_device(args.device)
    logging.info("Starting video server with device=%s width=%s height=%s fps=%s", device, args.width, args.height, args.fps)
    streamer = VideoStreamer(device=device, width=args.width, height=args.height, fps=args.fps)
    serve(args.port, streamer)


if __name__ == "__main__":
    main()
