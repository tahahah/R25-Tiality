import cv2
import os
import queue
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.utils import ops

# Get the parent directory path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)
from tiality_server import TialityServerManager


@dataclass
class ProcessedFrame:
    """Container for processed frame data."""

    image: np.ndarray
    bboxes: List
    timestamp: float
    frame_id: int


class OptimizedDetector:
    """Optimized YOLO detector supporting asynchronous inference."""

    def __init__(
        self,
        model_path: str,
        skip_frames: int = 2,
        inference_size: Tuple[int, int] = (640, 360),
        conf_threshold: float = 0.5,
        use_half_precision: bool = False,
    ) -> None:
        self.model = YOLO(model_path)

        self.device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        self.model.to(self.device)

        if use_half_precision and self.device.startswith('cuda'):
            try:
                self.model.model.half()
            except AttributeError:
                pass

        self.skip_frames = max(0, int(skip_frames))
        self.inference_size = inference_size
        self.conf_threshold = conf_threshold

        self.inference_queue: queue.Queue[Optional[Tuple[np.ndarray, int]]] = queue.Queue(maxsize=2)
        self.results_queue: queue.Queue[ProcessedFrame] = queue.Queue(maxsize=5)
        self.latest_result: Optional[ProcessedFrame] = None
        self.result_lock = threading.Lock()

        self.frame_counter = 0
        self.inference_thread: Optional[threading.Thread] = None
        self.running = False

        self.fps_tracker: deque[float] = deque(maxlen=30)
        self.last_inference_time: float = 0.0

        self.class_colour = {
            'cockatoo': (0, 165, 255),
            'croc': (0, 255, 255),
            'frog': (0, 255, 0),
            'kang': (0, 0, 255),
            'koala': (255, 0, 0),
            'platty': (255, 255, 0),
            'tas': (255, 165, 0),
            'wombat': (255, 0, 255),
        }

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.inference_thread = threading.Thread(target=self._inference_worker, daemon=True)
        self.inference_thread.start()

    def stop(self) -> None:
        self.running = False
        if self.inference_thread and self.inference_thread.is_alive():
            try:
                self.inference_queue.put_nowait(None)
            except queue.Full:
                pass
            self.inference_thread.join(timeout=2.0)

    def _inference_worker(self) -> None:
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
                bboxes = self._get_bounding_boxes(frame)
                inference_time = time.time() - start_time

                result = ProcessedFrame(
                    image=frame,
                    bboxes=bboxes,
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

    def process_frame_async(self, frame: np.ndarray) -> Tuple[Optional[List], np.ndarray]:
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
                annotated = self._draw_detections(frame, self.latest_result.bboxes, self.inference_size)
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
                return self.latest_result.bboxes, annotated

        return None, frame

    def detect_single_image(self, img: np.ndarray) -> Tuple[List, np.ndarray]:
        inference_img = cv2.resize(img, self.inference_size, interpolation=cv2.INTER_LINEAR)
        bboxes = self._get_bounding_boxes(inference_img)
        img_out = self._draw_detections(img, bboxes, self.inference_size)
        return bboxes, img_out

    def _get_bounding_boxes(self, cv_img: np.ndarray) -> List:
        try:
            predictions = self.model.predict(
                cv_img,
                imgsz=max(self.inference_size),
                conf=self.conf_threshold,
                verbose=False,
                device=self.device,
            )
        except Exception as exc:
            print(f"Error in detection: {exc}")
            return []

        bounding_boxes: List = []
        for prediction in predictions:
            boxes = prediction.boxes
            if boxes is None:
                continue

            for box in boxes:
                conf = float(box.conf)
                if conf < self.conf_threshold:
                    continue

                coords = box.xywh[0].detach().cpu().numpy()
                label_idx = int(box.cls)
                label = prediction.names.get(label_idx, str(label_idx)) if isinstance(prediction.names, dict) else prediction.names[label_idx]

                bounding_boxes.append([
                    label,
                    coords,
                    conf,
                ])

        return bounding_boxes

    def _draw_detections(
        self,
        img: np.ndarray,
        bboxes: List,
        inference_size: Tuple[int, int],
    ) -> np.ndarray:
        img_out = img.copy()

        if not bboxes:
            return img_out

        scale_x = img.shape[1] / float(inference_size[0])
        scale_y = img.shape[0] / float(inference_size[1])

        for bbox in bboxes:
            label, coords, confidence = bbox[0], bbox[1], bbox[2] if len(bbox) > 2 else None
            scaled_coords = coords.copy()
            scaled_coords[0] *= scale_x
            scaled_coords[1] *= scale_y
            scaled_coords[2] *= scale_x
            scaled_coords[3] *= scale_y

            xyxy = ops.xywh2xyxy(scaled_coords)
            x1, y1, x2, y2 = map(int, xyxy)

            color = self.class_colour.get(label, (255, 255, 255))
            cv2.rectangle(img_out, (x1, y1), (x2, y2), color, thickness=2)

            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2
            label_text = f"{label}: {confidence:.2f}" if confidence is not None else label

            (text_width, text_height), baseline = cv2.getTextSize(label_text, font, font_scale, thickness)

            cv2.rectangle(
                img_out,
                (x1, y1 - text_height - 5),
                (x1 + text_width, y1),
                color,
                -1,
            )

            cv2.putText(
                img_out,
                label_text,
                (x1, y1 - 5),
                font,
                font_scale,
                (255, 255, 255),
                thickness,
            )

        return img_out

    def _current_fps(self) -> float:
        if not self.fps_tracker:
            return 0.0
        return sum(self.fps_tracker) / len(self.fps_tracker)

    def __del__(self) -> None:
        self.stop()


class Detector(OptimizedDetector):
    """Backward-compatible detector wrapper."""

    def __init__(self, model_path: str) -> None:
        super().__init__(
            model_path=model_path,
            skip_frames=2,
            inference_size=(640, 360),
            conf_threshold=0.5,
        )
        self.start()

def _decode_video_frame_opencv(frame_bytes: bytes) -> np.ndarray:
    """
    Decodes a byte array (JPEG) into an OpenCV image (numpy ndarray).
    This is a high-performance method for rendering with OpenCV.

    Args:
        frame_bytes: The raw byte string of a single JPEG image.

    Returns:
        An OpenCV image (numpy ndarray in BGR format), or None if decoding fails.
    """
    try:
        # 1. Convert the raw byte string to a 1D NumPy array.
        np_array = np.frombuffer(frame_bytes, np.uint8)
        
        # 2. Decode the NumPy array into an OpenCV image (BGR format).
        img_bgr = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        
        if img_bgr is None:
            raise ValueError("Failed to decode image from bytes.")

        # 3. Optionally resize for display (remove or adjust as needed)
        img_bgr = cv2.resize(img_bgr, (510, 230), interpolation=cv2.INTER_AREA)

        return img_bgr

    except Exception as e:
        print(f"Error decoding frame with OpenCV: {e}")
        return None

# FOR TESTING ONLY
if __name__ == '__main__':
    # get current script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))

    model_path = os.path.join(script_dir, 'Teds_Model.pt')
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")

    detector = Detector(model_path)
    # Setup Server and shared frame queue
    server_manager = TialityServerManager(
        grpc_port = 50051, 
        mqtt_port = 2883, 
        mqtt_broker_host_ip = "localhost",
        decode_video_func = _decode_video_frame_opencv,
        num_decode_video_workers = 1 # Don't change this for now
        )
    server_manager.start_servers()

    window_title = 'YOLO Detector'
    blank_display = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(blank_display, 'Waiting for video feed...', (20, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    last_display = blank_display.copy()

    try:
        while True:
            frame = server_manager.get_video_frame()
            if frame is None:
                cv2.imshow(window_title, last_display)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord('q')):
                    break
                continue

            bboxes, img_out = detector.detect_single_image(frame)
            last_display = img_out

            cv2.imshow(window_title, img_out)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord('q')):
                break
    finally:
        detector.stop()
        server_manager.close_servers()
        cv2.destroyAllWindows()