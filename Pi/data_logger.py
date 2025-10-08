#!/usr/bin/env python3
"""
R25-Tiality Data Logger
Continuously captures and saves video data independently of gRPC/WebRTC
Continues logging even when gRPC connection fails
"""

import os
import json
import time
import base64
import threading
import queue
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
import logging
from picamera2 import Picamera2

# Configure the basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

#VIDEO CAPTURE CLASS
class VideoCapture:
    """Handles video capture from Pi's camera independently of gRPC stream"""
    #Quality is the JPEG quality of the video 1-100 (75 = 50-80kB / frame) (100 = 200-300kB / frame) 
    def __init__(self, quality=75):
        self.quality = quality
        self.picam2 = None
        self.running = False
    #Start the video capture and configures camera settings and is called only once when you want to start the video capture
    def start_capture(self):
        """Start video capture"""
        try:
            self.picam2 = Picamera2()
            config = self.picam2.create_preview_configuration(main={"format": "RGB888"}) #This is the OpenCV Default (Can make it YUV420 for more efficient video) 
            self.picam2.configure(config)
            self.picam2.start()
            self.running = True
            logger.info("Video capture started")
        except Exception as e:
            logger.error(f"Failed to start video capture: {e}")
    #Captures a single frame and returns it as JPEG bytes (call as many times as you want to capture frames per second)   
    def capture_frame(self):
        """Capture a single frame and return as JPEG bytes"""
        if self.picam2 and self.running:
            try:
                # Capture frame as numpy array
                frame_array = self.picam2.capture_array()
                
                # Convert RGB to BGR for OpenCV
                frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)
                
                # Encode as JPEG
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
                success, encoded_image = cv2.imencode(".jpg", frame_bgr, encode_param)
                
                if success:
                    return encoded_image.tobytes()
                else:
                    logger.warning("Failed to encode video frame")
                    return None
                    
            except Exception as e:
                logger.error(f"Video capture error: {e}")
                return None
        return None
        
    def stop_capture(self):
        """Stop video capture"""
        self.running = False
        if self.picam2:
            self.picam2.stop()
        logger.info("Video capture stopped")

#AUDIO CAPTURE CLASS
class AudioCapture:
    
    
    def __init__(self, sample_rate=44100, chunk_size=1024, channels=1):
        # TODO: Initialize audio capture parameters
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.running = False
        logger.info("Audio capture initialized (placeholder)")
        
    def start_capture(self):
        # TODO: Start audio capture
        logger.info("Audio capture started (placeholder)")
        self.running = True
        
    def read_audio_chunk(self):
        # TODO: Read audio chunk
        # Return audio data as bytes or None if no data
        if self.running:
            # Placeholder - return None for now
            time.sleep(0.01)  # Prevent busy waiting
            return None
        return None
        
    def stop_capture(self):
        # TODO: Stop audio capture
        self.running = False
        logger.info("Audio capture stopped (placeholder)")



