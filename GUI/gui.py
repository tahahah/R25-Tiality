import pygame
import sys
import logging
import cv2
import numpy as np
import os
import json
from typing import Callable, Optional, Mapping
from gui_config import ConnectionStatus, ArmState, Colour, GuiConfig, VisionInferenceConfig, AudioInferenceConfig

# Get the parent directory path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

# Now you can import modules from the parent directory
from tiality_server import TialityServerManager
from Inference import InferenceManager

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _decode_video_frame_opencv(frame_bytes: bytes) -> pygame.Surface:
    """
    Decodes a byte array (JPEG) into a Pygame surface using the highly
    optimized OpenCV library. This is the recommended, high-performance method.

    Args:
        frame_bytes: The raw byte string of a single JPEG image.

    Returns:
        A Pygame.Surface object, or None if decoding fails.
    """
    try:
        # 1. Convert the raw byte string to a 1D NumPy array.
        #    This is a very fast, low-level operation.
        np_array = np.frombuffer(frame_bytes, np.uint8)
        
        # 2. Decode the NumPy array into an OpenCV image.
        #    This is the core, high-speed decoding step. The result is in BGR format.
        img_bgr = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        
        img_bgr = cv2.resize(img_bgr, (510, 230), interpolation=cv2.INTER_AREA)

        # 3. Convert the color format from BGR (OpenCV's default) to RGB (Pygame's default).
        # img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        
        # 4. Correct the orientation. OpenCV arrays are (height, width), but
        #    pygame.surfarray.make_surface expects (width, height). We swap the axes.
        # img_rgb = img_rgb.swapaxes(0, 1)

        # 5. Create a Pygame surface directly from the NumPy array.
        #    This is another very fast, low-level operation.
        # frame_surface = pygame.surfarray.make_surface(img_rgb)
        
        return img_bgr
        
    except Exception as e:
        # If any part of the decoding fails (e.g., due to a corrupted frame),
        # print an error and return None so the GUI doesn't crash.
        print(f"Error decoding frame with OpenCV: {e}")
        return None



