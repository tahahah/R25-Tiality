import cv2
import os
import numpy as np
import sys
from copy import deepcopy
from ultralytics import YOLO
from ultralytics.utils import ops

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