#DATA LOGGER CLASS
class DataLogger:
    """Main data logger that captures and stores video and audio data"""

    #Currently have an enable audio option, as there is no audio capture functionality yet
    #Specify the save interval (seconds) , specify quality if wanting to change it   
    def __init__(self, save_interval=5.0, base_path="/home/pi/data_logs", quality=75, enable_audio=False, frame_rate=30, 
    audio_sample_rate=44100, audio_chunk_size=1024):

        self.save_interval = save_interval
        self.base_path = Path(base_path)
        self.quality = quality
        self.enable_audio = enable_audio
        self.frame_rate = frame_rate
        self.audio_sample_rate = audio_sample_rate
        self.audio_chunk_size = audio_chunk_size
        # Create session folder (with a timestamp)
        self.session_folder = self._create_session_folder()
        
        # Initialize video capture
        self.video_capture = VideoCapture(quality=quality)
        
        # Initialize audio capture (if enabled)
        self.audio_capture = None
        if self.enable_audio:
            self.audio_capture = AudioCapture(sample_rate=audio_sample_rate, chunk_size=audio_chunk_size)
        
        # Data queues
        video_queue_size = int(self.frame_rate * self.save_interval) #This is the size of the queue based on the frame rate and save interval
        self.video_queue = queue.Queue(maxsize=video_queue_size)  
        if self.enable_audio:
            audio_queue_size = int((self.audio_sample_rate / self.audio_chunk_size) * self.save_interval) #This is the size of the queue based on the audio sample rate and save interval
            self.audio_queue = queue.Queue(maxsize=audio_queue_size)
        
        # Threading
        self.running = False
        self.video_thread = None
        self.audio_thread = None
        self.save_thread = None
        
        # Statistics
        self.stats = {
            "video_frames_captured": 0,
            "audio_chunks_captured": 0,
            "files_saved": 0,
            "session_start": datetime.now(),
            "last_save_time": None,
            "grpc_status": "unknown"
        }
        
        logger.info(f"Data logger initialized. Session: {self.session_folder}")
        logger.info(f"Video: Enabled, Audio: {'Enabled' if enable_audio else 'Disabled'}")
    
    def _create_session_folder(self):
        """Create a new session folder with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_folder = self.base_path / f"session_{timestamp}"
        session_folder.mkdir(parents=True, exist_ok=True)
        
        # Create subfolders
        (session_folder / "video").mkdir(exist_ok=True)
        (session_folder / "metadata").mkdir(exist_ok=True)
        
        # Create audio folder if audio is enabled
        if self.enable_audio:
            (session_folder / "audio").mkdir(exist_ok=True)
        
        return session_folder
    
    def _video_capture_loop(self):        
        """Continuously capture video frames at specified frame rate"""
        logger.info(f"Video capture thread started - {self.frame_rate} FPS")
       
        while self.running:
            try:
                frame_bytes = self.video_capture.capture_frame()
                if frame_bytes:
                    timestamp = datetime.now().isoformat()
                    video_data = {
                        "timestamp": timestamp,
                        "data": base64.b64encode(frame_bytes).decode('utf-8'),
                        "size": len(frame_bytes),
                        "format": "jpeg"
                    }
                    
                    # Add to queue (non-blocking)
                    try:
                        self.video_queue.put_nowait(video_data)
                        self.stats["video_frames_captured"] += 1
                    except queue.Full:
                        # Remove oldest frame and add new one
                        try:
                            self.video_queue.get_nowait()
                            self.video_queue.put_nowait(video_data)
                            self.stats["video_frames_captured"] += 1
                        except queue.Empty:
                            pass
                
        
                time.sleep(1/self.frame_rate)
                
            except Exception as e:
                logger.error(f"Video capture loop error: {e}")
                time.sleep(1)
        
        logger.info("Video capture thread stopped")
    
    # ============================================================================
    # AUDIO CAPTURE LOOP - ADD YOUR AUDIO CAPTURE LOGIC HERE
    # ============================================================================
    
    def _audio_capture_loop(self):
        """Continuously capture audio chunks"""
        if not self.enable_audio or not self.audio_capture:
            return
            
        logger.info("Audio capture thread started")
        
        while self.running:
            try:
                # TODO: Implement audio capture logic here
                audio_chunk = self.audio_capture.read_audio_chunk()
                if audio_chunk:
                    timestamp = datetime.now().isoformat()
                    audio_data = {
                        "timestamp": timestamp,
                        "data": base64.b64encode(audio_chunk).decode('utf-8'),
                        "size": len(audio_chunk),
                        "format": "wav"
                    }
                    
                    # Add to queue (non-blocking)
                    try:
                        self.audio_queue.put_nowait(audio_data)
                        self.stats["audio_chunks_captured"] += 1
                    except queue.Full:
                        # Remove oldest chunk and add new one
                        try:
                            self.audio_queue.get_nowait()
                            self.audio_queue.put_nowait(audio_data)
                            self.stats["audio_chunks_captured"] += 1
                        except queue.Empty:
                            pass
                
            except Exception as e:
                logger.error(f"Audio capture loop error: {e}")
                time.sleep(0.1)
        
        logger.info("Audio capture thread stopped")
    
    # ============================================================================
    # END AUDIO CAPTURE LOOP
    # ============================================================================
    
    def _save_data_loop(self):
        """Periodically save accumulated data"""
        logger.info("Data save thread started")
        
        while self.running:
            try:
                time.sleep(self.save_interval)
                
                if self.running:
                    self._save_current_data()
                    
            except Exception as e:
                logger.error(f"Save loop error: {e}")
                time.sleep(1)
        
        logger.info("Data save thread stopped")
    
    def _save_current_data(self):
        """Save all accumulated data to files"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Collect video data from queue
            video_frames = []
            while not self.video_queue.empty():
                try:
                    frame = self.video_queue.get_nowait()
                    video_frames.append(frame)
                except queue.Empty:
                    break
            
            # Collect audio data from queue (if audio is enabled)
            audio_chunks = []
            if self.enable_audio and self.audio_queue:
                while not self.audio_queue.empty():
                    try:
                        chunk = self.audio_queue.get_nowait()
                        audio_chunks.append(chunk)
                    except queue.Empty:
                        break
            
            # Save data if we have any
            if video_frames or audio_chunks:
                if video_frames:
                    self._save_video_data(video_frames, timestamp)
                if audio_chunks:
                    self._save_audio_data(audio_chunks, timestamp)
                    
                # Save metadata
                self._save_metadata(timestamp, len(video_frames), len(audio_chunks))
                
                self.stats["files_saved"] += 1
                self.stats["last_save_time"] = timestamp
                
                logger.info(f"Saved {len(video_frames)} video frames, {len(audio_chunks)} audio chunks")
            else:
                logger.debug("No data to save")
            
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def _save_video_data(self, video_frames, timestamp):
        """Save video frames to files"""
        try:
            # Save as JSON metadata file
            video_file = self.session_folder / "video" / f"video_{timestamp}.json"
            
            with open(video_file, 'w') as f:
                json.dump({
                    "timestamp": timestamp,
                    "frames": video_frames,
                    "frame_count": len(video_frames),
                    "session_folder": str(self.session_folder)
                }, f, indent=2)
            
            # Save individual frames as JPEG files
            frames_dir = self.session_folder / "video" / f"frames_{timestamp}"
            frames_dir.mkdir(exist_ok=True)
            
            for i, frame in enumerate(video_frames):
                frame_file = frames_dir / f"frame_{i:04d}.jpg"
                with open(frame_file, 'wb') as f:
                    f.write(base64.b64decode(frame["data"]))
                    
            logger.debug(f"Saved {len(video_frames)} frames to {frames_dir}")
                    
        except Exception as e:
            logger.error(f"Error saving video data: {e}")
    
    # ============================================================================
    # AUDIO SAVE METHOD - ADD YOUR AUDIO SAVE LOGIC HERE
    # ============================================================================
    
    def _save_audio_data(self, audio_chunks, timestamp):
        """Save audio chunks to files"""
        try:
            # TODO: Implement audio saving logic here
            
            # Save as JSON metadata file
            audio_file = self.session_folder / "audio" / f"audio_{timestamp}.json"
            
            with open(audio_file, 'w') as f:
                json.dump({
                    "timestamp": timestamp,
                    "chunks": audio_chunks,
                    "chunk_count": len(audio_chunks),
                    "session_folder": str(self.session_folder)
                }, f, indent=2)
            
            # TODO: Save individual audio chunks as WAV files
            # Example:
            # wav_file = self.session_folder / "audio" / f"audio_{timestamp}.wav"
            # with open(wav_file, 'wb') as f:
            #     for chunk in audio_chunks:
            #         f.write(base64.b64decode(chunk["data"]))
                    
            logger.debug(f"Saved {len(audio_chunks)} audio chunks")
                    
        except Exception as e:
            logger.error(f"Error saving audio data: {e}")
    
    # ============================================================================
    # END AUDIO SAVE METHOD
    # ============================================================================
    
    def _save_metadata(self, timestamp, video_count, audio_count):
        """Save session metadata"""
        try:
            metadata = {
                "session_info": {
                    "start_time": self.stats["session_start"].isoformat(),
                    "last_save_time": timestamp,
                    "session_folder": str(self.session_folder)
                },
                "statistics": self.stats.copy(),
                "latest_save": {
                    "timestamp": timestamp,
                    "video_frames": video_count,
                    "audio_chunks": audio_count
                },
                "system_info": {
                    "save_interval": self.save_interval,
                    "quality": self.quality,
                    "audio_enabled": self.enable_audio,
                    "video_queue_size": self.video_queue.qsize(),
                    "audio_queue_size": self.audio_queue.qsize() if self.enable_audio else 0,
                    "frame_rate": self.frame_rate,
                    "audio_sample_rate": self.audio_sample_rate,
                    "audio_chunk_size": self.audio_chunk_size
                }
            }
            
            # Save metadata file
            metadata_file = self.session_folder / "metadata" / f"metadata_{timestamp}.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")
    
    def start(self):
        """Start the data logger"""
        logger.info("Starting data logger...")
        
        # Start video capture
        self.video_capture.start_capture()
        
        # Start audio capture (if enabled)
        if self.enable_audio and self.audio_capture:
            self.audio_capture.start_capture()
        
        # Set running flag
        self.running = True
        
        # Start threads
        self.video_thread = threading.Thread(target=self._video_capture_loop, daemon=True)
        self.save_thread = threading.Thread(target=self._save_data_loop, daemon=True)
        
        # Start audio thread (if audio is enabled)
        if self.enable_audio:
            self.audio_thread = threading.Thread(target=self._audio_capture_loop, daemon=True)
            self.audio_thread.start()
        
        self.video_thread.start()
        self.save_thread.start()
        
        logger.info("Data logger started successfully")

        logger.info(f"Video: {self.frame_rate} FPS, Audio: {'Enabled' if self.enable_audio else 'Disabled'}")
        logger.info(f"Saving every {self.save_interval} seconds")
        logger.info(f"Session folder: {self.session_folder}")
    
    def stop(self):
        """Stop the data logger"""
        logger.info("Stopping data logger...")
        
        # Set running flag to false
        self.running = False
        
        # Stop video capture
        self.video_capture.stop_capture()
        
        # Stop audio capture (if enabled)
        if self.enable_audio and self.audio_capture:
            self.audio_capture.stop_capture()
        
        # Wait for threads to finish
        if self.video_thread and self.video_thread.is_alive():
            self.video_thread.join(timeout=2)
        if self.audio_thread and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=2)
        if self.save_thread and self.save_thread.is_alive():
            self.save_thread.join(timeout=2)
        
        # Save any remaining data
        self._save_current_data()
        
        logger.info("Data logger stopped")
        logger.info(f"Session statistics: {self.stats}")
    
    def get_stats(self):
        """Get current statistics"""
        return self.stats.copy()

