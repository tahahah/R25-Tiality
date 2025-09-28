import cv2
import os
import numpy as np
import sys
from copy import deepcopy
from ultralytics import YOLO
from ultralytics.utils import ops

# Get the parent directory path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)
from tiality_server import TialityServerManager

class Detector:
    def __init__(self, model_path):
        self.model = YOLO(model_path)
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

    def detect_single_image(self, img):
        """
        function:
            detect target(s) in an image
        input:
            img: image, e.g., image read by the cv2.imread() function
        output:
            bboxes: list of lists, box info [label,[x,y,width,height]] for all detected targets in image
            img_out: image with bounding boxes and class labels drawn on
        """
        bboxes = self._get_bounding_boxes(img)

        img_out = deepcopy(img)

        # draw bounding boxes on the image
        for bbox in bboxes:
            label = bbox[0]
            coords = bbox[1]
            confidence = bbox[2] if len(bbox) > 2 else None

            #  translate bounding box info back to the format of [x1,y1,x2,y2]
            xyxy = ops.xywh2xyxy(coords)
            x1 = int(xyxy[0])
            y1 = int(xyxy[1])
            x2 = int(xyxy[2])
            y2 = int(xyxy[3])

            # draw bounding box
            color = self.class_colour.get(label, (255, 255, 255))
            img_out = cv2.rectangle(img_out, (x1, y1), (x2, y2), color, thickness=2)

            # draw class label
            label_text = label if confidence is None else f"{label}: {confidence:.2f}"
            img_out = cv2.putText(img_out, label_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                  color, 2)

        return bboxes, img_out

    def _get_bounding_boxes(self, cv_img):
        """
        function:
            get bounding box and class label of target(s) in an image as detected by YOLOv8
        input:
            cv_img    : image, e.g., image read by the cv2.imread() function
            model_path: str, e.g., 'yolov8n.pt', trained YOLOv8 model
        output:
            bounding_boxes: list of lists, box info [label,[x,y,width,height]] for all detected targets in image
        """

        # predict target type and bounding box with your trained YOLO

        predictions = self.model.predict(cv_img, imgsz=320, verbose=False)

        # get bounding box and class label for target(s) detected
        bounding_boxes = []
        for prediction in predictions:
            boxes = prediction.boxes
            for box in boxes:
                if box.conf > 0.80:
                    # bounding format in [x, y, width, height]
                    box_cord = box.xywh[0]

                    box_label = box.cls  # class label of the box

                    bounding_boxes.append([
                        prediction.names[int(box_label)],
                        np.asarray(box_cord),
                        float(box.conf)
                    ])

        return bounding_boxes

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
        server_manager.close_servers()
        cv2.destroyAllWindows()