import logging
import json
import threading
import queue
import numpy as np
from typing import Optional, Callable
import paho.mqtt.client as mqtt
import pygame

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioMQTTSubscriber:
    """Subscribes to MQTT audio stream and plays back via pygame."""
    
    def __init__(
        self,
        broker_host: str,
        broker_port: int = 1883,
        audio_topic: str = "robot/audio/tx",
        sample_rate: int = 48000,
        channels: int = 1,
        buffer_size: int = 10  # Number of packets to buffer
    ):
        """
        Initialize MQTT audio subscriber.
        
        Args:
            broker_host: MQTT broker hostname or IP
            broker_port: MQTT broker port (default 1883)
            audio_topic: Topic for subscribing to audio packets
            sample_rate: Audio sample rate (default 48000 Hz)
            channels: Number of audio channels (default 1)
            buffer_size: Number of packets to buffer before playback
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.audio_topic = audio_topic
        self.sample_rate = sample_rate
        self.channels = channels
        self.buffer_size = buffer_size
        
        # MQTT client
        self.client: Optional[mqtt.Client] = None
        self.connected = threading.Event()
        self.connected.clear()
        
        # Audio packet queue
        self.packet_queue = queue.Queue(maxsize=buffer_size)
        
        # Decoder (lazy import to avoid dependency issues)
        self.decoder = None
        
        # Playback thread
        self.playback_thread: Optional[threading.Thread] = None
        self.shutdown_event = threading.Event()
        self.shutdown_event.clear()
        
        # Statistics
        self.packets_received = 0
        self.packets_dropped = 0
        self.bytes_received = 0
        
        # Initialize pygame mixer for audio playback
        try:
            pygame.mixer.init(frequency=sample_rate, channels=channels, buffer=960)  # 20ms buffer
            logger.info("Pygame mixer initialized for audio playback")
        except Exception as e:
            logger.error(f"Failed to initialize pygame mixer: {e}")
    
    def _init_decoder(self):
        """Lazy initialize the Opus decoder."""
        if self.decoder is None:
            try:
                # Import PyOgg locally
                import sys
                import os
                # Add ALSA_Capture_Stream to path if needed
                parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                alsa_path = os.path.join(parent_dir, 'ALSA_Capture_Stream')
                if alsa_path not in sys.path:
                    sys.path.insert(0, alsa_path)
                
                from decoder_object import DecoderObject
                
                # Create decoder with settings
                import settings
                settings.init()
                settings.sample_rate = self.sample_rate
                settings.encoded_channels = self.channels
                
                self.decoder = DecoderObject()
                logger.info("Opus decoder initialized")
            except Exception as e:
                logger.error(f"Failed to initialize decoder: {e}")
                raise
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when client connects to broker."""
        if rc == 0:
            logger.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}")
            client.subscribe(self.audio_topic, qos=0)
            logger.info(f"Subscribed to audio topic: {self.audio_topic}")
            self.connected.set()
        else:
            logger.error(f"Failed to connect to MQTT broker (rc={rc})")
            self.connected.clear()
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when client disconnects from broker."""
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker (rc={rc})")
        self.connected.clear()
    
    def _on_message(self, client, userdata, msg):
        """Callback when audio packet received."""
        try:
            # Parse packet: [4 bytes header length][header json][audio data]
            packet = msg.payload
            header_length = int.from_bytes(packet[0:4], byteorder='big')
            header_json = packet[4:4+header_length].decode('utf-8')
            header = json.loads(header_json)
            audio_data = packet[4+header_length:]
            
            # Update stats
            self.packets_received += 1
            self.bytes_received += len(packet)
            
            # Queue packet for playback
            try:
                self.packet_queue.put_nowait({
                    "header": header,
                    "data": audio_data
                })
            except queue.Full:
                # Drop oldest packet if queue is full
                try:
                    self.packet_queue.get_nowait()
                    self.packet_queue.put_nowait({
                        "header": header,
                        "data": audio_data
                    })
                    self.packets_dropped += 1
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error processing audio packet: {e}")
    
    def _playback_worker(self):
        """Background thread that decodes and plays audio packets."""
        logger.info("Audio playback thread started")
        
        try:
            self._init_decoder()
        except Exception as e:
            logger.error(f"Failed to initialize decoder, playback disabled: {e}")
            return
        
        while not self.shutdown_event.is_set():
            try:
                # Get packet from queue with timeout
                packet = self.packet_queue.get(timeout=0.1)
                
                # Decode audio
                decoded_audio = self.decoder.decode(packet["data"])
                
                # Convert to numpy array for pygame
                audio_array = np.frombuffer(decoded_audio, dtype=np.int16)
                
                # Reshape for multi-channel if needed
                if self.channels > 1:
                    audio_array = audio_array.reshape(-1, self.channels)
                
                # Play audio using pygame
                # Note: This is non-blocking, packets will queue in pygame's buffer
                sound = pygame.sndarray.make_sound(audio_array)
                sound.play()
                
            except queue.Empty:
                # No packet available, continue
                continue
            except Exception as e:
                logger.error(f"Error in playback worker: {e}")
                continue
        
        logger.info("Audio playback thread stopped")
    
    def connect(self) -> bool:
        """
        Connect to MQTT broker and start audio playback.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client = mqtt.Client()
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            logger.info(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}...")
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            
            # Wait up to 5 seconds for connection
            if self.connected.wait(timeout=5.0):
                logger.info("MQTT audio subscriber ready")
                
                # Start playback thread
                self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
                self.playback_thread.start()
                
                return True
            else:
                logger.error("Connection timeout")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker and stop playback."""
        if self.client:
            logger.info(f"Disconnecting from MQTT broker. Stats: {self.packets_received} received, {self.packets_dropped} dropped")
            
            # Stop playback thread
            self.shutdown_event.set()
            if self.playback_thread:
                self.playback_thread.join(timeout=2.0)
            
            # Disconnect MQTT
            self.client.loop_stop()
            self.client.disconnect()
            self.connected.clear()
    
    def get_stats(self) -> dict:
        """Get subscriber statistics."""
        return {
            "connected": self.connected.is_set(),
            "packets_received": self.packets_received,
            "packets_dropped": self.packets_dropped,
            "bytes_received": self.bytes_received,
            "queue_size": self.packet_queue.qsize()
        }