class ExplorerGUI:
    """
    INITIALISATION:
    Wildlife Explorer RC Car Controller GUI.
    
    Provides a graphical interface for controlling an RC car with dual camera feeds,
    movement controls, and arm manipulation capabilities.
    """

    def __init__(
        self, 
        background_image_path: str, 
        command_callback: Optional[Callable[[str], None]] = None,
        is_robot: bool = True,
        mqtt_broker_host_ip: str = "localhost",
        mqtt_port: int = 1883,
    ):
        """
        Args:
            background_image_path: Path to the background image file
            command_callback: Callback function for handling commands to PI
        """
        # Initialise core components
        pygame.init()
        self.config = GuiConfig()
        self.colours = Colour()
        self.is_robot = is_robot
        
        # Setup display and resources
        self._load_background(background_image_path)
        self._init_display()
        self._init_fonts()
        self._init_camera_layout()
        
        # Setup Server and shared frame queue
        self.server_manager = TialityServerManager(
            grpc_port = 50051, 
            mqtt_port = mqtt_port, 
            mqtt_broker_host_ip = mqtt_broker_host_ip,
            decode_video_func = _decode_video_frame_opencv,
            num_decode_video_workers = 1 # Don't change this for now
            )
        self.server_manager.start_servers()
        
        # Initialise application state
        self._init_state()
        
        # Initialise joystick (if present)
        try:
            pygame.joystick.init()
            self.joystick = None
            if pygame.joystick.get_count() > 0:
                self.joystick = pygame.joystick.Joystick(0)
                if not self.joystick.get_init():
                    self.joystick.init()
                logger.info(f"Joystick initialised: {self.joystick.get_name()} | axes={self.joystick.get_numaxes()}")
            else:
                logger.info("No joystick detected")
        except Exception as e:
            self.joystick = None
            logger.warning(f"Joystick init failed: {e}")
        

        # Setup timing
        self.clock = pygame.time.Clock()
        self.running = True
        
        # Simple gimbal command tracking
        self.last_sent_gimbal_command = None
        
        # Controller mappings (defaults for common Xbox/SDL layout)
        self.RIGHT_STICK_X_AXIS = 2  # Right stick horizontal
        self.RIGHT_STICK_Y_AXIS = 3  # Right stick vertical
        self.BUTTON_LB = 4           # Left bumper
        self.BUTTON_RB = 5           # Right bumper
        
        # Gimbal control via right stick: threshold and dynamic rate/step
        self.GIMBAL_AXIS_THRESHOLD = 0.25
        self.GIMBAL_MIN_DEGREES = 2.0
        self.GIMBAL_MAX_DEGREES = 10.0
        self.GIMBAL_MIN_COOLDOWN_MS = 40
        self.GIMBAL_MAX_COOLDOWN_MS = 220
        self._last_gimbal_axis_send_ms = {"x": 0, "y": 0}
        
        logger.info("Wildlife Explorer GUI initialised successfully")

    # ============================================================================
    # INIT METHODS
    # ============================================================================

    def _load_background(self, image_path: str) -> None:
        self.background = pygame.image.load(image_path)
        logger.info(f"Background image loaded: {image_path}")
        

    def _init_display(self) -> None:
        screen_size = (self.config.SCREEN_WIDTH, self.config.SCREEN_HEIGHT)
        self.screen = pygame.display.set_mode(screen_size)
        pygame.display.set_caption("Wildlife Explorer - RC Car Controller")

    def _init_fonts(self) -> None:
        self.fonts = {
            'small': pygame.font.Font(None, 20),
            'medium': pygame.font.Font(None, 28),
            'large': pygame.font.Font(None, 36)
        }

    def _init_camera_layout(self) -> None:
        # Camera feed positions (left and right)
        self.camera_positions = [
            (35, 255),   # Camera 1 position (left)
            (450, 170),  # Camera 2 position (right)
        ]
        
        self.camera_surfaces = [None] * self.config.NUM_CAMERAS
        self.camera_threads = []
        
        # Status indicator positions for each camera
        self.camera_indicator_positions = [
            (370, self.config.SCREEN_HEIGHT - 500),   # Camera 1 indicator
            (909, self.config.SCREEN_HEIGHT - 500)    # Camera 2 indicator
        ]

    def _init_state(self) -> None:
        """Initialise Explorer Control state variables."""
        # Movement control states
        # Set default keybindings
        if self.is_robot:
            # Robot default: no movement (stop command)
            self.default_keys = {"type": "all", "action": "stop"}
            # Keep movement_keys empty in robot mode; we send commands directly
            self.movement_keys = {}
        else:
            self.default_keys = {}
            self.default_keys["up"] = False
            self.default_keys["down"] = False
            self.default_keys["rotate_left"] = False
            self.default_keys["rotate_right"] = False
            self.default_keys["left"] = False
            self.default_keys["right"] = False
            self.movement_keys = self.default_keys.copy()
        
        # Camera states (all cameras start active)
        self.camera_states = [True] * self.config.NUM_CAMERAS
        
        # Hardware states
        self.arm_state = ArmState.RETRACTED
        self.connection_status = ConnectionStatus.DISCONNECTED
        
        # Model inference states
        self.inference_enabled = False
        self.inference_manager = None
        self._init_inference_manager()

    def _init_inference_manager(self) -> None:
        """Initialize the vision and audio inference manager for model inference."""
        
        self.inference_manager = InferenceManager(
            vision_inference_config = VisionInferenceConfig(),
            audio_inference_config = AudioInferenceConfig(),
            server_manager = self.server_manager
        )

    def _pygame_surface_to_opencv(self, surface: pygame.Surface) -> Optional[np.ndarray]:
        """Convert a pygame surface to OpenCV format for model inference."""
        try:
            # Get the RGB array from the pygame surface
            rgb_array = pygame.surfarray.array3d(surface)
            # Swap axes to get (height, width, channels) format
            rgb_array = rgb_array.swapaxes(0, 1)
            # Convert RGB to BGR for OpenCV
            bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
            return bgr_array
        except Exception as e:
            logger.error(f"Error converting pygame surface to OpenCV: {e}")
            return None

    def _opencv_to_pygame_surface(self, opencv_img: np.ndarray) -> Optional[pygame.Surface]:
        """Convert an OpenCV image to a pygame surface for display."""
        try:
            # Convert BGR to RGB
            rgb_img = cv2.cvtColor(opencv_img, cv2.COLOR_BGR2RGB)
            # Swap axes to get (width, height, channels) format for pygame
            rgb_img = rgb_img.swapaxes(0, 1)
            # Create pygame surface from the RGB array
            surface = pygame.surfarray.make_surface(rgb_img)
            return surface
        except Exception as e:
            logger.error(f"Error converting OpenCV image to pygame surface: {e}")
            return None

    # ============================================================================
    # COMMAND AND STATUS METHODS
    # ============================================================================

    def send_command(self, command: str) -> None:
        """
        Send command to Pi via callback function 
        """
        try:
            self.server_manager.send_command(command)
            logger.debug(f"Command sent: {command}")
        except Exception as e:
            logger.error(f"Command callback error: {e}")
    
    def send_gimbal_command(self, action: str, degrees: float = 10.0) -> None:
        """
        Send gimbal command to Pi via MQTT - immediate response
        
        Args:
            action: The gimbal action (x_left, x_right, y_up, y_down, c_up, c_down, center)
            degrees: How many degrees to move (default 10.0)
        """
        cmd = {
            "type": "gimbal",
            "action": action,
            "degrees": degrees
        }
        
        try:
            command_json = json.dumps(cmd)
            logger.info(f"Sending gimbal command: {cmd}")
            self.send_command(command_json)
            logger.info(f"Gimbal command queued successfully: {cmd}")
        except Exception as e:
            logger.error(f"Failed to send gimbal command: {e}")
            raise

    def set_connection_status(self, status: ConnectionStatus) -> None:
        """TODO: Set connection for GUI idk if you want to open a socket and send over on a port"""
        self.connection_status = status

    def start_camera_streams(self) -> None:
        """TODO: Implement camera initialisation and streaming (Vinay)"""
        pass

    # ============================================================================
    # MOVEMENT HANDLING
    # ============================================================================

    def _get_active_movements(self) -> Mapping[str, object]:
        """
        Get list of currently active movement directions.
        """
        # return [
        #     direction.upper() 
        #     for direction, is_active in self.movement_keys.items() 
        #     if is_active
        # ]
        
        return self.movement_keys

    def handle_movement(self) -> None:
        """Process current movement key states and send commands."""
        if self.is_robot:
            # Robot mode publishes movement in _handle_movement_keys; avoid duplicate sends
            return
        active_movements = self._get_active_movements()
        
        if active_movements:
            # Build movement command from active directions
            
            json_string = json.dumps(active_movements)
            self.send_command(json_string)

    # ============================================================================
    # DRAWING METHODS
    # ============================================================================
    def _collect_recent_frame(self):
        """
        Collect frames from server manager to display, currently only works for first display.
        Optionally processes frames through model inference if enabled.
        """
        self.camera_surfaces[0] = self.inference_manager.get_vision_inference_frame()
        
        

    def _draw_cameras(self) -> None:
        """Draw camera feeds and their status indicators."""
        for camera_index in range(self.config.NUM_CAMERAS):
            self._draw_single_camera(camera_index)
            self._draw_camera_status(camera_index)

    def _draw_single_camera(self, camera_index: int) -> None:
        camera_surface = self.camera_surfaces[camera_index]
        if camera_surface:
            camera_position = self.camera_positions[camera_index]
            self.screen.blit(camera_surface, camera_position)

    def _draw_camera_status(self, camera_index: int) -> None:
        indicator_position = self.camera_indicator_positions[camera_index]
        is_camera_active = self.camera_states[camera_index]
        indicator_colour = self.colours.GREEN if is_camera_active else self.colours.RED
        
        # Draw filled circle with white border
        pygame.draw.circle(self.screen, indicator_colour, indicator_position, 8)
        pygame.draw.circle(self.screen, self.colours.WHITE, indicator_position, 8, 3)

    def _draw_movement_status(self) -> None:
        """Draw current movement status overlay."""
        active_movements = self._get_active_movements()
        
        if not active_movements:
            return
        
        # Create movement status text
        movement_text = " + ".join(active_movements)
        status_text = f"MOVING: {movement_text}"
        
        # Render text and calculate position
        text_surface = self.fonts['large'].render(status_text, True, self.colours.WHITE)
        text_rect = text_surface.get_rect(center=(self.config.SCREEN_WIDTH // 2, 80))
        
        # Draw semi-transparent background
        background_rect = text_rect.inflate(40, 20)
        background_overlay = pygame.Surface(background_rect.size, pygame.SRCALPHA)
        background_overlay.fill((0, 100, 0, 180))  # Semi-transparent green
        
        # Blit background and text
        self.screen.blit(background_overlay, background_rect)
        self.screen.blit(text_surface, text_rect)

    def _draw_status_info(self) -> None:
        """Draw connection, arm, and inference status information."""
        status_y_position = self.config.SCREEN_HEIGHT - 50
        
        self._draw_connection_status(status_y_position)
        self._draw_arm_status(status_y_position - 25)
        self._draw_inference_status(status_y_position - 50)

    def _draw_connection_status(self, y_position: int) -> None:
        is_connected = (self.connection_status == ConnectionStatus.CONNECTED)
        status_colour = self.colours.GREEN if is_connected else self.colours.RED
        
        status_text = f"Status: {self.connection_status.value}"
        status_surface = self.fonts['medium'].render(status_text, True, status_colour)
        
        self.screen.blit(status_surface, (30, y_position))

    def _draw_arm_status(self, y_position: int) -> None:
        is_extended = (self.arm_state == ArmState.EXTENDED)
        arm_colour = self.colours.GREEN if is_extended else self.colours.BLUE
        
        arm_text = f"Arm: {self.arm_state.value}"
        arm_surface = self.fonts['medium'].render(arm_text, True, arm_colour)
        
        self.screen.blit(arm_surface, (30, y_position))

    def _draw_inference_status(self, y_position: int) -> None:
        """Draw model inference status indicator."""
        # Determine status color and text
        if self.inference_manager is None:
            inference_colour = self.colours.RED
            inference_text = "Inference: NOT AVAILABLE"
        elif self.inference_manager.vision_inference_on.is_set():
            inference_colour = self.colours.GREEN
            inference_text = "Inference: ON"
        else:
            inference_colour = self.colours.YELLOW
            inference_text = "Inference: OFF"
        
        inference_surface = self.fonts['medium'].render(inference_text, True, inference_colour)
        self.screen.blit(inference_surface, (30, y_position))

    def draw_overlays(self) -> None:
        """Draw all interactive overlays on top of the background image."""
        self._draw_cameras()
        self._draw_movement_status()
        self._draw_status_info()


    # ============================================================================
    # HELP SYSTEM
    # ============================================================================

    def show_help(self) -> None:
        """Display help overlay and wait for user input."""
        self._draw_help_overlay()
        self._draw_help_text()
        pygame.display.flip()
        self._wait_for_keypress()

    def _draw_help_overlay(self) -> None:
        """Draw semi-transparent background for help text."""
        screen_size = (self.config.SCREEN_WIDTH, self.config.SCREEN_HEIGHT)
        overlay = pygame.Surface(screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))  # Semi-transparent black
        self.screen.blit(overlay, (0, 0))

    def _draw_help_text(self) -> None:
        """Draw help text content."""
        help_content = [
            "WILDLIFE EXPLORER - RC Buggy",
            "",
            "KEYBOARD CONTROLS:",
            "  WASD - Move car",
            "  Q/E - Rotate Car",
            "  Arrow Keys - Control gimbal X/Y axes",
            "  X/C - Control crane servo up/down",
            "  Space - Emergency stop",
            "  P - Toggle model inference ON/OFF",
            "  TODO: 1, 2 - Toggle cameras",
            "  H - Show/hide this help",
            "  ESC - Exit",
            "",
            "GIMBAL SETTINGS:",
            "  Direct Control: Each key press = 10° movement",
            "",
            "MODEL INFERENCE:",
            "  Press P to toggle wildlife detection",
            "  Green status = ON, Yellow = OFF, Red = Not Available",
            "",
            "Press any key to close help"
        ]
        
        starting_y = 150
        line_spacing = 40
        
        for line_index, line_text in enumerate(help_content):
            if not line_text:  # Skip empty lines
                continue
            
            self._draw_help_line(line_text, line_index, starting_y, line_spacing)

    def _draw_help_line(
        self, 
        text: str, 
        line_index: int, 
        starting_y: int, 
        line_spacing: int
    ) -> None:
        # Choose font and colour based on line type
        is_title = (line_index == 0)
        font = self.fonts['large'] if is_title else self.fonts['medium']
        colour = self.colours.YELLOW if is_title else self.colours.WHITE
        
        # Render and position text
        text_surface = font.render(text, True, colour)
        y_position = starting_y + line_index * line_spacing
        text_rect = text_surface.get_rect(center=(self.config.SCREEN_WIDTH // 2, y_position))
        
        self.screen.blit(text_surface, text_rect)

    def _wait_for_keypress(self) -> None:
        waiting_for_input = True
        
        while waiting_for_input and self.running:
            for event in pygame.event.get():
                if event.type in (pygame.KEYDOWN, pygame.QUIT):
                    waiting_for_input = False
                    
                    if event.type == pygame.QUIT:
                        self.server_manager.close_servers()
                        self.running = False

    # ============================================================================
    # EVENT HANDLING
    # ============================================================================

    def _handle_movement_keys(self, event: pygame.event.Event, is_key_pressed: bool) -> None:
        """
        Handle movement key press/release events.
        
        Args:
            event: Pygame event object
            is_key_pressed: True for key press, False for key release
        """
        keys = self.default_keys.copy()

        # Get movement keys from pygame
        if self.is_robot:
            # Robot motion publishing is handled each frame in update()
            return
        else:
            pygame_keys = pygame.key.get_pressed()
            keys["up"] = pygame_keys[pygame.K_w]
            keys["down"] = pygame_keys[pygame.K_s]
            keys["rotate_left"] = pygame_keys[pygame.K_q]
            keys["rotate_right"] = pygame_keys[pygame.K_e]
            keys["left"] = pygame_keys[pygame.K_a]
            keys["right"] = pygame_keys[pygame.K_d]
        
        if not self.is_robot:
            self.movement_keys = keys.copy()

    def _publish_robot_motion(self) -> None:
        """Read joystick/keyboard state and publish a single motion command."""
        x_axis = 0.0
        vx = 0.0
        vy = 0.0
        w = 0.0
        vy_front = 0.0
        vy_back = 0.0

        try:
            if self.joystick is not None and self.joystick.get_init():
                try:
                    y_axis = self.joystick.get_axis(0)
                except Exception:
                    y_axis = 0.0

                try:
                    rot_axis = self.joystick.get_axis(1)
                except Exception:
                    rot_axis = 0.0
                try:
                    front_axle_axis = self.joystick.get_axis(2)
                except Exception:
                    front_axle_axis = 0.0
                try:
                    back_axle_axis = self.joystick.get_axis(3)
                except Exception:
                    back_axle_axis = 0.0

                JOY_MAX_SPEED = 40.0
                vx = max(-100.0, min(100.0, x_axis * JOY_MAX_SPEED))
                vy = max(-100.0, min(100.0, -y_axis * JOY_MAX_SPEED))

                w = max(-100.0, min(100.0, rot_axis * JOY_MAX_ROT))
                vy_front = max(-100.0, min(100.0, front_axle_axis * JOY_MAX_SPEED))
                vy_back = max(-100.0, min(100.0, back_axle_axis * JOY_MAX_SPEED))

        except Exception:
            pass

        # Keyboard overrides/additions
        pygame_keys = pygame.key.get_pressed()
        key_speed = 50.0
        rot_speed = 40.0
        if pygame_keys[pygame.K_a]:
            vx = -key_speed
        if pygame_keys[pygame.K_d]:
            vx = key_speed
        if pygame_keys[pygame.K_w]:
            vy = key_speed
        if pygame_keys[pygame.K_s]:
            vy = -key_speed
        if pygame_keys[pygame.K_q]:
            w = -rot_speed
        if pygame_keys[pygame.K_e]:
            w = rot_speed

        # Deadzone to avoid noise
        DEADZONE = 0.10
        if abs(vy) < DEADZONE * 100.0:
            vy = 0.0
        if abs(w) < DEADZONE * 100.0:
            w = 0.0
        if abs(vy_front) < DEADZONE * 100.0:
            vy_front = 0.0
        if abs(vy_back) < DEADZONE * 100.0:
            vy_back = 0.0

        # Emit command: vector if movement present, else stop
        if (vx != 0.0) or (vy != 0.0) or (w != 0.0) or (vy_front != 0.0) or (vy_back != 0.0):
            cmd = {"type": "vector", "action": "set", "vx": int(vx), "vy": int(vy), "w": int(w), "vy_front": int(vy_front), "vy_back": int(vy_back)}
        else:
            cmd = self.default_keys

        try:
            print(cmd)
            self.send_command(json.dumps(cmd))
        except Exception as e:
            logger.error(f"Failed to send movement command: {e}")

    def _handle_function_keys(self, event: pygame.event.Event) -> None:
        key = event.key
        
        if key == pygame.K_SPACE:
            pass
            #self.send_command(json.dumps(self.default_keys.copy()).encode())
        elif key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_h:
            self.show_help()
        elif key == pygame.K_p:
            self._toggle_vision_inference()
        elif key in (pygame.K_1, pygame.K_2):
            self._handle_camera_toggle(key)
        elif key in (pygame.K_x, pygame.K_c):
            self._handle_gimbal_crane_control(key)
        elif key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
            self._handle_gimbal_arrow_keys(key)

    def _handle_camera_toggle(self, key: int) -> None:
        camera_index = 0 if key == pygame.K_1 else 1
        self.camera_states[camera_index] = not self.camera_states[camera_index]
        
        # Send appropriate command (intentionally not sent from GUI currently)
        
        #self.send_command(command)

    def _handle_gimbal_crane_control(self, key: int) -> None:
        """Handle X and C keys for crane servo control"""
        if key == pygame.K_x:
            self.send_gimbal_command("c_up")
        elif key == pygame.K_c:
            self.send_gimbal_command("c_down")
    
    def _handle_gimbal_arrow_keys(self, key: int) -> None:
        """Handle arrow keys for X/Y axis gimbal control"""
        if key == pygame.K_UP:
            self.send_gimbal_command("y_up")
        elif key == pygame.K_DOWN:
            self.send_gimbal_command("y_down")
        elif key == pygame.K_LEFT:
            self.send_gimbal_command("x_left")
        elif key == pygame.K_RIGHT:
            self.send_gimbal_command("x_right")
    
    def _handle_gimbal_key_release(self, event: pygame.event.Event) -> None:
        """Handle gimbal key releases (currently no action needed)"""
        pass

    def _toggle_vision_inference(self) -> None:
        """Toggle model inference on/off when 'p' key is pressed."""
        self.inference_manager.toggle_vision_inference()
            
        self.inference_enabled = not self.inference_enabled
        status = "ENABLED" if self.inference_enabled else "DISABLED"
        logger.info(f"Model inference {status}")
        print(f"Model inference {status}")  # Also print to console for immediate feedback

    def handle_events(self) -> None:
        """Handle all pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_movement_keys(event, True)
                self._handle_function_keys(event)
            elif event.type == pygame.KEYUP:
                self._handle_movement_keys(event, False)
                self._handle_gimbal_key_release(event)
            elif event.type == pygame.JOYBUTTONDOWN:
                # Map RB/LB to crane up/down
                if event.button == self.BUTTON_RB:
                    self.send_gimbal_command("c_up")
                elif event.button == self.BUTTON_LB:
                    self.send_gimbal_command("c_down")

    def _send_gimbal_action_with_throttle(self, axis_key: str, action: str, degrees: float, cooldown_ms: int) -> None:
        """Send a gimbal action with degrees if axis cooldown elapsed (axis_key: "x"|"y")."""
        now_ms = pygame.time.get_ticks()
        last_ms = self._last_gimbal_axis_send_ms.get(axis_key, 0)
        if (now_ms - last_ms) >= cooldown_ms:
            self.send_gimbal_command(action, degrees=degrees)
            self._last_gimbal_axis_send_ms[axis_key] = now_ms

    def _update_gimbal_from_controller(self) -> None:
        """Read right joystick axes and map to gimbal X/Y controls with throttling."""
        try:
            if self.joystick is None or not self.joystick.get_init():
                return
            try:
                right_x = self.joystick.get_axis(self.RIGHT_STICK_X_AXIS)
            except Exception:
                right_x = 0.0
            try:
                right_y = self.joystick.get_axis(self.RIGHT_STICK_Y_AXIS)
            except Exception:
                right_y = 0.0

            thr = self.GIMBAL_AXIS_THRESHOLD

            def calc_params(val: float) -> tuple[float, int]:
                mag = abs(val)
                if mag <= thr:
                    return 0.0, self.GIMBAL_MAX_COOLDOWN_MS
                # Normalize magnitude from threshold..1.0 to 0..1
                norm = (mag - thr) / max(1e-6, (1.0 - thr))
                # Degrees and cooldown scale with normalized magnitude
                degrees = self.GIMBAL_MIN_DEGREES + norm * (self.GIMBAL_MAX_DEGREES - self.GIMBAL_MIN_DEGREES)
                cooldown = int(self.GIMBAL_MAX_COOLDOWN_MS - norm * (self.GIMBAL_MAX_COOLDOWN_MS - self.GIMBAL_MIN_COOLDOWN_MS))
                return degrees, cooldown

            # Horizontal: right/left
            deg_x, cd_x = calc_params(right_x)
            if deg_x > 0.0:
                if right_x > 0:
                    self._send_gimbal_action_with_throttle("x", "x_right", degrees=deg_x, cooldown_ms=cd_x)
                else:
                    self._send_gimbal_action_with_throttle("x", "x_left", degrees=deg_x, cooldown_ms=cd_x)

            # Vertical: up/down (negative is up on most controllers)
            deg_y, cd_y = calc_params(right_y)
            if deg_y > 0.0:
                if right_y < 0:
                    self._send_gimbal_action_with_throttle("y", "y_up", degrees=deg_y, cooldown_ms=cd_y)
                else:
                    self._send_gimbal_action_with_throttle("y", "y_down", degrees=deg_y, cooldown_ms=cd_y)
        except Exception:
            # Never let controller issues crash the loop
            pass

    # ============================================================================
    # MAIN LOOP METHODS
    # ============================================================================

    def update(self) -> None:
        """Update game state (called once per frame)."""
        # Always process gimbal from controller regardless of robot/sim mode
        self._update_gimbal_from_controller()
        if self.is_robot:
            self._publish_robot_motion()
        else:
            self.handle_movement()

    def render(self) -> None:
        """Render the current frame."""
        self._collect_recent_frame()
        self.screen.blit(self.background, (0, 0))
        self.draw_overlays()
        pygame.display.flip()

    def run(self) -> None:
        """Main game loop with proper separation of concerns."""
        logger.info("Starting Wildlife Explorer GUI...")
        logger.info("Press 'H' for help, 'ESC' to exit")
        
        #TODO: Implement camera initialisation and streaming (Vinay)
        self.start_camera_streams()
        
        try:
            while self.running:
                self.handle_events()
                self.update()
                self.render()
                self.clock.tick(self.config.FPS)
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Clean up resources before exit."""
        logger.info("Cleaning up resources...")
        self.server_manager.close_servers()
        pygame.quit()
        sys.exit()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import os
    import argparse
    parser = argparse.ArgumentParser(description="Wildlife Explorer RC Car Controller")
    parser.add_argument("--robot", action='store_true', help="Whether to run the robot or sim")
    parser.add_argument("--broker", default="localhost", help="MQTT broker host/IP for robot mode")
    parser.add_argument("--broker_port", type=int, default=1883, help="MQTT broker TCP port for robot mode")
    args = parser.parse_args()
    gui_type = "Robot" if args.robot else "Sim"
    print(f"Wildlife Explorer for {gui_type}")
    print("==================================")
    print("1280x720 HD Interface")
    print()
    
    # Configure Background Path
    image_path = "GUI/wildlife_explorer_cams_open.png"
    
    if not os.path.exists(image_path):
        print(f"Image file '{image_path}' not found.")
        print("Place your image in the same folder and update the path.")
        print("Using fallback background for now...")
    
    #TODO: Implement your command callback function
    def command_callback(command: str) -> None:
        logger.info(f"GUI Command: {command}")
    
    try:
        gui = ExplorerGUI(image_path, command_callback, args.robot, mqtt_broker_host_ip=args.broker, mqtt_port=args.broker_port)
        gui.run()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)