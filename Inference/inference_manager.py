import os
import sys
import threading
import queue
import multiprocessing as mp
import pygame
import cv2
import numpy as np
import logging
from .detector import Detector
from .vision_worker_multiprocess import start_vision_process
from .audio_worker import run_audio_worker
from .audio_classifier import AudioClassifier

# Get the parent directory path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

# Now you can import modules from the parent directory
from tiality_server import TialityServerManager

class InferenceManager:
    def __init__(self, vision_inference_config: dict, audio_inference_config: dict, server_manager: TialityServerManager):
        # Initialize Server Manager FIRST
        self.server_manager = server_manager
        
        # Initialize shutdown events EARLY
        # Use multiprocessing Event for vision worker (separate process)
        self.vision_shutdown_event = mp.Event()
        self.vision_shutdown_event.clear()
        # Use threading Event for audio worker (thread is fine for audio)
        self.audio_shutdown_event = threading.Event()
        self.audio_shutdown_event.clear()
        
        # Vision Inference Variables (multiprocessing for performance)
        self.vision_inference_available: bool = vision_inference_config.VISION_INFERENCE_AVAILABLE
        self.vision_inference_on: mp.Event = mp.Event()  # Changed to mp.Event
        self.vision_inference_on.clear()
        self.vision_inference_model_name: str = vision_inference_config.VISION_MODEL_NAME
        self.previous_bounding_boxes: list = []
        self.annotated_video_queue: mp.Queue = mp.Queue(maxsize=1)  # Changed to mp.Queue
        self.bounding_boxes_queue: mp.Queue = mp.Queue(maxsize=1)  # Changed to mp.Queue

        # Audio Inference Variables
        self.audio_inference_available: bool = audio_inference_config.AUDIO_INFERENCE_AVAILABLE
        self.audio_inference_model_name: str = audio_inference_config.AUDIO_MODEL_NAME
        self.audio_trigger_queue: queue.Queue = queue.Queue(maxsize=5)
        self.audio_results_queue: queue.Queue = queue.Queue(maxsize=1)
        self.audio_classifier = None
        self.audio_receiver = None

        # Initialize worker references
        self.vision_process = None  # Changed to process
        self.audio_thread = None

        # Initialize Vision and Audio Workers
        if self.vision_inference_available:
            # Start vision inference as a separate PROCESS (bypasses GIL for better performance)
            self.vision_process = start_vision_process(
                inference_on=self.vision_inference_on,
                decoded_video_queue=self.server_manager.decoded_video_queue,
                annotated_video_queue=self.annotated_video_queue,
                bounding_boxes_queue=self.bounding_boxes_queue,
                vision_inference_model_name=self.vision_inference_model_name,
                shutdown_event=self.vision_shutdown_event
            )
            logging.info("Vision worker started as separate process (multiprocessing)")
        if self.audio_inference_available:
            # Initialize audio classifier (load model immediately at startup)
            try:
                self.audio_classifier = AudioClassifier(lazy_load=False)
                logging.info("Audio classifier initialized with model loaded")
            except Exception as e:
                logging.error(f"Audio classifier init failed: {e}")
                self.audio_inference_available = False

    def shutdown_inference_manager(self):
        """Shutdown both vision process and audio thread."""
        # Shutdown vision process
        if self.vision_process is not None and self.vision_process.is_alive():
            logging.info("Shutting down vision process...")
            self.vision_shutdown_event.set()
            self.vision_process.join(timeout=5.0)  # Wait up to 5 seconds
            if self.vision_process.is_alive():
                logging.warning("Vision process didn't terminate, forcing...")
                self.vision_process.terminate()
                self.vision_process.join()
        
        # Shutdown audio thread
        if self.audio_thread is not None and self.audio_thread.is_alive():
            logging.info("Shutting down audio thread...")
            self.audio_shutdown_event.set()
            self.audio_thread.join(timeout=5.0)

    def _bytes_to_pygame_surface(self, frame_data):
        """Convert bytes from worker process to pygame surface."""
        if frame_data is None:
            return None
        
        try:
            img_bytes, shape, dtype_str = frame_data
            dtype = np.dtype(dtype_str)
            rgb_array = np.frombuffer(img_bytes, dtype=dtype).reshape(shape)
            
            # Swap axes for pygame (width, height, channels)
            rgb_array = rgb_array.swapaxes(0, 1)
            return pygame.surfarray.make_surface(rgb_array)
        except Exception as e:
            logging.error(f"Error converting bytes to pygame surface: {e}")
            return None
    
    def get_vision_inference_frame(self):
        """
        Get the raw frame from the server manager and process it through the vision detector if enabled to return to GUI

        Returns:
            pygame.Surface or None: The frame surface to display
        """
        if self.server_manager.servers_active and self.vision_process is not None and self.vision_process.is_alive():
            try:
                # Get frame data (bytes format from multiprocessing worker)
                frame_data = self.annotated_video_queue.get_nowait()
                # Convert bytes back to pygame surface
                return self._bytes_to_pygame_surface(frame_data)
            except queue.Empty:
                return None
        elif self.server_manager.servers_active:
            # Vision process not running, get raw frame from server
            return self.server_manager.get_video_frame()
        else:
            return None
            
    def _get_previous_bounding_boxes(self):
        try:
            self.previous_bounding_boxes = self.bounding_boxes_queue.get_nowait()
            return self.previous_bounding_boxes
        except queue.Empty:
            return self.previous_bounding_boxes

    def toggle_vision_inference(self):
        if self.vision_inference_on.is_set():
            self.vision_inference_on.clear()
        else:
            self.vision_inference_on.set()

    def request_audio_classification(self, duration: float = 5.0):
        """Request one-shot audio classification of the last N seconds."""
        if not self.audio_inference_available or self.audio_classifier is None:
            logging.warning("Audio inference not available")
            return
        
        try:
            # Put duration request in trigger queue (non-blocking)
            self.audio_trigger_queue.put_nowait(duration)
            logging.info(f"Audio classification requested: {duration}s")
        except queue.Full:
            logging.warning("Audio classification request queue full, skipping")
    
    def start_audio_worker(self, audio_receiver):
        """Start audio worker thread with audio receiver."""
        if not self.audio_inference_available or self.audio_classifier is None:
            logging.warning("Audio inference not available")
            return
        
        if self.audio_thread is not None and self.audio_thread.is_alive():
            logging.warning("Audio worker already running")
            return
        
        self.audio_receiver = audio_receiver
        self.audio_thread = threading.Thread(
            target=run_audio_worker,
            args=(
                self.audio_receiver,
                self.audio_trigger_queue,
                self.audio_results_queue,
                self.audio_classifier,
                self.audio_shutdown_event  # Use audio-specific shutdown event
            ),
            daemon=True
        )
        self.audio_thread.start()
        logging.info("Audio worker started (one-shot mode, threading)")
    
    def get_audio_result(self):
        """Get latest audio classification result if available."""
        try:
            return self.audio_results_queue.get_nowait()
        except queue.Empty:
            return None