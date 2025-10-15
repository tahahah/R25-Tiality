"""
Multiprocessing version of vision_worker - bypasses Python GIL for true parallelism.
This should be significantly faster than the threaded version for ML inference.
"""

import multiprocessing as mp
import queue
import time
import numpy as np
import cv2
from .detector_rfdetr import Detector


def _convert_opencv_to_pygame_bytes(opencv_img: np.ndarray) -> tuple:
    """
    Convert OpenCV image (BGR format) to bytes that can be sent across process boundary.
    Returns (bytes, shape, dtype) tuple that can be reconstructed into pygame surface.
    """
    try:
        # Resize
        resized_img = cv2.resize(opencv_img, (510, 230), interpolation=cv2.INTER_AREA)
        # Convert BGR to RGB (pygame expects RGB)
        rgb_img = cv2.cvtColor(resized_img, cv2.COLOR_BGR2RGB)
        # Return as bytes with metadata
        return (rgb_img.tobytes(), rgb_img.shape, rgb_img.dtype.str)
    except Exception as e:
        print(f"Error converting OpenCV image: {e}")
        return None


def _bytes_to_numpy(img_bytes: bytes, shape: tuple, dtype_str: str) -> np.ndarray:
    """Reconstruct numpy array from bytes."""
    dtype = np.dtype(dtype_str)
    return np.frombuffer(img_bytes, dtype=dtype).reshape(shape)


def vision_inference_process(
    inference_on: mp.Event,
    decoded_video_queue: mp.Queue,
    annotated_video_queue: mp.Queue,
    bounding_boxes_queue: mp.Queue,
    vision_inference_model_name: str,
    shutdown_event: mp.Event
):
    """
    Vision inference worker running in a separate PROCESS (not thread).
    This bypasses Python's GIL and enables true parallel execution.
    
    Args:
        inference_on (mp.Event): Flag to indicate if inference is on
        decoded_video_queue (mp.Queue): Queue from which to get the raw frames
        annotated_video_queue (mp.Queue): Queue to put the annotated video frames
        bounding_boxes_queue (mp.Queue): Queue to put the bounding boxes
        vision_inference_model_name (str): Name of the vision inference model
        shutdown_event (mp.Event): Event to signal process shutdown
    """
    print("[Vision Process] Starting...")
    
    # Initialize model and detector variables
    model_loaded = False
    vision_detector = None
    
    # Performance tracking
    frame_count = 0
    last_fps_time = time.time()
    
    # Constant loop until shutdown event is set
    while not shutdown_event.is_set():
        # Get the most recent decoded frame (skip old frames)
        decoded_frame = None
        frames_skipped = 0
        
        try:
            # Keep pulling frames until we get the most recent one
            while True:
                try:
                    decoded_frame = decoded_video_queue.get_nowait()
                    frames_skipped += 1
                except queue.Empty:
                    break
        except Exception as e:
            print(f"[Vision Process] Error getting frame: {e}")
            pass
        
        # If no frame available, sleep briefly and continue
        if decoded_frame is None:
            time.sleep(0.001)  # Small sleep to avoid CPU spinning
            continue
        
        if frames_skipped > 1:
            print(f"[Vision Process] Skipped {frames_skipped - 1} old frames")
        
        # If inference is on, run inference and get annotated frame and bounding boxes
        annotated_frame = None
        if inference_on.is_set():
            # Load model if not already loaded
            if not model_loaded:
                print("[Vision Process] Loading RF-DETR model...")
                model_loaded = True
                vision_detector = Detector(vision_inference_model_name)
                print("[Vision Process] Model loaded successfully")
            
            # Run inference and get annotated frame and bounding boxes
            inference_start = time.time()
            bboxes, annotated_frame = vision_detector.detect_single_image(decoded_frame)
            inference_time = time.time() - inference_start
            print(annotated_frame.shape)
            
            frame_count += 1
            
            # Log FPS every 30 frames
            if frame_count % 30 == 0:
                current_time = time.time()
                elapsed = current_time - last_fps_time
                fps = 30 / elapsed
                print(f"[Vision Process] Inference FPS: {fps:.1f}, Last inference: {inference_time*1000:.1f}ms")
                last_fps_time = current_time
            
            # Use a "dumping" pattern on the queue to ensure it only holds
            # the single most recent bounding box.
            try:
                # Clear any old list of bounding boxes that the GUI hasn't processed yet.
                bounding_boxes_queue.get_nowait()
            except queue.Empty:
                # The queue was already empty, which is fine.
                pass
            
            # Put the new, most recent bounding boxes into the bounding boxes queue.
            try:
                bounding_boxes_queue.put_nowait(bboxes)
            except queue.Full:
                print("[Vision Process] Bounding boxes queue full")
        
        # Convert frame to bytes for inter-process communication
        if annotated_frame is not None:
            frame_data = _convert_opencv_to_pygame_bytes(annotated_frame)
        else:
            frame_data = _convert_opencv_to_pygame_bytes(decoded_frame)
        
        if frame_data is None:
            continue
        
        # Use a "dumping" pattern on the queue to ensure it only holds
        # the single most recent annotated frame.
        try:
            # Clear any old frame that the GUI hasn't processed yet.
            annotated_video_queue.get_nowait()
        except queue.Empty:
            # The queue was already empty, which is fine.
            pass
        
        # Put the new, most recent annotated frame into the queue.
        try:
            annotated_video_queue.put_nowait(frame_data)
        except queue.Full:
            print("[Vision Process] Annotated video queue full")
    
    print("[Vision Process] Shutting down...")
    vision_detector = None


def start_vision_process(
    inference_on: mp.Event,
    decoded_video_queue: mp.Queue,
    annotated_video_queue: mp.Queue,
    bounding_boxes_queue: mp.Queue,
    vision_inference_model_name: str,
    shutdown_event: mp.Event
) -> mp.Process:
    """
    Helper function to start the vision inference process.
    
    Returns:
        mp.Process: The started process object
    """
    process = mp.Process(
        target=vision_inference_process,
        args=(
            inference_on,
            decoded_video_queue,
            annotated_video_queue,
            bounding_boxes_queue,
            vision_inference_model_name,
            shutdown_event
        ),
        daemon=True  # Process will terminate when main process exits
    )
    process.start()
    return process

