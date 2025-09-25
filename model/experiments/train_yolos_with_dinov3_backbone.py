#!/usr/bin/env python3
"""
Train a YOLOS object detection model using a pre-trained DINOv3 backbone.

This script leverages the high-level `YolosForObjectDetection` class from Hugging Face,
which simplifies training significantly by handling the detection head, loss calculation,
and Hungarian matching internally.

- Backbone: DINOv3 ViT-S/16 (e.g., facebook/dinov3-vits16-pretrain-lvd1689m)
- Head: YOLOS/DETR-style detection head
- Input Labels: YOLO format (cx cy w h normalized)

Usage (from the `model/` directory):
  uv run python experiments/train_yolos_with_dinov3_backbone.py \
    --epochs 10 --batch-size 8 --lr 1e-4 --freeze-backbone
"""

import argparse
import os
from pathlib import Path
from typing import List

import torch
from PIL import Image as PILImage, ImageDraw
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm
from dotenv import load_dotenv

from transformers import YolosImageProcessor, YolosForObjectDetection, DINOv3ViTModel

try:
    import wandb
except ImportError:
    wandb = None

# --- Dataset --- #

IMG_EXTS = (".png", ".jpg", ".jpeg")

class YoloDetectionDataset(Dataset):
    def __init__(self, samples: list, labels_root: Path, class_names: List[str]):
        self.samples = samples
        self.class_to_id = {name: i for i, name in enumerate(class_names)}
        self.id_to_class = {i: name for i, name in enumerate(class_names)}

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label_path, class_name = self.samples[idx]
        image = PILImage.open(img_path).convert("RGB")

        boxes, labels = [], []
        with open(label_path, 'r') as f:
            for line in f.readlines():
                parts = line.strip().split()
                # YOLO format: class_id cx cy w h
                # We use the folder-derived class_id, not the one in the file.
                class_id = self.class_to_id[class_name]
                cx, cy, w, h = map(float, parts[1:])
                boxes.append([cx, cy, w, h])
                labels.append(class_id)

        # Format for YolosForObjectDetection
        targets = [{'class_labels': torch.tensor(labels), 'boxes': torch.tensor(boxes)}]
        return image, targets


def collate_fn(batch, image_processor):
    # The image processor is now passed into the dataset, so we can instantiate it once
    # and pass it around. We'll grab it from the first dataset instance.
    images, raw_targets = list(zip(*batch))
    
    # 1. Process images
    batch_encoding = image_processor(images=images, return_tensors="pt")
    
    # 2. Format labels for the model
    # The model expects a list of dictionaries, one for each image in the batch.
    # Each dictionary contains the 'class_labels' and 'boxes' for that image.
    labels = []
    for target_list in raw_targets:
        # Our getitem returns a list containing one dict, so we extract it.
        if isinstance(target_list, list) and len(target_list) > 0:
            labels.append(target_list[0])
        else:
            # Handle cases where a target might be empty or malformed
            labels.append({'class_labels': torch.tensor([]), 'boxes': torch.tensor([])})

    batch_encoding['labels'] = labels
    return batch_encoding


# --- Main Training Logic --- #

def get_default_paths() -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parent.parent.parent
    dataset_root = repo_root / "dataset"
    labels_root = repo_root / "model" / "auto_boxes_text"
    return dataset_root, labels_root

def list_class_names(dataset_root: Path) -> List[str]:
    return sorted([d.name for d in dataset_root.iterdir() if d.is_dir()])

def get_all_samples(dataset_root: Path, labels_root: Path) -> List:
    samples = []
    for class_name in sorted([d.name for d in dataset_root.iterdir() if d.is_dir()]):
        img_dir = dataset_root / class_name
        if not img_dir.exists(): continue
        for img_path in sorted(img_dir.iterdir()):
            if img_path.suffix.lower() in IMG_EXTS:
                label_path = labels_root / class_name / "labels" / f"{img_path.stem}.txt"
                if label_path.exists():
                    samples.append((img_path, label_path, class_name))
    return samples

