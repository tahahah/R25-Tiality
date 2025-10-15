import cv2
import os
import numpy as np
import supervision as sv
from PIL import Image
from rfdetr import RFDETRNano

# Custom fine-tuned model classes (Australian wildlife)
CUSTOM_CLASSES = [
    "animals", "Cockatoo", "Crocodile", "Frog", "Kangaroo", 
    "Koala", "Owl", "Platypus", "Snake", "Tassie Dev", "Wombat"
]


class Detector:
    def __init__(self, model_path):
        # If model_path is just a filename (no directory), resolve it relative to this file's directory
        if not os.path.isabs(model_path) and os.path.dirname(model_path) == '':
            current_dir = os.path.dirname(os.path.abspath(__file__))
            model_path = os.path.join(current_dir, model_path)

        print("[RF-DETR] Initializing model...")
        self.model = RFDETRNano(pretrain_weights=model_path)
        
        # Optimize for inference
        import torch
        self.device = self.model.model.device
        try:
            self.model.optimize_for_inference(compile=False, dtype=torch.float16)
            print("[RF-DETR] Model optimized (FP16)")
        except Exception as e:
            print(f"[RF-DETR] Optimization failed: {e}")
        
        self.inference_size = (640, 640)
        self.conf_threshold = 0.5
        
        # Supervision annotators
        self.color = sv.ColorPalette.from_hex([
            "#888888", "#ffffff", "#08780c", "#90ff00", "#f70e0e", "#bbeffe",
            "#ffa521", "#006df2", "#000000", "#FFFF00"
        ])

    def detect_single_image(self, img):
        """
        Detect targets in an image.
        Returns (bboxes_xywh, annotated_image) matching YOLO format
        """
        # Resize for inference
        inference_img = cv2.resize(img, self.inference_size, interpolation=cv2.INTER_LINEAR)
        
        # Convert BGR to RGB and to PIL Image
        img_rgb = cv2.cvtColor(inference_img, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)
        
        # Run inference
        detections = self.model.predict(pil_image, threshold=self.conf_threshold)
        
        # Scale detections back to original frame size
        detections = self._scale_detections(detections, img.shape, self.inference_size)
        
        # Convert xyxy to xywh format (center_x, center_y, width, height) to match YOLO
        bboxes_xywh = self._xyxy_to_xywh(detections.xyxy) if len(detections.xyxy) > 0 else np.empty((0, 4))
        
        # Annotate frame
        annotated_img = self._annotate_frame(img, detections)
        
        return bboxes_xywh, annotated_img

    def _xyxy_to_xywh(self, xyxy):
        """Convert xyxy format to xywh (center_x, center_y, width, height)"""
        xywh = np.zeros_like(xyxy)
        xywh[:, 0] = (xyxy[:, 0] + xyxy[:, 2]) / 2  # center_x
        xywh[:, 1] = (xyxy[:, 1] + xyxy[:, 3]) / 2  # center_y
        xywh[:, 2] = xyxy[:, 2] - xyxy[:, 0]        # width
        xywh[:, 3] = xyxy[:, 3] - xyxy[:, 1]        # height
        return xywh

    def _scale_detections(self, detections, target_shape, inference_size):
        """Scale detection coordinates from inference size to target size"""
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

    def _annotate_frame(self, frame, detections):
        """Annotate frame with detections"""
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
            for class_id, confidence in zip(detections.class_id, detections.confidence)
        ]
        
        # Annotate
        annotated_rgb = bbox_annotator.annotate(annotated_rgb, detections)
        annotated_rgb = label_annotator.annotate(annotated_rgb, detections, labels)
        
        # Convert back to BGR
        return cv2.cvtColor(annotated_rgb, cv2.COLOR_RGB2BGR)


