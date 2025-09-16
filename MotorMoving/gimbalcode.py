#!/usr/bin/env python3
"""
3-Axis Gimbal Controller for Raspberry Pi
Uses ServoClass.py for motor control
Controls X-axis (left/right) and Y-axis (up/down) using pigpio for better performance
Controls C-axis (crane) using RPi.GPIO
"""
import sys
import os
from ServoClass import Servo
from time import sleep

# Import config from same directory
from config import GIMBAL_PIN_X, GIMBAL_PIN_Y, GIMBAL_PIN_C

class GimbalController:
    def __init__(self, x_pin=GIMBAL_PIN_X, y_pin=GIMBAL_PIN_Y, c_pin=GIMBAL_PIN_C):
        """
        Initialize 3-axis gimbal controller
        
        Args:
            x_pin (int): GPIO pin for X-axis servo (left/right) - uses pigpio
            y_pin (int): GPIO pin for Y-axis servo (up/down) - uses pigpio
            c_pin (int): GPIO pin for crane servo (up/down) - uses RPi.GPIO
        """
        # Initialize servos with different libraries
        self.x_servo = Servo(x_pin, use_pigpio=True)  # X-axis (left/right) - pigpio
        self.y_servo = Servo(y_pin, use_pigpio=True)  # Y-axis (up/down) - pigpio
        self.c_servo = Servo(c_pin, use_pigpio=False) # Crane servo (up/down) - RPi.GPIO
        self.center_gimbal() #automatic centering
        
    def x_left(self, degrees=10):
        """
        Move X-axis left (negative direction)
        
        Args:
            degrees (int): How many degrees to move left
        """
        current_angle = self.x_servo.get_current_angle()
        new_angle = max(0, current_angle - degrees)
        print(f"X-LEFT: Current={current_angle}, Moving by {degrees}, New={new_angle}")
        self.x_servo.move(new_angle)
        
    def x_right(self, degrees=10):
        """
        Move X-axis right (positive direction)
        
        Args:
            degrees (int): How many degrees to move right
        """
        current_angle = self.x_servo.get_current_angle()
        new_angle = min(180, current_angle + degrees)
        print(f"X-RIGHT: Current={current_angle}, Moving by {degrees}, New={new_angle}")
        self.x_servo.move(new_angle)
        
    def y_up(self, degrees=10):
        """
        Move Y-axis up (positive direction)
        
        Args:
            degrees (int): How many degrees to move up
        """
        current_angle = self.y_servo.get_current_angle()
        new_angle = min(180, current_angle + degrees)
        print(f"Y-UP: Current={current_angle}, Moving by {degrees}, New={new_angle}")
        self.y_servo.move(new_angle)
        
    def y_down(self, degrees=10):
        """
        Move Y-axis down (negative direction)
        
        Args:
            degrees (int): How many degrees to move down
        """
        current_angle = self.y_servo.get_current_angle()
        new_angle = max(0, current_angle - degrees)
        print(f"Y-DOWN: Current={current_angle}, Moving by {degrees}, New={new_angle}")
        self.y_servo.move(new_angle)

    def c_up(self, degrees=10):
        """
        Move Crane up (positive direction)
        
        Args:
            degrees (int): How many degrees to move up
        """
        current_angle = self.c_servo.get_current_angle()
        new_angle = min(180, current_angle + degrees)
        print(f"C-UP: Current={current_angle}, Moving by {degrees}, New={new_angle}")
        self.c_servo.move(new_angle)
        
    def c_down(self, degrees=10):
        """
        Move Crane down (negative direction)
        
        Args:
            degrees (int): How many degrees to move down
        """
        current_angle = self.c_servo.get_current_angle()
        new_angle = max(0, current_angle - degrees)
        print(f"C-DOWN: Current={current_angle}, Moving by {degrees}, New={new_angle}")
        self.c_servo.move(new_angle)


        
    def set_x_angle(self, angle):
        """
        Set X-axis to specific angle (0-180)
        
        Args:
            angle (int): Target angle for X-axis
        """
        self.x_servo.move(angle)
        
    def set_y_angle(self, angle):
        """
        Set Y-axis to specific angle (0-180)
        
        Args:
            angle (int): Target angle for Y-axis
        """
        self.y_servo.move(angle)


    def set_c_angle(self, angle):
        """
        Set Crane to specific angle (0-180)
        Args:
            angle (int): Target angle for Crane
        """
        self.c_servo.move(angle)
        
    def center_gimbal(self):
        """Center all axes at 90 degrees"""
        print("Centering gimbal to 90 degrees")
        self.x_servo.move(90)  # Center X-axis (pigpio)
        sleep(0.1)  # Small delay to reduce jitter
        self.y_servo.move(90)  # Center Y-axis (pigpio)
        sleep(0.1)  # Small delay to reduce jitter
        self.c_servo.move(90)  # Center Crane (RPi.GPIO)
        sleep(0.1)  # Small delay to reduce jitter
        
    def get_position(self):
        """Get current X and Y, and C positions"""
        return {
            'x': self.x_servo.get_current_angle(),
            'y': self.y_servo.get_current_angle(),
            'c': self.c_servo.get_current_angle()
        }
        
    def cleanup(self):
        """Clean up all servos"""
        self.x_servo.stop()  # pigpio servo
        self.y_servo.stop()  # pigpio servo
        self.c_servo.stop()  # RPi.GPIO servo
        # Clean up pigpio instances
        from ServoClass import Servo
        Servo.cleanup_all()



