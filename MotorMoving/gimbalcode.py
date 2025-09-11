#!/usr/bin/env python3
"""
2-Axis Gimbal Controller for Raspberry Pi
Uses ServoClass.py for motor control
Controls X-axis (left/right) and Y-axis (up/down) using SG90 servos
"""
from ServoClass import Servo
from time import sleep

class GimbalController:
    def __init__(self, x_pin=18, y_pin=27, c_pin=22):
        """
        Initialize 3-axis gimbal controller
        
        Args:
            x_pin (int): GPIO pin for X-axis servo (left/right) - default: 18 
            y_pin (int): GPIO pin for Y-axis servo (up/down) - default: 27 
            c_pin (int): GPIO pin for crane servo (up/down) - default: 22
        """
        # Initialize both servos
        self.x_servo = Servo(x_pin)  # X-axis (left/right)
        self.y_servo = Servo(y_pin)  # Y-axis (up/down)
        self.c_servo = Servo(c_pin)  # Crane servo (up/down)
        # Center both servos at startup
        self.center_gimbal()
        
    def x_left(self, degrees=10):
        """
        Move X-axis left (negative direction)
        
        Args:
            degrees (int): How many degrees to move left
        """
        current_angle = self.x_servo.get_current_angle()
        new_angle = max(0, current_angle - degrees)
        self.x_servo.move(new_angle)
        
    def x_right(self, degrees=10):
        """
        Move X-axis right (positive direction)
        
        Args:
            degrees (int): How many degrees to move right
        """
        current_angle = self.x_servo.get_current_angle()
        new_angle = min(180, current_angle + degrees)
        self.x_servo.move(new_angle)
        
    def y_up(self, degrees=10):
        """
        Move Y-axis up (positive direction)
        
        Args:
            degrees (int): How many degrees to move up
        """
        current_angle = self.y_servo.get_current_angle()
        new_angle = min(180, current_angle + degrees)
        self.y_servo.move(new_angle)
        
    def y_down(self, degrees=10):
        """
        Move Y-axis down (negative direction)
        
        Args:
            degrees (int): How many degrees to move down
        """
        current_angle = self.y_servo.get_current_angle()
        new_angle = max(0, current_angle - degrees)
        self.y_servo.move(new_angle)

    def c_up(self, degrees=10):
        """
        Move Crane up (positive direction)
        
        Args:
            degrees (int): How many degrees to move up
        """
        current_angle = self.c_servo.get_current_angle()
        new_angle = min(180, current_angle + degrees)
        self.c_servo.move(new_angle)
        
    def c_down(self, degrees=10):
        """
        Move Crane down (negative direction)
        
        Args:
            degrees (int): How many degrees to move down
        """
        current_angle = self.c_servo.get_current_angle()
        new_angle = max(0, current_angle - degrees)
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
        """Center both X and Y axes"""
        self.x_servo.move(90)  # Center X-axis
        self.y_servo.move(90)  # Center Y-axis
        self.c_servo.move(90)  # Center Crane (Check Actaul angle that we want to  center it at )
        
    def get_position(self):
        """Get current X and Y, and C positions"""
        return {
            'x': self.x_servo.get_current_angle(),
            'y': self.y_servo.get_current_angle(),
            'c': self.c_servo.get_current_angle()
        }
        
    def cleanup(self):
        """Clean up both servos"""
        self.x_servo.stop()
        self.y_servo.stop()
        self.c_servo.stop()



