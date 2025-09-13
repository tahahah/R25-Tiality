import asyncio
import json
import logging
import threading
from typing import Optional

import cv2
import numpy as np
import paho.mqtt.client as mqtt
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Configuration - change this to your Pi's IP address
PI_IP_ADDRESS = "10.1.1.228"  # Replace with your Pi's actual IP


class WebRTCClient:
    """WebRTC client that displays video stream using OpenCV."""
    
    def __init__(self, pi_ip: str):
        self.pi_ip = pi_ip
        self.mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.peer_connection: Optional[RTCPeerConnection] = None
        self.connected = False
        self.frame_queue = asyncio.Queue(maxsize=5)
        self.loop = None
        self.pending_messages = asyncio.Queue()
        
        # MQTT event handlers
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        
    def _on_mqtt_connect(self, client, userdata, flags, rc, properties):
        """Callback when MQTT connects."""
        if rc == 0:
            logging.info("Connected to MQTT broker")
            # Subscribe to WebRTC answer topic
            client.subscribe("webrtc/answer")
            # Queue the initiation task
            if self.loop:
                self.loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._initiate_webrtc())
                )
        else:
            logging.error(f"Failed to connect to MQTT broker: {rc}")
    
    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        try:
            if msg.topic == "webrtc/answer":
                answer_data = json.loads(msg.payload.decode())
                # Queue the message handling
                if self.loop:
                    self.loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(self._handle_answer(answer_data))
                    )
        except Exception as e:
            logging.error(f"Error handling MQTT message: {e}")
    
    async def _initiate_webrtc(self):
        """Initiate WebRTC connection by sending offer."""
        try:
            logging.info("Initiating WebRTC connection")
            
            # Create peer connection with configuration
            configuration = RTCConfiguration(
                iceServers=[]  # Local network only, no STUN/TURN servers needed
            )
            self.peer_connection = RTCPeerConnection(configuration)
            
            # Add a transceiver to receive video (receive-only)
            from aiortc import RTCRtpTransceiver
            self.peer_connection.addTransceiver("video", direction="recvonly")
            
            # Handle incoming video tracks
            @self.peer_connection.on("track")
            async def on_track(track):
                logging.info(f"Received track: {track.kind}")
                if track.kind == "video":
                    asyncio.create_task(self._process_video_track(track))
            
            @self.peer_connection.on("connectionstatechange")
            async def on_connectionstatechange():
                logging.info(f"Connection state: {self.peer_connection.connectionState}")
                if self.peer_connection.connectionState == "connected":
                    self.connected = True
                elif self.peer_connection.connectionState in ["failed", "closed"]:
                    self.connected = False
            
            @self.peer_connection.on("iceconnectionstatechange")
            async def on_iceconnectionstatechange():
                logging.info(f"ICE connection state: {self.peer_connection.iceConnectionState}")
            
            # Create offer
            logging.info("Creating WebRTC offer")
            offer = await self.peer_connection.createOffer()
            await self.peer_connection.setLocalDescription(offer)
            
            # Send offer via MQTT
            offer_data = {
                "sdp": self.peer_connection.localDescription.sdp,
                "type": self.peer_connection.localDescription.type
            }
            self.mqtt_client.publish("webrtc/offer", json.dumps(offer_data))
            logging.info("Sent WebRTC offer")
            
        except Exception as e:
            import traceback
            logging.error(f"Error initiating WebRTC: {e}")
            logging.error(f"Traceback: {traceback.format_exc()}")
    
    async def _handle_answer(self, answer_data):
        """Handle WebRTC answer from server."""
        try:
            logging.info("Received WebRTC answer from server")
            if self.peer_connection:
                await self.peer_connection.setRemoteDescription(
                    RTCSessionDescription(
                        sdp=answer_data["sdp"],
                        type=answer_data["type"]
                    )
                )
                logging.info("Set remote description from answer")
        except Exception as e:
            import traceback
            logging.error(f"Error handling WebRTC answer: {e}")
            logging.error(f"Traceback: {traceback.format_exc()}")
    
    async def _process_video_track(self, track):
        """Process incoming video frames from WebRTC track."""
        try:
            while True:
                frame = await track.recv()
                if frame:
                    # Convert frame to numpy array for OpenCV
                    img = frame.to_ndarray(format="bgr24")
                    
                    # Add frame to queue (non-blocking, drop old frames if queue is full)
                    try:
                        self.frame_queue.put_nowait(img)
                    except asyncio.QueueFull:
                        # Remove oldest frame and add new one
                        try:
                            self.frame_queue.get_nowait()
                            self.frame_queue.put_nowait(img)
                        except asyncio.QueueEmpty:
                            pass
                            
        except Exception as e:
            logging.error(f"Error processing video track: {e}")
    
    async def display_video(self):
        """Display video frames using OpenCV."""
        logging.info("Starting video display (press 'q' to quit)")
        
        while True:
            try:
                # Get frame from queue with timeout
                frame = await asyncio.wait_for(self.frame_queue.get(), timeout=1.0)
                
                # Display frame
                cv2.imshow("Pi Camera Stream (WebRTC)", frame)
                
                # Check for quit key
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    logging.info("'q' pressed, stopping client")
                    break
                    
            except asyncio.TimeoutError:
                # No frame received, continue
                pass
            except Exception as e:
                logging.error(f"Error displaying video: {e}")
                break
    
    async def start(self):
        """Start the WebRTC client."""
        # Store event loop reference
        self.loop = asyncio.get_running_loop()
        
        # Connect to MQTT broker on Pi
        try:
            self.mqtt_client.connect(self.pi_ip, 1883, 60)
            self.mqtt_client.loop_start()
            
            # Start video display task
            await self.display_video()
            
        except Exception as e:
            logging.error(f"Error starting client: {e}")
        finally:
            # Cleanup
            cv2.destroyAllWindows()
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            
            if self.peer_connection:
                await self.peer_connection.close()
            
            logging.info("Client stopped and cleaned up")


async def main():
    """Main function to start the WebRTC client."""
    client = WebRTCClient(PI_IP_ADDRESS)
    await client.start()


if __name__ == "__main__":
    logging.info(f"Starting WebRTC client, connecting to Pi at {PI_IP_ADDRESS}")
    logging.info("Make sure the Pi is running the WebRTC server and MQTT broker")
    asyncio.run(main())