#!/usr/bin/env python3
"""
GroundingDINO-only bounding box labeller.

- Uses a text prompt (e.g., the class name) to detect boxes with GroundingDINO.
- Saves YOLO-format label files per image and optional overlay images for quick QA.

Usage examples:
  uv run python auto_box_with_grounding_dino.py --class "kangaroo" --prompt "kangaroo" \
      --detector-model "IDEA-Research/grounding-dino-tiny" --det-threshold 0.25 --text-threshold 0.25

  uv run python auto_box_with_grounding_dino.py --class "cockatoo" --prompt "toy bird" \
      --detector-model "IDEA-Research/grounding-dino-base" --det-threshold 0.35 --text-threshold 0.25 --max-dets 2

Outputs:
  auto_boxes_text/<class>/
    - labels/<stem>.txt   (YOLO: class_id x y w h, normalized)
    - overlays/<stem>.png (image with boxes drawn) [optional, always saved]
    - classes.txt         (the single class for this run; class_id 0)

Notes:
- YOLO expects no label file if there are no detections; we skip creating the .txt in that case.
- Boxes are clamped to image bounds before normalization.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image as PILImage, ImageDraw
import torch
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection, Sam2Processor, Sam2Model
from tqdm import tqdm

# Paths (relative to this script)
THIS_DIR = Path(__file__).resolve().parent
DATASET_DIR = (THIS_DIR / "./dataset").resolve()
OUTPUT_DIR = (THIS_DIR / "auto_boxes_text").resolve()


def to_device(device_arg: str | None) -> torch.device:
    if device_arg:
        return torch.device(device_arg)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def clamp_box(xmin, ymin, xmax, ymax, width, height):
    xmin = max(0, min(int(round(xmin)), width - 1))
    ymin = max(0, min(int(round(ymin)), height - 1))
    xmax = max(0, min(int(round(xmax)), width - 1))
    ymax = max(0, min(int(round(ymax)), height - 1))
    if xmax < xmin:
        xmin, xmax = xmax, xmin
    if ymax < ymin:
        ymin, ymax = ymax, ymin
    return xmin, ymin, xmax, ymax


def yolo_line_from_xyxy(xmin, ymin, xmax, ymax, width, height, class_id: int = 0) -> str:
    x_c = ((xmin + xmax) / 2.0) / float(width)
    y_c = ((ymin + ymax) / 2.0) / float(height)
    w = (xmax - xmin) / float(width)
    h = (ymax - ymin) / float(height)
    # clip to [0,1]
    x_c = max(0.0, min(1.0, x_c))
    y_c = max(0.0, min(1.0, y_c))
    w = max(0.0, min(1.0, w))
    h = max(0.0, min(1.0, h))
    return f"{class_id} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}"


def draw_box_on_image(img: PILImage, box, color=(255, 0, 0), text: str | None = None) -> PILImage:
    draw = ImageDraw.Draw(img)
    xmin, ymin, xmax, ymax = box
    draw.rectangle([xmin, ymin, xmax, ymax], outline=color, width=3)
    if text:
        # draw simple text box
        tw, th = draw.textlength(text), 14
        tx, ty = xmin, max(0, ymin - th - 2)
        draw.rectangle([tx, ty, tx + tw + 6, ty + th + 4], fill=(0, 0, 0))
        draw.text((tx + 3, ty + 2), text, fill=(255, 255, 255))
    return img


def compute_bbox_from_mask(mask_bool: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask_bool)
    if ys.size == 0 or xs.size == 0:
        return 0, 0, mask_bool.shape[1] - 1, mask_bool.shape[0] - 1  # xmin, ymin, xmax, ymax
    ymin, ymax = int(ys.min()), int(ys.max())
    xmin, xmax = int(xs.min()), int(xs.max())
    return xmin, ymin, xmax, ymax


def refine_box_with_sam2(img_pil: PILImage, box_xyxy, sam2_processor: Sam2Processor, sam2_model: Sam2Model, device, pad_px: int = 0):
    try:
        xmin, ymin, xmax, ymax = box_xyxy
        input_boxes = [[[int(xmin), int(ymin), int(xmax), int(ymax)]]]
        inputs = sam2_processor(images=img_pil, input_boxes=input_boxes, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = sam2_model(**inputs)
        masks = sam2_processor.post_process_masks(outputs.pred_masks.cpu(), inputs["original_sizes"])[0]
        if masks.ndim == 4:
            masks = masks[0]
        mask_np = np.array(masks[0] > 0, dtype=np.uint8)
        xmin2, ymin2, xmax2, ymax2 = compute_bbox_from_mask(mask_np.astype(bool))
        # clamp to image bounds
        width, height = img_pil.size
        if pad_px and pad_px > 0:
            xmin2 -= pad_px
            ymin2 -= pad_px
            xmax2 += pad_px
            ymax2 += pad_px
        xmin2, ymin2, xmax2, ymax2 = clamp_box(xmin2, ymin2, xmax2, ymax2, width, height)
        return xmin2, ymin2, xmax2, ymax2
    except Exception:
        return box_xyxy


def main():
    parser = argparse.ArgumentParser(description="GroundingDINO-only bounding box labeller")
    parser.add_argument("--class", dest="class_name", required=True, help="Class name (dataset folder under ../dataset)")
    parser.add_argument("--prompt", default=None, help="Text prompt for GroundingDINO (defaults to class name)")
    parser.add_argument("--detector-model", default="IDEA-Research/grounding-dino-tiny", help="GroundingDINO model id (tiny or base)")
    parser.add_argument("--det-threshold", type=float, default=0.25, help="Box threshold")
    parser.add_argument("--text-threshold", type=float, default=0.25, help="Text threshold")
    parser.add_argument("--num-images", type=int, default=-1, help="Max images to process (-1 = all)")
    parser.add_argument("--max-dets", type=int, default=1, help="Max boxes to save per image")
    parser.add_argument("--prefer-smallest", action="store_true", help="Among the top-k by score, pick the smallest box by area")
    parser.add_argument("--device", default=None, help="torch device (cuda or cpu, default auto)")
    parser.add_argument("--last", type=int, default=0, help="Process only the last N images (takes precedence over --num-images if > 0)")
    parser.add_argument("--refine-with-sam2", action="store_true", help="Use SAM2 with the detected box to tighten the box to the mask's bbox")
    parser.add_argument("--sam2-model", default="facebook/sam2-hiera-small", help="SAM2 model id (used only if --refine-with-sam2)")
    parser.add_argument("--refine-pad", type=int, default=0, help="Pixel padding to add around SAM2-refined box (default 0)")
    args = parser.parse_args()

    class_name = args.class_name
    prompt = args.prompt or class_name
    device = to_device(args.device)

    # Load models
    processor = AutoProcessor.from_pretrained(args.detector_model)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(args.detector_model).to(device)
    sam2_model = None
    sam2_processor = None
    if args.refine_with_sam2:
        sam2_model = Sam2Model.from_pretrained(args.sam2_model).to(device)
        sam2_processor = Sam2Processor.from_pretrained(args.sam2_model)

    # Dataset
    class_dir = DATASET_DIR / class_name
    if not class_dir.exists():
        raise FileNotFoundError(f"Dataset class directory not found: {class_dir}")

    images = (
        sorted(class_dir.glob("*.png"))
        + sorted(class_dir.glob("*.jpg"))
        + sorted(class_dir.glob("*.jpeg"))
    )
    if args.last and args.last > 0:
        images = images[-args.last:]
    elif args.num_images > 0:
        images = images[: args.num_images]

    # Output dirs
    labels_dir = (OUTPUT_DIR / class_name / "labels")
    overlays_dir = (OUTPUT_DIR / class_name / "overlays")
    labels_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    # classes files (single-class for this run)
    classes_txt = OUTPUT_DIR / class_name / "classes.txt"
    classes_txt.write_text(f"{prompt}\n")
    predefined_classes_txt = OUTPUT_DIR / class_name / "predefined_classes.txt"
    predefined_classes_txt.write_text(f"{prompt}\n")

    for img_path in tqdm(images, desc=f"Processing {class_name}"):
        img_pil = PILImage.open(img_path).convert("RGB")
        width, height = img_pil.size

        # Run GroundingDINO
        encoding = processor(images=img_pil, text=[prompt], return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**encoding)

        target_sizes = torch.tensor([(height, width)], device=device)
        results = processor.post_process_grounded_object_detection(
            outputs,
            target_sizes=target_sizes,
            threshold=args.det_threshold,
            text_threshold=args.text_threshold,
        )[0]

        boxes = results.get("boxes", [])
        scores = results.get("scores", [])
        labels = results.get("labels", [])

        # Sort by score desc and take top-k
        if len(scores) > 0:
            order = np.argsort(-np.array(scores))
            order = order[: args.max_dets]
            if args.prefer_smallest and len(order) > 1:
                # Reorder the selected candidates by area ascending and keep first
                def _area(idx):
                    b = boxes[idx].tolist() if hasattr(boxes[idx], 'tolist') else boxes[idx]
                    xmin, ymin, xmax, ymax = b
                    return max(0.0, (xmax - xmin)) * max(0.0, (ymax - ymin))
                order = sorted(order, key=_area)
        else:
            order = []

        # Write YOLO labels file if any dets
        yolo_lines = []
        img_with_boxes = img_pil.copy()
        for idx in order:
            xmin, ymin, xmax, ymax = boxes[idx].tolist() if hasattr(boxes[idx], 'tolist') else boxes[idx]
            xmin, ymin, xmax, ymax = clamp_box(xmin, ymin, xmax, ymax, width, height)
            if args.refine_with_sam2 and sam2_model is not None and sam2_processor is not None:
                xmin, ymin, xmax, ymax = refine_box_with_sam2(
                    img_pil,
                    (xmin, ymin, xmax, ymax),
                    sam2_processor,
                    sam2_model,
                    device,
                    pad_px=args.refine_pad,
                )
            yolo_lines.append(yolo_line_from_xyxy(xmin, ymin, xmax, ymax, width, height, class_id=0))
            label_txt = f"{prompt} {scores[idx]:.2f}"
            img_with_boxes = draw_box_on_image(img_with_boxes, (xmin, ymin, xmax, ymax), color=(255, 0, 0), text=label_txt)

        if yolo_lines:
            label_file = labels_dir / f"{img_path.stem}.txt"
            label_file.write_text("\n".join(yolo_lines) + "\n")

        # Always save overlay for QA
        img_with_boxes.save(overlays_dir / f"{img_path.stem}.png")

    print(f"Done. Labels saved under: {labels_dir}\nOverlays under: {overlays_dir}")


if __name__ == "__main__":
    main()
