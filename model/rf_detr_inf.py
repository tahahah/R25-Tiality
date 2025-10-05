import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np
import supervision as sv
from PIL import Image

from rfdetr import RFDETRNano

# Custom fine-tuned model classes (Australian wildlife)
# Order matches the COCO annotations from the training dataset
CUSTOM_CLASSES = [
    "animals",     # 0 - generic animal class
    "Cockatoo",    # 1
    "Crocodile",   # 2
    "Frog",        # 3
    "Kangaroo",    # 4
    "Koala",       # 5
    "Owl",         # 6
    "Platypus",    # 7
    "Snake",       # 8
    "Tassie Dev",  # 9
    "Wombat"       # 10
]


@dataclass
class ProcessedFrame:
    """Container for processed frame data."""
    image: np.ndarray
    detections: sv.Detections
    timestamp: float
    frame_id: int


class RFDETRDetector:
    """RF-DETR detector with asynchronous inference and frame skipping."""

    def __init__(
        self,
        model_path: str,
        skip_frames: int = 2,
        inference_size: Tuple[int, int] = (640, 640),  # Square size for optimal performance
        conf_threshold: float = 0.5,
    ) -> None:
        """
        Initialize RF-DETR detector.
        
        Args:
            model_path: Path to RF-DETR model weights
            skip_frames: Number of frames to skip between inferences
            inference_size: Target size for inference (width, height)
            conf_threshold: Confidence threshold for detections
        """
        print("Initializing RF-DETR model...")
        self.model = RFDETRNano(pretrain_weights=model_path)
        
        # RF-DETR automatically uses MPS/CUDA if available
        import torch
        self.device = self.model.model.device
        device_name = 'CPU'
        if 'mps' in str(self.device):
            device_name = 'Apple Silicon GPU (MPS)'
        elif 'cuda' in str(self.device):
            device_name = 'NVIDIA GPU (CUDA)'
        
        print(f"Device: {device_name}")
        
        # Optimize for inference - CRITICAL FOR SPEED
        # Use compile=False because TorchScript tracing fails on dynamic control flow
        # But this still gives 5x speedup through optimized inference path
        print("Optimizing model for inference...")
        try:
            self.model.optimize_for_inference(compile=False, dtype=torch.float16)
            print("✓ Model optimized (FP16, no-compile mode) - expect ~30ms inference")
        except Exception as e:
            print(f"Warning: Optimization failed: {e}")
            print("Falling back to unoptimized mode - expect slower inference")
        
        self.skip_frames = max(0, int(skip_frames))
        self.inference_size = inference_size
        self.conf_threshold = conf_threshold
        
        # Threading components
        self.inference_queue: queue.Queue[Optional[Tuple[np.ndarray, int]]] = queue.Queue(maxsize=2)
        self.results_queue: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=5)
        self.latest_result: Optional[ProcessedFrame] = None
        self.result_lock = threading.Lock()
        
        self.frame_counter = 0
        self.inference_thread: Optional[threading.Thread] = None
        self.running = False
        
        # FPS tracking
        self.fps_tracker: deque[float] = deque(maxlen=30)
        self.last_inference_time: float = 0.0
        
        # Supervision annotators with color palette for 10 wildlife classes
        # Order matches CUSTOM_CLASSES (from COCO annotations)
        self.color = sv.ColorPalette.from_hex([
            "#888888",  # 0: animals - Gray (generic class)
            "#ffffff",  # 1: Cockatoo - White
            "#08780c",  # 2: Crocodile - Green
            "#90ff00",  # 3: Frog - Yellow-Green
            "#f70e0e",  # 4: Kangaroo - Red
            "#bbeffe",  # 5: Koala - Light Blue
            "#ffa521",  # 6: Platypus - Orange
            "#006df2",  # 7: Snake - Blue
            "#000000",  # 8: Tassie Dev - Black
            "#FFFF00"   # 9: Wombat - Yellow
        ])

    def start(self) -> None:
        """Start the inference worker thread."""
        if self.running:
            return
        self.running = True
        self.inference_thread = threading.Thread(target=self._inference_worker, daemon=True)
        self.inference_thread.start()

    def stop(self) -> None:
        """Stop the inference worker thread."""
        self.running = False
        if self.inference_thread and self.inference_thread.is_alive():
            try:
                self.inference_queue.put_nowait(None)
            except queue.Full:
                pass
            self.inference_thread.join(timeout=2.0)

    def _inference_worker(self) -> None:
        """Worker thread for asynchronous inference."""
        while self.running:
            try:
                frame_data = self.inference_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                if frame_data is None:
                    continue

                frame, frame_id = frame_data
                start_time = time.time()
                
                # Convert BGR to RGB and to PIL Image
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                
                # Run inference
                detections = self.model.predict(pil_image, threshold=self.conf_threshold)
                inference_time = time.time() - start_time

                result = ProcessedFrame(
                    image=frame,
                    detections=detections,
                    timestamp=time.time(),
                    frame_id=frame_id,
                )

                fps_value = 1.0 / inference_time if inference_time > 0 else 0.0

                with self.result_lock:
                    self.latest_result = result
                    self.last_inference_time = inference_time
                    if fps_value > 0:
                        self.fps_tracker.append(fps_value)

                try:
                    self.results_queue.put_nowait(result)
                except queue.Full:
                    pass
            except Exception as exc:
                print(f"Inference worker error: {exc}")
            finally:
                self.inference_queue.task_done()

    def process_frame_async(self, frame: np.ndarray) -> Tuple[Optional[sv.Detections], np.ndarray]:
        """
        Process frame asynchronously with frame skipping.
        
        Args:
            frame: Input frame in BGR format
            
        Returns:
            Tuple of (detections, annotated_frame)
        """
        if not self.running:
            self.start()

        self.frame_counter += 1
        should_process = self.skip_frames == 0 or self.frame_counter % (self.skip_frames + 1) == 0

        if should_process:
            inference_frame = cv2.resize(frame, self.inference_size, interpolation=cv2.INTER_LINEAR)
            try:
                self.inference_queue.put_nowait((inference_frame, self.frame_counter))
            except queue.Full:
                pass

        with self.result_lock:
            if self.latest_result:
                annotated = self._annotate_frame(frame, self.latest_result.detections)
                fps = self._current_fps()
                if fps > 0:
                    cv2.putText(
                        annotated,
                        f"Inference FPS: {fps:.1f}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2,
                    )
                return self.latest_result.detections, annotated

        return None, frame

    def detect_single_image(self, img: np.ndarray) -> Tuple[sv.Detections, np.ndarray]:
        """
        Perform synchronous detection on a single image.
        
        Args:
            img: Input image in BGR format
            
        Returns:
            Tuple of (detections, annotated_image)
        """
        import time
        t0 = time.time()
        
        inference_img = cv2.resize(img, self.inference_size, interpolation=cv2.INTER_LINEAR)
        t1 = time.time()
        print(f"  ⏱ Resize: {(t1-t0)*1000:.1f}ms")
        
        # Convert BGR to RGB and to PIL Image
        img_rgb = cv2.cvtColor(inference_img, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)
        t2 = time.time()
        print(f"  ⏱ BGR→RGB→PIL: {(t2-t1)*1000:.1f}ms")
        
        # Run inference
        detections = self.model.predict(pil_image, threshold=self.conf_threshold)
        t3 = time.time()
        print(f"  ⏱ Model inference: {(t3-t2)*1000:.1f}ms ⚠️")
        
        # Scale detections back to original frame size
        detections = self._scale_detections(detections, img.shape, self.inference_size)
        t4 = time.time()
        print(f"  ⏱ Scale detections: {(t4-t3)*1000:.1f}ms")
        
        img_out = self._annotate_frame(img, detections)
        t5 = time.time()
        print(f"  ⏱ Annotate: {(t5-t4)*1000:.1f}ms")
        print(f"  ⏱ TOTAL: {(t5-t0)*1000:.1f}ms")
        
        return detections, img_out

    def _scale_detections(
        self, 
        detections: sv.Detections, 
        target_shape: Tuple[int, int, int],
        inference_size: Tuple[int, int]
    ) -> sv.Detections:
        """Scale detection coordinates from inference size to target size."""
        if detections.xyxy is None or len(detections.xyxy) == 0:
            return detections
        
        scale_x = target_shape[1] / float(inference_size[0])
        scale_y = target_shape[0] / float(inference_size[1])
        
        scaled_xyxy = detections.xyxy.copy()
        scaled_xyxy[:, [0, 2]] *= scale_x
        scaled_xyxy[:, [1, 3]] *= scale_y
        
        return sv.Detections(
            xyxy=scaled_xyxy,
            confidence=detections.confidence,
            class_id=detections.class_id,
        )

    def _annotate_frame(self, frame: np.ndarray, detections: sv.Detections) -> np.ndarray:
        """
        Annotate frame with detections using supervision utilities.
        
        Args:
            frame: Input frame in BGR format
            detections: Detection results
            
        Returns:
            Annotated frame
        """
        annotated = frame.copy()
        
        if detections.xyxy is None or len(detections.xyxy) == 0:
            return annotated
        
        # Convert to RGB for supervision
        annotated_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        
        # Calculate optimal parameters
        text_scale = sv.calculate_optimal_text_scale(resolution_wh=(frame.shape[1], frame.shape[0]))
        thickness = sv.calculate_optimal_line_thickness(resolution_wh=(frame.shape[1], frame.shape[0]))
        
        # Create annotators
        bbox_annotator = sv.BoxAnnotator(color=self.color, thickness=thickness)
        label_annotator = sv.LabelAnnotator(
            color=self.color,
            text_color=sv.Color.BLACK,
            text_scale=text_scale,
            smart_position=True
        )
        
        # Create labels
        labels = [
            f"{CUSTOM_CLASSES[class_id]} {confidence:.2f}"
            for class_id, confidence
            in zip(detections.class_id, detections.confidence)
        ]
        
        # Annotate
        annotated_rgb = bbox_annotator.annotate(annotated_rgb, detections)
        annotated_rgb = label_annotator.annotate(annotated_rgb, detections, labels)
        
        # Convert back to BGR
        return cv2.cvtColor(annotated_rgb, cv2.COLOR_RGB2BGR)

    def _current_fps(self) -> float:
        """Calculate current average FPS."""
        if not self.fps_tracker:
            return 0.0
        return sum(self.fps_tracker) / len(self.fps_tracker)

    def __del__(self) -> None:
        """Cleanup on deletion."""
        try:
            self.stop()
        except (AttributeError, Exception):
            # Handle case where initialization failed and attributes don't exist
            pass