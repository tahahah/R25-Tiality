import asyncio
import json
import logging
import time
from typing import Optional

import cv2
import numpy as np
import paho.mqtt.client as mqtt
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCConfiguration
from aiortc.contrib.media import MediaPlayer
from picamera2 import Picamera2

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class CameraVideoTrack(VideoStreamTrack):
    """Video track that captures from camera and streams via WebRTC."""
    
    def __init__(self):
        super().__init__()
        try:
            self.picam = Picamera2()
            # Configure camera for 640x480 at 30fps
            config = self.picam.create_video_configuration(
                main={"size": (640, 480), "format": "RGB888"}
            )
            self.picam.configure(config)
            self.picam.start()
            logging.info("Pi Camera initialized successfully with picamera2")
        except Exception as e:
            logging.warning(f"Failed to initialize Pi Camera: {e}\nTrying again in 2 seconds")
            time.sleep(2)

    async def recv(self):
        """Capture frame from camera and return as WebRTC frame."""
        if self.picam:
            # Using Pi Camera
            try:
                frame = self.picam.capture_array()
                if frame is None:
                    logging.warning("Failed to capture frame from Pi Camera")
                    return None
                # Frame is already in RGB format from picamera2
            except Exception as e:
                logging.warning(f"Error capturing from Pi Camera: {e}")
                return None
        else:
            # Using USB camera
            ret, frame = self.cap.read()
            if not ret:
                logging.warning("Failed to capture frame from USB camera")
                return None
            # Convert BGR to RGB for WebRTC
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Create WebRTC frame with proper timestamp handling
        from av import VideoFrame
        from fractions import Fraction
        
        av_frame = VideoFrame.from_ndarray(frame, format="rgb24")
        
        # Set proper timestamp and time base
        current_time = time.time()
        av_frame.pts = int(current_time * 90000)  # 90kHz is common for video
        av_frame.time_base = Fraction(1, 90000)
        
        return av_frame

    def __del__(self):
        if hasattr(self, 'picam') and self.picam:
            self.picam.stop()
        if hasattr(self, 'cap'):
            self.cap.release()


class WebRTCServer:
    """WebRTC server that uses MQTT for signaling."""
    
    def __init__(self, mqtt_broker="localhost"):
        self.mqtt_broker = mqtt_broker
        self.mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.peer_connections = set()
        self.camera_track = None
        self.loop = None
        
        # MQTT event handlers
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        
    def _on_mqtt_connect(self, client, userdata, flags, rc, properties):
        """Callback when MQTT connects."""
        if rc == 0:
            logging.info("Connected to MQTT broker")
            # Subscribe to WebRTC signaling topics
            client.subscribe("webrtc/offer")
            client.subscribe("webrtc/ice")
        else:
            logging.error(f"Failed to connect to MQTT broker: {rc}")
    
    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT messages for WebRTC signaling."""
        try:
            topic = msg.topic
            data = json.loads(msg.payload.decode())
            
            if topic == "webrtc/offer" and self.loop:
                self.loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._handle_offer(data))
                )
            elif topic == "webrtc/ice" and self.loop:
                self.loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._handle_ice_candidate(data))
                )
                
        except Exception as e:
            logging.error(f"Error handling MQTT message: {e}")
    
    async def _handle_offer(self, offer_data):
        """Handle WebRTC offer from client."""
        try:
            logging.info("Received WebRTC offer from client")
            
            # Create new peer connection with configuration
            configuration = RTCConfiguration(
                iceServers=[]  # Local network only, no STUN/TURN servers needed
            )
            pc = RTCPeerConnection(configuration)
            self.peer_connections.add(pc)
            
            # Add camera track
            if not self.camera_track:
                self.camera_track = CameraVideoTrack()
            pc.addTrack(self.camera_track)
            
            # Handle peer connection state changes
            @pc.on("connectionstatechange")
            async def on_connectionstatechange():
                logging.info(f"Connection state: {pc.connectionState}")
                if pc.connectionState == "closed":
                    self.peer_connections.discard(pc)
            
            # Handle ICE connection state changes
            @pc.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                logging.info(f"ICE connection state: {pc.iceConnectionState}")
            
            # Set remote description (offer)
            logging.info("Setting remote description")
            await pc.setRemoteDescription(
                RTCSessionDescription(
                    sdp=offer_data["sdp"],
                    type=offer_data["type"]
                )
            )
            
            # Create answer
            logging.info("Creating answer")
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            
            # Send answer via MQTT
            answer_data = {
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type
            }
            self.mqtt_client.publish(
                "webrtc/answer",
                json.dumps(answer_data)
            )
            
            logging.info("Sent WebRTC answer")
            
        except Exception as e:
            import traceback
            logging.error(f"Error handling WebRTC offer: {e}")
            logging.error(f"Traceback: {traceback.format_exc()}")
    
    async def _handle_ice_candidate(self, ice_data):
        """Handle ICE candidate from client."""
        # For simplicity, we'll rely on the initial offer/answer exchange
        # In a production setup, you'd need to match candidates to specific peer connections
        pass
    
    async def start(self):
        """Start the WebRTC server."""
        # Store event loop reference
        self.loop = asyncio.get_running_loop()
        
        # Initialize camera track
        try:
            self.camera_track = CameraVideoTrack()
        except RuntimeError as e:
            logging.error(f"Failed to initialize camera: {e}")
            return
        
        # Connect to MQTT broker
        self.mqtt_client.connect(self.mqtt_broker, 1883, 60)
        self.mqtt_client.loop_start()
        
        logging.info("WebRTC server started, waiting for connections...")
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logging.info("Shutting down WebRTC server...")
        finally:
            # Cleanup
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            
            # Close all peer connections
            for pc in self.peer_connections:
                await pc.close()
            
            if self.camera_track:
                del self.camera_track


async def main():
    """Main function to start the WebRTC server."""
    server = WebRTCServer()
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())