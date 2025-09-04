#!/usr/bin/env python3
"""
Simple Gimbal Remote Control Client
Run this on your computer to control the gimbal on your Raspberry Pi
"""
import paho.mqtt.client as mqtt
import json
import time
from pynput import keyboard

class GimbalRemote:
    def __init__(self, pi_ip="127.0.1.1"): 
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Connect to Pi's MQTT broker
        print(f"Connecting to Raspberry Pi at {pi_ip}...")
        self.client.connect(pi_ip, 1883, 60)
        self.client.loop_start()
        
        # Wait for connection
        time.sleep(1)
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"✅ Connected to Pi MQTT broker successfully!")
        else:
            print(f"❌ Failed to connect to MQTT broker (code: {rc})")
        
    def on_message(self, client, userdata, msg):
        if msg.topic == "robot/rx":
            try:
                data = json.loads(msg.payload.decode())
                if data.get("status") == "gimbal":
                    print(f"🎯 Gimbal: {data['action']} - {data.get('degrees', '')}°")
                elif data.get("status") == "error":
                    print(f"❌ Error: {data.get('message', 'Unknown error')}")
            except json.JSONDecodeError:
                print(f"📡 Raw message: {msg.payload.decode()}")
    
    def send_gimbal_command(self, action, degrees=10, **kwargs):
        """Send gimbal command to Pi"""
        command = {
            "type": "gimbal",
            "action": action,
            "degrees": degrees,
            **kwargs
        }
        self.client.publish("robot/tx", json.dumps(command))
        print(f"📤 Sent: {action} ({degrees}°)")
    
    def on_key_press(self, key):
        """Handle keyboard input"""
        try:
            if key == keyboard.Key.left:
                self.send_gimbal_command("x_left")
            elif key == keyboard.Key.right:
                self.send_gimbal_command("x_right")
            elif key == keyboard.Key.up:
                self.send_gimbal_command("y_up")
            elif key == keyboard.Key.down:
                self.send_gimbal_command("y_down")
            elif key == keyboard.Key.space:
                self.send_gimbal_command("center")
            elif key == keyboard.Key.esc:
                print("🛑 Exiting...")
                return False
            elif hasattr(key, 'char') and key.char:
                # Number keys for custom degrees
                if key.char in '123456789':
                    degrees = int(key.char) * 5  # 5, 10, 15, 20, 25, 30, 35, 40, 45 degrees
                    print(f"🔢 Set movement to {degrees}°")
                    # Store for next movement
                    self.last_degrees = degrees
                elif key.char == '0':
                    self.send_gimbal_command("position")
        except AttributeError:
            pass
    
    def run(self):
        """Start keyboard listener"""
        print("\n🎮 Gimbal Remote Control")
        print("=" * 40)
        print("Arrow keys: Move gimbal")
        print("Space: Center gimbal")
        print("1-9: Set movement degrees (5-45°)")
        print("0: Get current position")
        print("ESC: Exit")
        print("=" * 40)
        
        # Initialize default movement degrees
        self.last_degrees = 10
        
        with keyboard.Listener(on_press=self.on_key_press) as listener:
            listener.join()
        
        self.client.loop_stop()
        self.client.disconnect()

if __name__ == "__main__":
    # ⚠️ IMPORTANT: Change this to your Raspberry Pi's IP address!
    PI_IP = "192.168.1.100"  # Change this!
    
    print("🔧 Gimbal Remote Control Setup")
    print("Make sure to change the PI_IP variable to your Pi's actual IP address!")
    
    try:
        remote = GimbalRemote(PI_IP)
        remote.run()
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure:")
        print("   1. Your Pi is running the updated mqtt_to_pwm.py")
        print("   2. You've changed PI_IP to your Pi's actual IP address")
        print("   3. Your Pi and computer are on the same network")
