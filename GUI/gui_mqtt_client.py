import paho.mqtt.client as mqtt
import json
import logging
import threading
import time

logger = logging.getLogger(__name__)

class GuiMqttClient:
    """MQTT Client for GUI to Pi communication"""
    
    def __init__(self, pi_ip: str):
        self.pi_ip = pi_ip
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.connected = False
        self.connection_callback = None
        
    def set_connection_callback(self, callback):
        """Set callback for connection status changes"""
        self.connection_callback = callback
        
    def connect(self):
        """Connect to Pi's MQTT broker"""
        try:
            logger.info(f"Connecting to Pi at {self.pi_ip}...")
            self.client.connect(self.pi_ip, 1883, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Pi: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.connected:
            self.client.loop_stop()
            self.client.disconnect()
    
    def send_gimbal_command(self, action: str, degrees: int = 10):
        """Send gimbal command to Pi"""
        if not self.connected:
            logger.warning("Not connected to Pi")
            return False
            
        command = {
            "type": "gimbal",
            "action": action,
            "degrees": degrees
        }
        
        return self._publish_command(command)
    
    def send_motor_command(self, vx: float = 0, vy: float = 0, omega: float = 0):
        """Send motor movement command to Pi"""
        if not self.connected:
            logger.warning("Not connected to Pi")
            return False
            
        command = {
            "type": "vector",
            "action": "set",
            "vx": vx,
            "vy": vy,
            "omega": omega
        }
        
        return self._publish_command(command)
    
    def send_stop_command(self):
        """Send emergency stop command"""
        if not self.connected:
            logger.warning("Not connected to Pi")
            return False
            
        command = {
            "type": "all",
            "action": "stop"
        }
        
        return self._publish_command(command)
    
    def _publish_command(self, command: dict):
        """Internal method to publish MQTT command"""
        try:
            message = json.dumps(command)
            result = self.client.publish("robot/tx", message)
            logger.info(f"Sent MQTT: {command}")
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"Failed to send command: {e}")
            return False
    
    def on_connect(self, client, userdata, flags, rc):
        """Callback for MQTT connection"""
        if rc == 0:
            self.connected = True
            logger.info("Connected to Pi MQTT broker successfully!")
            client.subscribe("robot/rx")  # Subscribe to responses
            if self.connection_callback:
                self.connection_callback(True)
        else:
            self.connected = False
            logger.error(f"Failed to connect to MQTT broker (code: {rc})")
            if self.connection_callback:
                self.connection_callback(False)
    
    def on_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection"""
        self.connected = False
        logger.warning("Disconnected from Pi MQTT broker")
        if self.connection_callback:
            self.connection_callback(False)
    
    def on_message(self, client, userdata, msg):
        """Handle messages from Pi"""
        try:
            if msg.topic == "robot/rx":
                data = json.loads(msg.payload.decode())
                logger.info(f"Received from Pi: {data}")
                # Handle position updates, status messages, etc.
        except Exception as e:
            logger.error(f"Error processing message: {e}")