def main():
    """Main function to run the data logger"""
    import argparse
    
    parser = argparse.ArgumentParser(description="R25-Tiality Data Logger")
    parser.add_argument("--save-interval", type=float, default=5.0, 
                       help="Time interval between saves in seconds (default: 5.0)")
    parser.add_argument("--base-path", default="/home/pi/data_logs",
                       help="Base path for data storage (default: /home/pi/data_logs)")
    parser.add_argument("--quality", type=int, default=75,
                       help="JPEG quality 1-100 (default: 75)")
    parser.add_argument("--enable-audio", action="store_true",
                       help="Enable audio capture (requires audio implementation)")
    parser.add_argument("--frame-rate", type=int, default=30,
                   help="Video frame rate in FPS (default: 30)")
    parser.add_argument("--audio-sample-rate", type=int, default=44100,
                   help="Audio sample rate in Hz (default: 44100)")
    parser.add_argument("--audio-chunk-size", type=int, default=1024,
                   help="Audio chunk size in samples (default: 1024)")
    parser.add_argument("--loglevel", default="INFO",
                       choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="Logging level (default: INFO)")
    
    args = parser.parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.loglevel))
    
    # Create and start data logger
    logger_instance = DataLogger(
        save_interval=args.save_interval,
        base_path=args.base_path,
        quality=args.quality,
        enable_audio=args.enable_audio,
        frame_rate=args.frame_rate,
        audio_sample_rate=args.audio_sample_rate,
        audio_chunk_size=args.audio_chunk_size
    )
    
    try:
        logger_instance.start()
        
        # Keep running until interrupted
        while True:
            time.sleep(1)
            # Print stats every 30 seconds
            if int(time.time()) % 30 == 0:
                stats = logger_instance.get_stats()
                logger.info(f"Stats - Video Frames: {stats['video_frames_captured']}, "
                           f"Audio Chunks: {stats['audio_chunks_captured']}, "
                           f"Files: {stats['files_saved']}")
                
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        logger_instance.stop()

if __name__ == "__main__":
    main()