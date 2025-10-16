import threading
import queue
import time
import pygame
import numpy as np
import cv2
from .detector_rfdetr import Detector

def _convert_opencv_to_pygame_surface(opencv_img: np.ndarray) -> pygame.Surface:
        """Convert an OpenCV image (BGR format) to a pygame surface for display."""
        try:
            # Resize
            resized_img = cv2.resize(opencv_img, (510, 230), interpolation=cv2.INTER_AREA)
            # Convert BGR to RGB (pygame expects RGB)
            rgb_img = cv2.cvtColor(resized_img, cv2.COLOR_BGR2RGB)
            # Swap axes to get (width, height, channels) format for pygame
            rgb_img = rgb_img.swapaxes(0, 1)
            # Create pygame surface from the RGB array
            surface = pygame.surfarray.make_surface(rgb_img)
            return surface
        except Exception as e:
            print(f"Error converting OpenCV image to pygame surface: {e}")
            return None

def run_vision_worker(inference_on: threading.Event, decoded_video_queue: queue.Queue, annotated_video_queue: queue.Queue, bounding_boxes_queue: queue.Queue, vision_inference_model_name: str, shutdown_event: threading.Event):
    """

    This worker is designed to run on a seperate thread.
    Vision Worker that will run inference on the decoded video queue and put the annotated video and bounding boxes into the annotated video and bounding boxes queues

    Args:
        inference_on (threading.Event): Flag to indicate if inference is on
        decoded_video_queue (queue.Queue): Queue from which to get the raw, decoded frames
        annotated_video_queue (queue.Queue): Queue to put the annotated video frames into
        bounding_boxes_queue (queue.Queue): Queue to put the bounding boxes into
        vision_inference_model_name (str): Name of the vision inference model
    """
    print("Vision worker starting...")
    # Initialize model and detector variables
    model_loaded = False
    vision_detector = None
    
    # Constant loop until shutdown event is set
    while not shutdown_event.is_set():
        # Get the most recent decoded frame (skip old frames if multiple are queued)
        decoded_frame = None
        try:
            # Keep pulling frames until we get the most recent one
            while True:
                try:
                    decoded_frame = decoded_video_queue.get_nowait()
                except queue.Empty:
                    break
        except Exception:
            pass
        
        # If no frame available, sleep briefly and continue
        if decoded_frame is None:
            time.sleep(0.001)  # Small sleep to avoid CPU spinning
            continue

        # If inference is on, run inference and get annotated frame and bounding boxes
        annotated_frame = None
        if inference_on.is_set():
            # Load model if not already loaded
            if not model_loaded:
                model_loaded = True
                vision_detector = Detector(vision_inference_model_name)
            
            
            # Run inference and get annotated frame and bounding boxes
            bboxes, annotated_frame = vision_detector.detect_single_image(decoded_frame)


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
                # Queue is full, skip this frame
                pass
        
        if annotated_frame is not None:
            frame_surface = _convert_opencv_to_pygame_surface(annotated_frame)
        else:
            frame_surface = _convert_opencv_to_pygame_surface(decoded_frame)

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
            annotated_video_queue.put_nowait(frame_surface)
        except queue.Full:
            # Queue is full, skip this frame
            pass
            

    print("Vision worker ending...")

    # Set vision detector loaded to False
    vision_detector = None

