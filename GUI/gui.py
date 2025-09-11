import pygame
import sys
import logging
import cv2
import numpy as np
import os
import json
from typing import Callable, Optional, List
from gui_config import ConnectionStatus, ArmState, Colour, GuiConfig

# Get the parent directory path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

# Now you can import modules from the parent directory
from tiality_server import TialityServerManager

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
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        
        # 4. Correct the orientation. OpenCV arrays are (height, width), but
        #    pygame.surfarray.make_surface expects (width, height). We swap the axes.
        img_rgb = img_rgb.swapaxes(0, 1)

        # 5. Create a Pygame surface directly from the NumPy array.
        #    This is another very fast, low-level operation.
        frame_surface = pygame.surfarray.make_surface(img_rgb)
        
        return frame_surface
        
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
        sim: bool = False
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
        self.sim = sim
        
        # Setup display and resources
        self._load_background(background_image_path)
        self._init_display()
        self._init_fonts()
        self._init_camera_layout()
        
        # Initialise application state
        self._init_state()
        
        # Setup Server and shared frame queue
        self.server_manager = TialityServerManager(
            grpc_port = 50051, 
            mqtt_port = 1883, 
            mqtt_broker_host_ip = "localhost",
            decode_video_func = _decode_video_frame_opencv,
            num_decode_video_workers = 1 # Don't change this for now
            )
        self.server_manager.start_servers()

        # Setup timing
        self.clock = pygame.time.Clock()
        self.running = True
        
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

    def set_connection_status(self, status: ConnectionStatus) -> None:
        """TODO: Set connection for GUI idk if you want to open a socket and send over on a port"""
        self.connection_status = status

    def start_camera_streams(self) -> None:
        """TODO: Implement camera initialisation and streaming (Vinay)"""
        pass

    # ============================================================================
    # MOVEMENT HANDLING
    # ============================================================================

    def _get_active_movements(self) -> List[str]:
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
        active_movements = self._get_active_movements()
        
        if active_movements:
            # Build movement command from active directions
            
            json_string = json.dumps(active_movements)
            encoded_string = json_string.encode()
            self.send_command(encoded_string)

    # ============================================================================
    # DRAWING METHODS
    # ============================================================================
    def _collect_recent_frame(self):
        """
        Collect frames from server manager to display, currently only works for first display
        """
        #TODO: Add multiple camera functionality
        self.camera_surfaces[0] = self.server_manager.get_video_frame()
        # print(type(self.server_manager.get_video_frame()))

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
        """Draw connection and arm status information."""
        status_y_position = self.config.SCREEN_HEIGHT - 50
        
        self._draw_connection_status(status_y_position)
        self._draw_arm_status(status_y_position - 25)

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
            "  WASD / Arrow Keys - Move car",
            " E/R - Rotate Car"
            "  Space - Emergency stop",
            "  TODO: 1, 2 - Toggle cameras",
            "  TODO: X - Extend arm",
            "  TODO: C - Contract arm",
            "  H - Show/hide this help",
            "  ESC - Exit",
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
        # Map pygame keys to movement directions
        # key_to_direction = {
        #     pygame.K_UP: 'up', 
        #     pygame.K_w: 'up',
        #     pygame.K_DOWN: 'down', 
        #     pygame.K_s: 'down',
        #     pygame.K_LEFT: 'left', 
        #     pygame.K_a: 'left',
        #     pygame.K_RIGHT: 'right', 
        #     pygame.K_d: 'right',
        #     pygame.K_e: 'rotate_right',
        #     pygame.K_q: 'rotate_left'
        # }
        
        # if event.key in key_to_direction:
        #     direction = key_to_direction[event.key]
        #     self.movement_keys[direction] = is_key_pressed

        pygame_keys = pygame.key.get_pressed()
        keys = self.default_keys.copy()
        keys["up"] = pygame_keys[pygame.K_w] or pygame_keys[pygame.K_UP]
        keys["down"] = pygame_keys[pygame.K_s] or pygame_keys[pygame.K_DOWN]
        keys["rotate_left"] = pygame_keys[pygame.K_q]
        keys["rotate_right"] = pygame_keys[pygame.K_e]
        keys["left"] = pygame_keys[pygame.K_a]
        keys["right"] = pygame_keys[pygame.K_d]
        self.movement_keys = keys.copy()

    def _handle_function_keys(self, event: pygame.event.Event) -> None:
        key = event.key
        
        if key == pygame.K_SPACE:
            pass
            #self.send_command(json.dumps(self.default_keys.copy()).encode())
        elif key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_h:
            self.show_help()
        elif key in (pygame.K_1, pygame.K_2):
            self._handle_camera_toggle(key)
        elif key in (pygame.K_x, pygame.K_c):
            self._handle_arm_control(key)

    def _handle_camera_toggle(self, key: int) -> None:
        camera_index = 0 if key == pygame.K_1 else 1
        self.camera_states[camera_index] = not self.camera_states[camera_index]
        
        # Send appropriate command
        camera_number = camera_index + 1
        state = "ON" if self.camera_states[camera_index] else "OFF"
        command = f'CAMERA_{camera_number}_{state}'
        
        #self.send_command(command)

    def _handle_arm_control(self, key: int) -> None:
        if key == pygame.K_x:
            self.arm_state = ArmState.EXTENDED
            #self.send_command('ARM_EXTEND')
        elif key == pygame.K_c:
            self.arm_state = ArmState.RETRACTED
            #self.send_command('ARM_CONTRACT')

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

    # ============================================================================
    # MAIN LOOP METHODS
    # ============================================================================

    def update(self) -> None:
        """Update game state (called once per frame)."""
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
    
    print("Wildlife Explorer RC Car Controller")
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
        gui = ExplorerGUI(image_path, command_callback)
        gui.run()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)