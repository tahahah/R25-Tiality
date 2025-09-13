from picamera2 import Picamera2
import tiality_server
import queue
import cv2
import time
import threading
import grpc
import io

def pi_video_manager_worker(server_addr, frame_generator_func):
    """
    Initialize Picamera2 and continuously capture JPEG-encoded frames,
    keeping only the most recent frame in the provided queue.

    Robust to camera not being initially available or disconnecting: attempts
    to (re)initialize with exponential backoff and restarts on repeated
    capture failures.
    """
    reconnect_delay_seconds = 0.5
    max_reconnect_delay_seconds = 5.0

    # Setup thread safe queues, vars  and start gRPC client---
    video_queue = queue.Queue(maxsize = 1)
    video_thread = threading.Thread(
        target=tiality_server.client.run_grpc_client, 
        args=(server_addr, video_queue, frame_generator_func),
        daemon=True  # A daemon thread will exit when the main program exits.
    )
    video_thread.start()

    while True:
        picam2 = None
        try:
            # Attempt camera initialization
            picam2 = Picamera2()
            config = picam2.create_preview_configuration(main={"format": "RGB888"})
            picam2.configure(config)
            picam2.start()

            # Reset backoff on successful start
            reconnect_delay_seconds = 0.5
            consecutive_failures = 0

            # Capture loop
            while True:
                frame_bytes = capture_frame_as_bytes(picam2)
                if frame_bytes is None:
                    consecutive_failures += 1
                    # Short pause to avoid tight loop on failure
                    time.sleep(0.05)
                    # If too many consecutive failures, force a reconnect
                    if consecutive_failures >= 10:
                        raise RuntimeError("Repeated capture failures; restarting camera")
                    continue

                consecutive_failures = 0

                # Replace any existing frame with the newest one without blocking
                try:
                    # Drain existing items (keep queue at most 1 item)
                    while True:
                        try:
                            video_queue.get_nowait()
                        except queue.Empty:
                            break

                    # Try to enqueue the latest frame
                    try:
                        video_queue.put_nowait(frame_bytes)
                    except queue.Full:
                        # If a race filled the queue, drop oldest and retry once
                        try:
                            video_queue.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            video_queue.put_nowait(frame_bytes)
                        except queue.Full:
                            pass
                except Exception as e:
                    print(f"Video queue error: {e}")

        except Exception as e:
            # Log and attempt reconnect with backoff
            print(f"Video manager error (will retry): {e}")
            try:
                if picam2 is not None:
                    picam2.stop()
            except Exception:
                pass
            # Exponential backoff capped for Pi Zero 2 friendliness
            time.sleep(reconnect_delay_seconds)
            reconnect_delay_seconds = min(max_reconnect_delay_seconds, reconnect_delay_seconds * 2)
            continue
        finally:
            # Ensure camera is stopped before next reconnect attempt
            try:
                if picam2 is not None:
                    picam2.stop()
            except Exception:
                pass

def frame_generator_picamera2(frame_queue: queue.Queue):
    """
    A generator function that gets camera frame from a thread-safe queue as bytes and yields them as VideoFrame messages.
    """
    print("Frame generator started. Waiting for frames from the queue...")
    while True:
        # Block until a frame is available in the queue.
        frame_bytes = frame_queue.get()
        
        # If a sentinel value (e.g., None) is received, stop the generator.
        if frame_bytes is None:
            print("Stopping frame generator.")
            break

        try:
            # Yield the frame data in the format expected by the .proto file.
            yield tiality_server.video_streaming_pb2.VideoFrame(frame_data=frame_bytes)

        except Exception as e:
            print(f"Error encoding frame: {e}")


def capture_frame_as_bytes(picam2: Picamera2, quality: int = 75) -> bytes:
    """
    Captures a single frame from the Picamera2 object and encodes it as a JPEG.

    Args:
        picam2: The initialized and running Picamera2 instance.
        quality: The JPEG compression quality (0-100).

    Returns:
        A byte string containing the JPEG data.
    """
    try:
        # Capture the raw image data as a NumPy array (in RGB format).
        # This is the fastest way to get the frame data.
        frame_array = picam2.capture_array()
        
        # OpenCV expects BGR format, so we need to convert from RGB.
        frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)

        # Encode the BGR frame into a JPEG in memory.
        # This is much faster than saving to a file and reading it back.
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        success, encoded_image = cv2.imencode(".jpg", frame_bgr, encode_param)

        if not success:
            print("Failed to encode frame.")
            return None

        return encoded_image.tobytes()

    except Exception as e:
        print(f"Error capturing frame: {e}")
        return None