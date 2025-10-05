import cv2
import os
import numpy as np
import sys
import threading
import queue
import time
from copy import deepcopy
from ultralytics import YOLO
from ultralytics.utils import ops
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple, List

@dataclass
class ProcessedFrame:
    """Container for processed frame data"""
    image: np.ndarray
    bboxes: List
    timestamp: float
    frame_id: int

class OptimizedDetector:
    def __init__(self, model_path: str, 
                 skip_frames: int = 2,
                 inference_size: Tuple[int, int] = (640, 360),
                 conf_threshold: float = 0.5,
                 use_half_precision: bool = False):
        """
        Optimized YOLO detector with async processing
        
        Args:
            model_path: Path to YOLO model
            skip_frames: Process every Nth frame (0 = process all)
            inference_size: Size to resize frames for inference
            conf_threshold: Confidence threshold for detections
            use_half_precision: Use FP16 for faster inference (GPU only)
        """
        # Load model
        self.model = YOLO(model_path)
        
        # Try to optimize model for inference
        if use_half_precision and cv2.cuda.getCudaEnabledDeviceCount() > 0:
            self.model.to('cuda')
            self.model.model.half()  # FP16 inference
        
        # Configuration
        self.skip_frames = skip_frames
        self.inference_size = inference_size
        self.conf_threshold = conf_threshold
        
        # Threading components
        self.inference_queue = queue.Queue(maxsize=2)  # Small queue to avoid lag
        self.results_queue = queue.Queue(maxsize=5)
        self.latest_result = None
        self.result_lock = threading.Lock()
        
        # Frame counting for skip logic
        self.frame_counter = 0
        self.inference_thread = None
        self.running = False
        
        # Performance tracking
        self.fps_tracker = deque(maxlen=30)
        self.last_inference_time = 0
        
        # Colors for visualization
        self.class_colour = {
            'cockatoo': (0, 165, 255),
            'croc': (0, 255, 255),
            'frog': (0, 255, 0),
            'kang': (0, 0, 255),
            'koala': (255, 0, 0),
            'platty': (255, 255, 0),
            'tas': (255, 165, 0),
            'wombat': (255, 0, 255)
        }
    
    def start(self):
        """Start the inference thread"""
        if not self.running:
            self.running = True
            self.inference_thread = threading.Thread(target=self._inference_worker, daemon=True)
            self.inference_thread.start()
    
    def stop(self):
        """Stop the inference thread"""
        self.running = False
        if self.inference_thread:
            self.inference_thread.join(timeout=2.0)
    
    def _inference_worker(self):
        """Worker thread for running inference"""
        while self.running:
            try:
                # Get frame from queue with timeout
                frame_data = self.inference_queue.get(timeout=0.1)
                if frame_data is None:
                    continue
                
                frame, frame_id = frame_data
                
                # Run inference
                start_time = time.time()
                bboxes = self._get_bounding_boxes(frame)
                inference_time = time.time() - start_time
                
                # Create processed frame
                result = ProcessedFrame(
                    image=frame,
                    bboxes=bboxes,
                    timestamp=time.time(),
                    frame_id=frame_id
                )
                
                # Update latest result (non-blocking)
                with self.result_lock:
                    self.latest_result = result
                    self.last_inference_time = inference_time
                
                # Try to add to results queue (drop if full)
                try:
                    self.results_queue.put_nowait(result)
                except queue.Full:
                    pass
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Inference worker error: {e}")
    
    def process_frame_async(self, frame: np.ndarray) -> Optional[Tuple[List, np.ndarray]]:
        """
        Process a frame asynchronously
        
        Args:
            frame: Input frame
            
        Returns:
            Tuple of (bboxes, annotated_frame) if available, else None
        """
        self.frame_counter += 1
        
        # Check if we should process this frame
        should_process = (self.skip_frames == 0 or 
                         self.frame_counter % (self.skip_frames + 1) == 0)
        
        if should_process:
            # Resize frame for inference
            inference_frame = cv2.resize(frame, self.inference_size, 
                                        interpolation=cv2.INTER_LINEAR)
            
            # Try to add to queue (non-blocking)
            try:
                self.inference_queue.put_nowait((inference_frame, self.frame_counter))
            except queue.Full:
                # Drop frame if queue is full
                pass
        
        # Get latest result if available
        with self.result_lock:
            if self.latest_result:
                # Draw on current frame using latest detections
                annotated = self._draw_detections(frame, self.latest_result.bboxes, 
                                                 self.inference_size)
                
                # Add performance overlay
                if self.last_inference_time > 0:
                    fps = 1.0 / self.last_inference_time if self.last_inference_time > 0 else 0
                    cv2.putText(annotated, f"Inference FPS: {fps:.1f}", 
                              (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                              0.7, (0, 255, 0), 2)
                
                return self.latest_result.bboxes, annotated
        
        return None, frame
    
    def detect_single_image(self, img: np.ndarray) -> Tuple[List, np.ndarray]:
        """
        Synchronous detection for compatibility
        
        Args:
            img: Input image
            
        Returns:
            Tuple of (bboxes, annotated_image)
        """
        # Resize for inference
        inference_img = cv2.resize(img, self.inference_size, 
                                  interpolation=cv2.INTER_LINEAR)
        
        # Get bounding boxes
        bboxes = self._get_bounding_boxes(inference_img)
        
        # Draw detections
        img_out = self._draw_detections(img, bboxes, self.inference_size)
        
        return bboxes, img_out
    
    def _get_bounding_boxes(self, cv_img: np.ndarray) -> List:
        """
        Get bounding boxes from YOLO model
        """
        try:
            # Run prediction with optimized settings
            predictions = self.model.predict(
                cv_img, 
                imgsz=self.inference_size[0],  # Use consistent size
                conf=self.conf_threshold,
                verbose=False,
                device='cuda' if cv2.cuda.getCudaEnabledDeviceCount() > 0 else 'cpu'
            )
            
            bounding_boxes = []
            for prediction in predictions:
                boxes = prediction.boxes
                if boxes is None:
                    continue
                    
                for box in boxes:
                    if box.conf >= self.conf_threshold:
                        # Get box coordinates
                        box_cord = box.xywh[0]
                        box_label = box.cls
                        
                        bounding_boxes.append([
                            prediction.names[int(box_label)],
                            np.asarray(box_cord),
                            float(box.conf)
                        ])
            
            return bounding_boxes
            
        except Exception as e:
            print(f"Error in detection: {e}")
            return []
    
    def _draw_detections(self, img: np.ndarray, bboxes: List, 
                        inference_size: Tuple[int, int]) -> np.ndarray:
        """
        Draw bounding boxes on image with scaling
        """
        img_out = img.copy()
        
        if not bboxes:
            return img_out
        
        # Calculate scaling factors
        scale_x = img.shape[1] / inference_size[0]
        scale_y = img.shape[0] / inference_size[1]
        
        for bbox in bboxes:
            label = bbox[0]
            coords = bbox[1]
            confidence = bbox[2] if len(bbox) > 2 else None
            
            # Scale coordinates back to original image size
            scaled_coords = coords.copy()
            scaled_coords[0] *= scale_x  # x
            scaled_coords[1] *= scale_y  # y
            scaled_coords[2] *= scale_x  # width
            scaled_coords[3] *= scale_y  # height
            
            # Convert to xyxy format
            xyxy = ops.xywh2xyxy(scaled_coords)
            x1 = int(xyxy[0])
            y1 = int(xyxy[1])
            x2 = int(xyxy[2])
            y2 = int(xyxy[3])
            
            # Draw bounding box
            color = self.class_colour.get(label, (255, 255, 255))
            cv2.rectangle(img_out, (x1, y1), (x2, y2), color, thickness=2)
            
            # Draw label with background
            label_text = f"{label}: {confidence:.2f}" if confidence else label
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2
            
            # Get text size for background
            (text_width, text_height), baseline = cv2.getTextSize(
                label_text, font, font_scale, thickness
            )
            
            # Draw background rectangle
            cv2.rectangle(img_out, 
                         (x1, y1 - text_height - 5),
                         (x1 + text_width, y1),
                         color, -1)
            
            # Draw text
            cv2.putText(img_out, label_text, 
                       (x1, y1 - 5), font, font_scale,
                       (255, 255, 255), thickness)
        
        return img_out

# Backward compatible wrapper
class Detector(OptimizedDetector):
    """Wrapper for backward compatibility"""
    def __init__(self, model_path):
        super().__init__(
            model_path=model_path,
            skip_frames=2,  # Process every 3rd frame
            inference_size=(640, 360),  # Lower resolution for faster inference
            conf_threshold=0.5
        )
        # Auto-start for compatibility
        self.start()