import logging
import json
import paho.mqtt.client as mqtt
from queue import Queue, Empty
from threading import Event
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioMQTTPublisher:
    """Publishes encoded audio packets via MQTT."""
    
    def __init__(
        self,
        broker_host: str,
        broker_port: int = 1883,
        audio_topic: str = "robot/audio/tx",
        qos: int = 0  # QoS 0 for low latency audio streaming
    ):
        """
        Initialize MQTT audio publisher.
        
        Args:
            broker_host: MQTT broker hostname or IP
            broker_port: MQTT broker port (default 1883)
            audio_topic: Topic for publishing audio packets
            qos: Quality of Service level (0=at most once, 1=at least once, 2=exactly once)
        """
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.audio_topic = audio_topic
        self.qos = qos
        
        # MQTT client
        self.client: Optional[mqtt.Client] = None
        self.connected = Event()
        self.connected.clear()
        
        # Statistics
        self.packets_sent = 0
        self.bytes_sent = 0
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback when client connects to broker."""
        if rc == 0:
            logger.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}")
            self.connected.set()
        else:
            logger.error(f"Failed to connect to MQTT broker (rc={rc})")
            self.connected.clear()
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback when client disconnects from broker."""
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker (rc={rc})")
        self.connected.clear()
    
    def connect(self) -> bool:
        """
        Connect to MQTT broker.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client = mqtt.Client()
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            
            logger.info(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}...")
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()
            
            # Wait up to 5 seconds for connection
            if self.connected.wait(timeout=5.0):
                logger.info("MQTT audio publisher ready")
                return True
            else:
                logger.error("Connection timeout")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False
    
    def publish_audio_packet(self, header: dict, data: bytes) -> bool:
        """
        Publish an encoded audio packet.
        
        Args:
            header: Packet header dict with timestamp, sequence_number, packet_length, algorithm_delay
            data: Encoded audio data bytes
            
        Returns:
            True if published successfully, False otherwise
        """
        if not self.connected.is_set():
            logger.warning("Not connected to MQTT broker")
            return False
        
        try:
            # Create packet with header and data
            # Format: JSON header followed by raw binary data
            header_json = json.dumps(header).encode('utf-8')
            header_length = len(header_json)
            
            # Pack: [4 bytes header length][header json][audio data]
            packet = header_length.to_bytes(4, byteorder='big') + header_json + data
            
            # Publish
            result = self.client.publish(self.audio_topic, payload=packet, qos=self.qos)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.packets_sent += 1
                self.bytes_sent += len(packet)
                return True
            else:
                logger.error(f"Failed to publish audio packet (rc={result.rc})")
                return False
                
        except Exception as e:
            logger.error(f"Error publishing audio packet: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker."""
        if self.client:
            logger.info(f"Disconnecting from MQTT broker. Stats: {self.packets_sent} packets, {self.bytes_sent} bytes sent")
            self.client.loop_stop()
            self.client.disconnect()
            self.connected.clear()
    
    def get_stats(self) -> dict:
        """Get publisher statistics."""
        return {
            "connected": self.connected.is_set(),
            "packets_sent": self.packets_sent,
            "bytes_sent": self.bytes_sent
        }
