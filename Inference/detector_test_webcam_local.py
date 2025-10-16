#!/usr/bin/env python3
"""
Local Webcam Object Detection Test
Uses the Detector class to perform real-time object detection on local webcam feed.
This version uses a USB/built-in camera directly, not the gRPC stream.
"""

import cv2
import time
import argparse
from detector import Detector


def main():
    parser = argparse.ArgumentParser(
        description="Live webcam object detection using trained YOLO model"
    )
    parser.add_argument(
        '-m', '--model',
        type=str,
        default='Teds_Model.pt',
        help='Model filename (default: Teds_Model.pt)'
    )
    parser.add_argument(
        '-c', '--camera',
        type=int,
        default=0,
        help='Camera device index (default: 0)'
    )
    parser.add_argument(
        '--width',
        type=int,
        default=640,
        help='Camera capture width (default: 640)'
    )
    parser.add_argument(
        '--height',
        type=int,
        default=480,
        help='Camera capture height (default: 480)'
    )
    parser.add_argument(
        '--show-fps',
        action='store_true',
        help='Display FPS counter on screen'
    )
    args = parser.parse_args()

    print("=" * 50)
    print("Local Webcam Object Detection")
    print("=" * 50)
    print(f"Model: {args.model}")
    print(f"Camera: {args.camera}")
    print(f"Resolution: {args.width}x{args.height}")
    print("\nControls:")
    print("  'q' or ESC - Quit")
    print("  's' - Save current frame")
    print("=" * 50)

    # Initialize detector
    print("\nInitializing detector...")
    try:
        detector = Detector(args.model)
        print("✓ Detector initialized successfully")
    except Exception as e:
        print(f"✗ Failed to initialize detector: {e}")
        return

    # Initialize webcam
    print(f"Opening camera {args.camera}...")
    cap = cv2.VideoCapture(args.camera)
    
    if not cap.isOpened():
        print(f"✗ Failed to open camera {args.camera}")
        return
    
    # Set camera resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    
    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"✓ Camera opened (actual resolution: {actual_width}x{actual_height})")
    print("\nStarting detection... Press 'q' to quit\n")

    # FPS calculation variables
    frame_count = 0
    fps = 0
    fps_update_time = time.time()
    frame_save_count = 0

    try:
        while True:
            # Capture frame from webcam
            ret, frame = cap.read()
            
            if not ret:
                print("✗ Failed to grab frame")
                break

            frame_start_time = time.time()

            # Run detection (frame is already in BGR format from cv2.VideoCapture)
            bboxes, annotated_frame = detector.detect_single_image(frame)

            # Calculate FPS
            frame_count += 1
            current_time = time.time()
            if current_time - fps_update_time >= 1.0:
                fps = frame_count / (current_time - fps_update_time)
                frame_count = 0
                fps_update_time = current_time

            # Add FPS and detection info to frame
            info_y_offset = 30
            if args.show_fps:
                cv2.putText(
                    annotated_frame,
                    f"FPS: {fps:.1f}",
                    (10, info_y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2
                )
                info_y_offset += 30

            # Display detection count
            detection_text = f"Detections: {len(bboxes)}"
            cv2.putText(
                annotated_frame,
                detection_text,
                (10, info_y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            # Print detection info to console
            if bboxes:
                frame_time = time.time() - frame_start_time
                detected_classes = [bbox[0] for bbox in bboxes]
                print(f"Frame {frame_count}: Found {len(bboxes)} object(s) - {detected_classes} ({frame_time:.3f}s)")

            # Display frame (already in BGR format, native for cv2.imshow)
            cv2.imshow('Live Object Detection - Local Webcam', annotated_frame)

            # Handle key presses
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q') or key == 27:  # 'q' or ESC
                print("\nQuitting...")
                break
            elif key == ord('s'):  # Save frame
                filename = f"detection_frame_{frame_save_count:04d}.jpg"
                cv2.imwrite(filename, annotated_frame)
                frame_save_count += 1
                print(f"✓ Saved frame to {filename}")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n✗ Error during detection: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        print("\nCleaning up...")
        cap.release()
        cv2.destroyAllWindows()
        print("✓ Done")


if __name__ == "__main__":
    main()