def log_predictions_to_wandb(model, val_loader, image_processor, device, id_to_class, epoch, args):
    model.eval()
    images_to_log = []
    val_samples = val_loader.dataset.samples[:args.num_val_images_to_log]

    for img_path, label_path, class_name in val_samples:
        image = PILImage.open(img_path).convert("RGB")
        image_with_boxes = image.copy()
        draw = ImageDraw.Draw(image_with_boxes)
        
        # Draw Ground truth boxes (in green)
        with open(label_path, 'r') as f:
            for line in f.readlines():
                parts = line.strip().split()
                cx, cy, w, h = map(float, parts[1:])
                x_min, y_min = image.width * (cx - w/2), image.height * (cy - h/2)
                x_max, y_max = image.width * (cx + w/2), image.height * (cy + h/2)
                draw.rectangle([x_min, y_min, x_max, y_max], outline="green", width=2)
                draw.text((x_min, y_min), f"gt_{class_name}", fill="green")

        # Get and Draw Model predictions (in red)
        inputs = image_processor(images=image, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        
        target_sizes = torch.tensor([image.size[::-1]]).to(device)
        results = image_processor.post_process_object_detection(outputs, threshold=0.5, target_sizes=target_sizes)[0]

        for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
            box = [round(i, 2) for i in box.tolist()]
            draw.rectangle(box, outline="red", width=2)
            caption = f"pred_{id_to_class[label.item()]} ({score:.2f})"
            draw.text((box[0], box[1]), caption, fill="red")

        images_to_log.append(wandb.Image(image_with_boxes, caption=f"{img_path.name}"))

    wandb.log({f"epoch_{epoch+1}_predictions": images_to_log})
    model.train()


def train(args):
    # --- Setup ---
    if not args.cpu and torch.cuda.is_available():
        device = torch.device("cuda")
    elif not args.cpu and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    dataset_root, labels_root = get_default_paths()
    if args.dataset_root: dataset_root = Path(args.dataset_root)
    if args.labels_root: labels_root = Path(args.labels_root)

    class_names = list_class_names(dataset_root)
    num_classes = len(class_names)
    assert num_classes > 0, f"No class directories found in {dataset_root}"

    # --- Model --- #
    # 1. Load a standard YOLOS model
    model = YolosForObjectDetection.from_pretrained(
        args.yolos_model_id,
        num_labels=num_classes,
        ignore_mismatched_sizes=True # Allow head replacement
    )

    # 2. Load the DINOv3 backbone
    dinov3_backbone = DINOv3ViTModel.from_pretrained(args.dinov3_backbone_id)

    # 3. Replace the YOLOS backbone and adjust the prediction heads
    model.vit = dinov3_backbone

    # The YOLOS-tiny heads expect a hidden dim of 192, but DINOv3-ViTS16 has 384.
    # We need to replace the heads with new ones that match the backbone's output dimension.
    hidden_dim = dinov3_backbone.config.hidden_size
    model.class_labels_classifier = torch.nn.Sequential(
        torch.nn.Linear(hidden_dim, hidden_dim),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_dim, num_classes + 1)
    )
    model.bbox_predictor = torch.nn.Sequential(
        torch.nn.Linear(hidden_dim, hidden_dim),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_dim, hidden_dim),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_dim, 4)
    )
    model.to(device)

    if args.freeze_backbone:
        for name, param in model.vit.named_parameters():
            param.requires_grad = False

    # --- Data --- #
    image_processor = YolosImageProcessor.from_pretrained(args.yolos_model_id)
    all_samples = get_all_samples(dataset_root, labels_root)
    train_samples, val_samples = train_test_split(all_samples, test_size=args.val_split, random_state=42)

    train_dataset = YoloDetectionDataset(train_samples, labels_root, class_names)
    val_dataset = YoloDetectionDataset(val_samples, labels_root, class_names)

    collate_with_processor = lambda batch: collate_fn(batch, image_processor)
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, collate_fn=collate_with_processor)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, collate_fn=collate_with_processor)

    # --- W&B --- #
    use_wandb = wandb and not args.no_wandb
    if use_wandb:
        load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
        if os.getenv("WANDB_TOKEN") and not os.getenv("WANDB_API_KEY"):
            os.environ["WANDB_API_KEY"] = os.getenv("WANDB_TOKEN", "")
        if os.getenv("WANDB_API_KEY"):
            wandb.init(project=args.wandb_project, name=args.run_name, config=vars(args))
            print("Weights & Biases logging enabled.")
        else:
            use_wandb = False
            print("Weights & Biases logging disabled (API key not found).")
    else:
        print("Weights & Biases logging disabled.")

    # --- Training Loop --- #
    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=args.lr, weight_decay=1e-4)

    for epoch in range(args.epochs):
        # --- Training Step ---
        model.train()
        train_loss = 0.0
        pbar = tqdm(train_loader, desc=f"Epoch {epoch + 1}/{args.epochs} [Training]")
        for batch in pbar:
            pixel_values = batch['pixel_values'].to(device)
            labels = [{k: v.to(device) for k, v in t.items()} for t in batch['labels']]

            outputs = model(pixel_values=pixel_values, labels=labels)
            loss = outputs.loss
            train_loss += loss.item()

            pbar.set_postfix({"loss": loss.item()})
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()

        avg_train_loss = train_loss / len(train_loader)

        # --- Validation Step ---
        model.eval()
        val_loss = 0.0
        pbar_val = tqdm(val_loader, desc=f"Epoch {epoch + 1}/{args.epochs} [Validation]")
        with torch.no_grad():
            for batch in pbar_val:
                pixel_values = batch['pixel_values'].to(device)
                labels = [{k: v.to(device) for k, v in t.items()} for t in batch['labels']]

                outputs = model(pixel_values=pixel_values, labels=labels)
                loss = outputs.loss
                val_loss += loss.item()
                pbar_val.set_postfix({"val_loss": loss.item()})
        
        avg_val_loss = val_loss / len(val_loader)

        print(f"Epoch {epoch+1}: Train Loss: {avg_train_loss:.4f}, Val Loss: {avg_val_loss:.4f}")

        # --- Logging ---
        if use_wandb:
            wandb.log({
                "train/loss": avg_train_loss,
                "val/loss": avg_val_loss,
                "epoch": epoch + 1
            })
            log_predictions_to_wandb(model, val_loader, image_processor, device, val_dataset.id_to_class, epoch, args)

        # --- Save Checkpoint --- #
        ckpt_dir = Path(args.out_dir)
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(ckpt_dir / f"epoch_{epoch+1}")

    if use_wandb: wandb.finish()
    print("Training complete.")


