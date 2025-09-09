"""
GUI Configuration Module

Contains the core configuration classes and enums for the Wildlife Explorer GUI.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Tuple

class ConnectionStatus(Enum):
    """Connection status enumeration."""
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"


class ArmState(Enum):
    """Arm position state enumeration."""
    RAISED = "RAISED"    # When raised, arrow keys control gimbal
    LOWERED = "LOWERED"  # When lowered, arrow keys control car


class GimbalMode(Enum):
    """Gimbal control mode."""
    CAR_CONTROL = "CAR_CONTROL"      # Arrow keys move car
    GIMBAL_CONTROL = "GIMBAL_CONTROL" # Arrow keys move gimbal


@dataclass
class Colour:
    """Colour constants for the GUI."""
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    GREEN = (0, 255, 0)
    RED = (255, 0, 0)
    BLUE = (0, 0, 255)
    YELLOW = (255, 255, 0)
    BEIGE = (222, 196, 160)


@dataclass
class GuiConfig:
    """Configuration constants for the GUI."""
    SCREEN_WIDTH: int = 1280
    SCREEN_HEIGHT: int = 720
    CAMERA_WIDTH: int = 350
    CAMERA_HEIGHT: int = 240
    FPS: int = 60
    NUM_CAMERAS: int = 2
