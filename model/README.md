# GroundingDINO Auto-Labeling Pipeline

This directory contains a streamlined pipeline for generating bounding box labels using a text-prompted zero-shot object detector (GroundingDINO).

## Prerequisites

- Install uv: https://github.com/astral-sh/uv
- Python 3.10+ recommended
- A `dataset/` folder located at the root of this repository, structured as follows:

```
<repository-root>/
  dataset/
    class_a/  image1.png, image2.jpg, ...
    class_b/  ...
```

## 1. Environment Setup

From the `model/` directory, run the installation script:

```bash
bash scripts/00_install.sh
```

This will create a virtual environment (`.venv/`), install the required packages from `requirements.txt`, and activate the environment.

## 2. Auto-Labeling with GroundingDINO

The `autolabel_boxes.py` script uses GroundingDINO to detect objects based on a text prompt and saves the bounding boxes in YOLO format.

### Usage

To run the script for a specific class, use the following command structure:

```bash
uv run python autolabel_boxes.py --class "<class_name>" --prompt "<prompt_text>"
```

### Example

To label all images in the `kangaroo` class using the prompt "kangaroo" and the `grounding-dino-tiny` model:

```bash
uv run python autolabel_boxes.py \
    --class "kangaroo" \
    --prompt "kangaroo" \
    --detector-model "IDEA-Research/grounding-dino-tiny" \
    --det-threshold 0.35 \
    --text-threshold 0.25
```

### Outputs

For each class, the script generates the following outputs in the `model/auto_boxes_text/<class_name>/` directory:

- `labels/`: Contains `.txt` files in YOLO format (`<class_id> <x_center> <y_center> <width> <height>`).
- `overlays/`: Contains images with the detected bounding boxes drawn on them for quick verification.
- `classes.txt` and `predefined_classes.txt`: Text files defining the class name, useful for annotation tools like LabelImg.

### Advanced Options

- **SAM2 Refinement**: For tighter bounding boxes, use `--refine-with-sam2` to segment the detected box and use the mask's bounding box instead.
- **Model Selection**: Choose between `IDEA-Research/grounding-dino-tiny` (fast) and `IDEA-Research/grounding-dino-base` (more accurate) with the `--detector-model` flag.
- **Filtering**: Use `--max-dets` to limit the number of detections per image and `--prefer-smallest` to select the smallest box among the top candidates.

For a full list of options, run:

```bash
uv run python autolabel_boxes.py --help
```
