#!/usr/bin/env python3
"""
Live gRPC Video Stream Object Detection Test
Uses the Detector class to perform real-time object detection on video from gRPC server.
"""

import cv2
import time
import argparse
import os
import sys
import numpy as np
from detector import Detector

# Get the parent directory path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

# Now you can import modules from the parent directory
from tiality_server import TialityServerManager


def _decode_video_frame_opencv(frame_bytes: bytes) -> np.ndarray:
    """
    Decodes a byte array (JPEG) into an OpenCV numpy array (BGR format).
    
    Args:
        frame_bytes: The raw byte string of a single JPEG image.
    
    Returns:
        A numpy array (BGR format) or None if decoding fails.
    """
    try:
        # Convert the raw byte string to a 1D NumPy array
        np_array = np.frombuffer(frame_bytes, np.uint8)
        
        # Decode the NumPy array into an OpenCV image (BGR format)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        
        # Rotate 180 degrees (if needed for your camera)
        img = cv2.rotate(img, cv2.ROTATE_180)
        
        # TEMPORARY DEBUG: Check if JPEG from Pi is actually RGB, not BGR
        # If colors still look wrong, the Pi might be encoding in RGB format
        # Convert BGR to RGB (swap red and blue channels)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Now return as RGB (which YOLO might actually expect if trained on RGB images)
        return img
        
    except Exception as e:
        print(f"Error decoding frame: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Live gRPC video stream object detection using trained YOLO model"
    )
    parser.add_argument(
        '-m', '--model',
        type=str,
        default='Teds_Model.pt',
        help='Model filename (default: Teds_Model.pt)'
    )
    parser.add_argument(
        '--grpc-port',
        type=int,
        default=50051,
        help='gRPC server port (default: 50051)'
    )
    parser.add_argument(
        '--mqtt-broker',
        type=str,
        default='localhost',
        help='MQTT broker host/IP (default: localhost)'
    )
    parser.add_argument(
        '--mqtt-port',
        type=int,
        default=1883,
        help='MQTT broker port (default: 1883)'
    )
    parser.add_argument(
        '--show-fps',
        action='store_true',
        help='Display FPS counter on screen'
    )
    args = parser.parse_args()

    print("=" * 50)
    print("Live gRPC Video Stream Object Detection")
    print("=" * 50)
    print(f"Model: {args.model}")
    print(f"gRPC Port: {args.grpc_port}")
    print(f"MQTT Broker: {args.mqtt_broker}:{args.mqtt_port}")
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

    # Initialize TialityServerManager
    print(f"\nInitializing TialityServerManager...")
    print(f"Waiting for connection from Pi on gRPC port {args.grpc_port}...")
    server_manager = TialityServerManager(
        grpc_port=args.grpc_port,
        mqtt_port=args.mqtt_port,
        mqtt_broker_host_ip=args.mqtt_broker,
        decode_video_func=_decode_video_frame_opencv,
        num_decode_video_workers=1
    )
    server_manager.start_servers()
    print("✓ Server manager started")
    print("\nWaiting for Pi to connect and start streaming...")
    print("Starting detection... Press 'q' to quit\n")

    # FPS calculation variables
    frame_count = 0
    total_frame_count = 0
    fps = 0
    fps_update_time = time.time()
    frame_save_count = 0
    frames_received = 0
    last_frame_time = time.time()

    try:
        while True:
            # Get frame from server manager's decoded video queue
            frame = server_manager.get_video_frame()
            
            if frame is None:
                # No frame available yet, wait a bit
                time.sleep(0.01)
                
                # Check if we haven't received frames for a while
                if frames_received > 0 and time.time() - last_frame_time > 5.0:
                    print("⚠ No frames received for 5 seconds. Connection may be lost.")
                    last_frame_time = time.time()
                
                # Check for quit key even when no frames
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:
                    print("\nQuitting...")
                    break
                continue
            
            frames_received += 1
            last_frame_time = time.time()
            frame_start_time = time.time()

            # Run detection
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
            
            # Add connection status
            info_y_offset += 30
            connection_status = "Connected" if server_manager.connection_established_event.is_set() else "Waiting..."
            cv2.putText(
                annotated_frame,
                f"Status: {connection_status}",
                (10, info_y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0) if server_manager.connection_established_event.is_set() else (0, 165, 255),
                2
            )

            # Print detection info to console
            if bboxes:
                frame_time = time.time() - frame_start_time
                detected_classes = [bbox[0] for bbox in bboxes]
                print(f"Frame {total_frame_count}: Found {len(bboxes)} object(s) - {detected_classes} ({frame_time:.3f}s)")
            
            total_frame_count += 1

            # Convert RGB to BGR for cv2.imshow (since we're now using RGB for inference)
            display_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR)
            cv2.imshow('Live Object Detection - gRPC Stream', display_frame)

            # Handle key presses
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q') or key == 27:  # 'q' or ESC
                print("\nQuitting...")
                break
            elif key == ord('s'):  # Save frame
                filename = f"detection_frame_{frame_save_count:04d}.jpg"
                # Convert RGB to BGR before saving (cv2.imwrite expects BGR)
                save_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR)
                cv2.imwrite(filename, save_frame)
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
        print(f"Total frames processed: {total_frame_count}")
        print(f"Total detections shown: {frames_received}")
        server_manager.close_servers()
        cv2.destroyAllWindows()
        print("✓ Done")


if __name__ == "__main__":
    main()

