import os
import sys
import threading
import queue
import pygame
import cv2
import numpy as np
import logging
from .detector import Detector
from .vision_worker import run_vision_worker

# Get the parent directory path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

# Now you can import modules from the parent directory
from tiality_server import TialityServerManager

class InferenceManager:
    def __init__(self, vision_inference_config: dict, audio_inference_config: dict, server_manager: TialityServerManager):
        # Initialize Server Manager FIRST
        self.server_manager = server_manager
        
        # Initialize shutdown event EARLY
        self.shutdown_event = threading.Event()
        self.shutdown_event.clear()
        
        # Vision Inference Variables
        self.vision_inference_available: bool = vision_inference_config.VISION_INFERENCE_AVAILABLE
        self.vision_inference_on: threading.Event = threading.Event()
        self.vision_inference_on.clear()
        self.vision_inference_model_name: str = vision_inference_config.VISION_MODEL_NAME
        self.previous_bounding_boxes: list = []
        self.annotated_video_queue: queue.Queue = queue.Queue(maxsize=1)
        self.bounding_boxes_queue: queue.Queue = queue.Queue(maxsize=1)

        # Audio Inference Variables
        self.audio_inference_available: bool = audio_inference_config.AUDIO_INFERENCE_AVAILABLE
        self.audio_inference_on: threading.Event = threading.Event()
        self.audio_inference_on.clear()
        self.audio_inference_model_name: str = audio_inference_config.AUDIO_MODEL_NAME

        # Initialize thread references
        self.vision_thread = None
        self.audio_thread = None

        # Initialize Vision and Audio Detectors
        if self.vision_inference_available:
            self.vision_thread = threading.Thread(
                target=run_vision_worker, 
                args=(
                    self.vision_inference_on, 
                    self.server_manager.decoded_video_queue, 
                    self.annotated_video_queue, 
                    self.bounding_boxes_queue, 
                    self.vision_inference_model_name, 
                    self.shutdown_event
                )
            )
            self.vision_thread.start()
        if self.audio_inference_available:
            pass

    def shutdown_inference_manager(self):
        self.shutdown_event.set()
        if self.vision_thread is not None and self.vision_thread.is_alive():
            self.vision_thread.join()
        if self.audio_thread is not None and self.audio_thread.is_alive():
            self.audio_thread.join()

    def get_vision_inference_frame(self):
        """
        Get the raw frame from the server manager and process it through the vision detector if enabled to return to GUI

        Returns:
            pygame.Surface or None: The frame surface to display
        """
        if self.server_manager.servers_active and self.vision_thread is not None and self.vision_thread.is_alive():
            try:
                annotated_frame = self.annotated_video_queue.get_nowait()
                return annotated_frame
            except queue.Empty:
                return None
        elif self.server_manager.servers_active:
            # Vision thread not running, get raw frame from server
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

    def toggle_audio_inference_on(self):
       if self.audio_inference_on.is_set():
            self.audio_inference_on.clear()
       else:
            self.audio_inference_on.set()