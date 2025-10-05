#!/usr/bin/env python3
"""
Real-time wildlife detection using RF-DETR with webcam feed.
Optimized for performance with Apple Silicon GPU acceleration.
"""

import cv2
import time
import torch
import supervision as sv
from collections import deque
from rfdetr import RFDETRNano

# Custom fine-tuned model classes (Australian wildlife)
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

# Configuration
MODEL_PATH = "model/rfdetr_4191_checkpoint_best_total_1.pth"
CONFIDENCE_THRESHOLD = 0.5
INPUT_SIZE = 640  # Square input for optimal performance
FRAME_SKIP = 1    # Process every N frames (1 = process all, 2 = skip every other frame)

print("="*70)
print("🐨 Wildlife Detection - Real-time Webcam Inference")
print("="*70)

# Initialize model
print("\n📦 Loading RF-DETR model...")
model = RFDETRNano(pretrain_weights=MODEL_PATH)

# Check device
device = model.model.device
device_name = 'CPU'
if 'mps' in str(device):
    device_name = '🍎 Apple Silicon GPU (MPS)'
elif 'cuda' in str(device):
    device_name = '🎮 NVIDIA GPU (CUDA)'
print(f"   Device: {device_name}")

# Optimize for inference
print("⚡ Optimizing model for real-time inference...")
try:
    model.optimize_for_inference(compile=False, dtype=torch.float16)
    print("   ✓ Model optimized (FP16, no-compile mode)")
except Exception as e:
    print(f"   ⚠️  Optimization failed: {e}")
    print("   Continuing with unoptimized model...")

# Initialize webcam
print("\n📹 Initializing webcam...")
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("❌ Error: Could not open webcam")
    exit(1)

# Set webcam resolution (optional - adjust if needed)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"   ✓ Webcam initialized: {actual_width}x{actual_height}")

# Initialize supervision annotators with color palette
color = sv.ColorPalette.from_hex([
    "#888888",  # 0: animals - Gray
    "#ffffff",  # 1: Cockatoo - White
    "#08780c",  # 2: Crocodile - Green
    "#90ff00",  # 3: Frog - Yellow-Green
    "#f70e0e",  # 4: Kangaroo - Red
    "#bbeffe",  # 5: Koala - Light Blue
    "#FFABAB",  # 6: Owl - Pink
    "#ffa521",  # 7: Platypus - Orange
    "#006df2",  # 8: Snake - Blue
    "#000000",  # 9: Tassie Dev - Black
    "#FFFF00"   # 10: Wombat - Yellow
])

bbox_annotator = sv.BoxAnnotator(color=color, thickness=2)
label_annotator = sv.LabelAnnotator(
    color=color,
    text_color=sv.Color.BLACK,
    text_scale=0.5,
    text_thickness=1
)

# FPS tracking
fps_tracker = deque(maxlen=30)
frame_count = 0
start_time = time.time()

print("\n🎬 Starting real-time detection...")
print("   Press 'q' to quit")
print("   Press 's' to toggle frame skipping")
print("-"*70)

try:
    while True:
        success, frame = cap.read()
        if not success:
            print("⚠️  Failed to read frame from webcam")
            break

        frame_count += 1
        
        # Frame skipping for better FPS
        if frame_count % FRAME_SKIP != 0:
            # Show last annotated frame
            cv2.imshow("Wildlife Detection", annotated_frame if 'annotated_frame' in locals() else frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            continue

        # Run inference
        inference_start = time.time()
        
        # Convert BGR to RGB for model
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Resize to square for optimal performance
        h, w = frame.shape[:2]
        if w != INPUT_SIZE or h != INPUT_SIZE:
            frame_resized = cv2.resize(frame_rgb, (INPUT_SIZE, INPUT_SIZE))
        else:
            frame_resized = frame_rgb
        
        # Predict
        detections = model.predict(frame_resized, threshold=CONFIDENCE_THRESHOLD)
        
        inference_time = time.time() - inference_start
        fps = 1.0 / inference_time if inference_time > 0 else 0
        fps_tracker.append(fps)
        avg_fps = sum(fps_tracker) / len(fps_tracker)
        
        # Scale detections back to original frame size
        if w != INPUT_SIZE or h != INPUT_SIZE:
            scale_x = w / INPUT_SIZE
            scale_y = h / INPUT_SIZE
            
            if detections.xyxy is not None and len(detections.xyxy) > 0:
                scaled_xyxy = detections.xyxy.copy()
                scaled_xyxy[:, [0, 2]] *= scale_x
                scaled_xyxy[:, [1, 3]] *= scale_y
                
                detections = sv.Detections(
                    xyxy=scaled_xyxy,
                    confidence=detections.confidence,
                    class_id=detections.class_id,
                )
        
        # Create labels
        labels = []
        if detections.class_id is not None and len(detections.class_id) > 0:
            for class_id, confidence in zip(detections.class_id, detections.confidence):
                class_name = CUSTOM_CLASSES[class_id] if class_id < len(CUSTOM_CLASSES) else f"class_{class_id}"
                labels.append(f"{class_name} {confidence:.2f}")
        
        # Annotate frame
        annotated_frame = frame.copy()
        if len(detections) > 0:
            annotated_frame = bbox_annotator.annotate(annotated_frame, detections)
            annotated_frame = label_annotator.annotate(annotated_frame, detections, labels)
        
        # Draw FPS and info overlay
        cv2.putText(
            annotated_frame,
            f"FPS: {avg_fps:.1f} | Detections: {len(detections)}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )
        
        cv2.putText(
            annotated_frame,
            f"Inference: {inference_time*1000:.1f}ms | Frame Skip: {FRAME_SKIP}",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1
        )
        
        # Display
        cv2.imshow("Wildlife Detection", annotated_frame)
        
        # Handle key presses
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            # Toggle frame skip
            FRAME_SKIP = 1 if FRAME_SKIP > 1 else 2
            print(f"   Frame skip: {FRAME_SKIP}")

except KeyboardInterrupt:
    print("\n\n⏸️  Interrupted by user")

finally:
    # Cleanup
    elapsed_time = time.time() - start_time
    print("\n" + "="*70)
    print("📊 Session Statistics:")
    print(f"   Total frames processed: {frame_count}")
    print(f"   Total time: {elapsed_time:.1f}s")
    print(f"   Average FPS: {frame_count/elapsed_time:.1f}")
    print("="*70)
    
    cap.release()
    cv2.destroyAllWindows()
    print("\n✅ Done!")