def parse_args():
    parser = argparse.ArgumentParser(description="Train YOLOS with a DINOv3 backbone.")
    # Model IDs
    parser.add_argument("--yolos-model-id", type=str, default="hustvl/yolos-tiny", help="Base YOLOS model to use for the head.")
    parser.add_argument("--dinov3-backbone-id", type=str, default="facebook/dinov3-vits16-pretrain-lvd1689m", help="DINOv3 backbone model.")
    # Data
    parser.add_argument("--dataset-root", type=str, default=None, help="Path to dataset root directory.")
    parser.add_argument("--labels-root", type=str, default=None, help="Path to YOLO labels root directory.")
    # Training
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--val-split", type=float, default=0.2, help="Fraction of the dataset to use for validation.")
    parser.add_argument("--num-val-images-to-log", type=int, default=10, help="Number of validation images to log to W&B.")
    parser.add_argument("--freeze-backbone", action="store_true", help="Freeze the DINOv3 backbone during training.")
    parser.add_argument("--out-dir", type=str, default="./experiments/yolos_dinov3_checkpoints", help="Output directory for checkpoints.")
    parser.add_argument("--cpu", action="store_true", help="Force CPU.")
    # W&B
    parser.add_argument("--wandb-project", type=str, default="yolos-dinov3-experiment")
    parser.add_argument("--run-name", type=str, default=None, help="A name for the W&B run.")
    parser.add_argument("--no-wandb", action="store_true", help="Disable Weights & Biases logging.")

    return parser.parse_args()

if __name__ == "__main__":
    train(parse_args())
