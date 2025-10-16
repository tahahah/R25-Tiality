import cv2
import os
import sys
import asyncio
import tempfile
import torch

# Add model directory to path before importing
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(REPO_ROOT, "model")
if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

# Direct import from model directory
from gemini_classify import classify_image


class GeminiDetector:
    def __init__(self, model_path):
        # Gemini-based classifier does not require a YOLO model; keep signature for parity
        self.class_colour = {
            'cockatoo': (0, 165, 255),
            'crocodile': (0, 255, 255),
            'frog': (0, 255, 0),
            'kangaroo': (0, 0, 255),
            'koala': (255, 0, 0),
            'platypus': (255, 255, 0),
            'tasmanian_devil': (255, 165, 0),
            'wombat': (255, 0, 255),
            'owl': (200, 200, 0),
            'snake': (0, 200, 200),
        }

    def detect_single_image(self, img):
        """
        function:
            detect target(s) in an image
        input:
            img: image, e.g., image read by the cv2.imread() function
        output:
            bboxes: tensor of shape (N, 4) in [cx, cy, w, h] for detected targets
            img_out: image with bounding boxes and class labels drawn on
            predicted_label: string with the predicted class name
        """
        height, width = img.shape[:2]

        # Persist the input image temporarily to pass a path to the Gemini classifier
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                tmp_path = tmp_file.name
            cv2.imwrite(tmp_path, img)

            # Run Gemini classification (async) synchronously here
            # Create a new event loop for this thread to avoid conflicts
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(classify_image(tmp_path))

            # Extract the predicted label from the structured response
            predicted_label = None
            if result is not None:
                try:
                    predicted_label = getattr(result, "animal").value
                except Exception:
                    try:
                        predicted_label = result["animal"]
                    except Exception:
                        predicted_label = None

            # Choose a color for annotation; default to white if label not recognized
            key = predicted_label if isinstance(predicted_label, str) else ""
            color = self.class_colour.get(key, (255, 255, 255))

            # Annotate the image: draw a single full-frame box and label
            annotated_img = img.copy()
            cv2.rectangle(annotated_img, (0, 0), (width - 1, height - 1), color, 2)
            if predicted_label:
                cv2.putText(
                    annotated_img,
                    predicted_label,
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    color,
                    2,
                    cv2.LINE_AA,
                )

            # Return a YOLO-like bbox tensor: [cx, cy, w, h] in pixels
            bboxes = torch.tensor([[width / 2.0, height / 2.0, float(width), float(height)]], dtype=torch.float32)
            # Store the predicted label as an attribute for the GUI to access
            self.last_predicted_label = predicted_label if predicted_label else "Unknown"
            return bboxes, annotated_img
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass