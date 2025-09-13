import pygame
import sys
import logging
import os
from typing import Callable, Optional, List
from gui_config import ConnectionStatus, ArmState, Colour, GuiConfig
from gui_mqtt_client import GuiMqttClient

# Add MotorMoving directory to path to import config
motor_moving_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'MotorMoving')
if motor_moving_path not in sys.path:
    sys.path.append(motor_moving_path)
from config import PI_IP, DEFAULT_GIMBAL_DEGREES

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        pi_ip: str = PI_IP,
        command_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Args:
            background_image_path: Path to the background image file
            pi_ip: IP address of the Raspberry Pi
            command_callback: Callback function for handling commands to PI
        """
        # Initialise core components
        pygame.init()
        self.config = GuiConfig()
        self.colours = Colour()
        
        # Setup display and resources
        self._load_background(background_image_path)
        self._init_display()
        self._init_fonts()
        self._init_camera_layout()
        
        # Initialise application state
        self._init_state()
        
        # Setup callback and timing
        self.command_callback = command_callback
        self.clock = pygame.time.Clock()
        
        # Command throttling for 2Hz (500ms between commands)
        self.last_command_time = 0
        self.command_interval = 500  # milliseconds (2Hz = 1000ms/2 = 500ms)
        self.last_sent_command = None
        
        # Setup MQTT client
        self.mqtt_client = GuiMqttClient(pi_ip)
        self.mqtt_client.set_connection_callback(self._on_connection_change)
        self.mqtt_connected = self.mqtt_client.connect()
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
            (30, 170),   # Camera 1 position (left)
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
        self.movement_keys = {
            'up': False, 
            'down': False, 
            'left': False, 
            'right': False
        }
        
        # Camera states (all cameras start active)
        self.camera_states = [True] * self.config.NUM_CAMERAS
        
        # Hardware states
        self.arm_state = ArmState.LOWERED
        
        # Add gimbal state tracking
        self.gimbal_position = {'x': 90, 'y': 90, 'c': 90}  # Track current angles
        
        self.connection_status = ConnectionStatus.DISCONNECTED

    @property
    def is_gimbal_mode(self) -> bool:
        """Returns True if we're in gimbal control mode (arm is raised)"""
        return self.arm_state == ArmState.RAISED
    
    def _on_connection_change(self, connected: bool):
        """Callback for MQTT connection status changes"""
        if connected:
            self.connection_status = ConnectionStatus.CONNECTED
        else:
            self.connection_status = ConnectionStatus.DISCONNECTED
        logger.info(f"Pi connection status: {self.connection_status.value}")

    # ============================================================================
    # COMMAND AND STATUS METHODS
    # ============================================================================

    def send_command(self, command: str) -> None:
        """Enhanced command sending with MQTT support"""
        logger.info(f"Sending command: {command}")
        
        # Handle different command types via MQTT
        if command.startswith('GIMBAL_'):
            self._send_gimbal_mqtt_command(command)
        elif command.startswith('MOVE_'):
            # Handle movement commands like MOVE_LEFT, MOVE_UP, etc.
            self._handle_move_command(command)
        elif command in ['UP', 'DOWN', 'LEFT', 'RIGHT']:
            self._send_movement_command(command)
        elif command == 'STOP':
            self.mqtt_client.send_stop_command()
        elif command.startswith('ARM_'):
            # For now, just log arm commands - could extend later
            logger.info(f"Arm command: {command}")
        
        # Call existing callback if set (for backwards compatibility)
        if self.command_callback:
            try:
                self.command_callback(command)
            except Exception as e:
                logger.error(f"Command callback error: {e}")
    
    def _send_gimbal_mqtt_command(self, command: str) -> None:
        """Convert GUI command to MQTT gimbal command"""
        # Parse command like "GIMBAL_X_LEFT_10"
        parts = command.split('_')
        if len(parts) >= 3:
            action = f"{parts[1].lower()}_{parts[2].lower()}"  # "x_left"
            degrees = int(parts[3]) if len(parts) > 3 else 10
            
            # This would integrate with your MQTT client
            mqtt_command = {
                "type": "gimbal", 
                "action": action,
                "degrees": degrees
            }
            
            # Send via MQTT client to Pi
            self.mqtt_client.send_gimbal_command(action, degrees)
    
    def _send_movement_command(self, direction: str) -> None:
        """Send motor movement command via MQTT"""
        # Convert direction to velocity vector
        vx, vy = 0, 0
        if direction == "UP":
            vy = 50
        elif direction == "DOWN":
            vy = -50
        elif direction == "LEFT":
            vx = -50
        elif direction == "RIGHT":
            vx = 50
        
        self.mqtt_client.send_motor_command(vx, vy, 0)

    def _handle_move_command(self, command: str) -> None:
        """Handle MOVE commands like MOVE_LEFT, MOVE_UP_RIGHT, etc."""
        # Remove 'MOVE_' prefix and split by '_'
        directions = command[5:].split('_')
        
        vx, vy = 0, 0
        
        for direction in directions:
            if direction == "UP":
                vy += 50
            elif direction == "DOWN":
                vy -= 50
            elif direction == "LEFT":
                vx -= 50
            elif direction == "RIGHT":
                vx += 50
        
        # Send the combined movement command
        self.mqtt_client.send_motor_command(vx, vy, 0)

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
        return [
            direction.upper() 
            for direction, is_active in self.movement_keys.items() 
            if is_active
        ]

    def handle_movement(self) -> None:
        """Process current movement key states and send commands with throttling."""
        current_time = pygame.time.get_ticks()
        
        # Check if enough time has passed since last command (2Hz throttling)
        if current_time - self.last_command_time < self.command_interval:
            return
        
        active_movements = self._get_active_movements()
        
        if active_movements:
            # Build movement command from active directions
            command = 'MOVE_' + '_'.join(active_movements)
        else:
            # Send stop command when no keys are pressed
            command = 'STOP'
        
        # Only send command if it's different from the last one
        if command != self.last_sent_command:
            self.send_command(command)
            self.last_command_time = current_time
            self.last_sent_command = command

    # ============================================================================
    # DRAWING METHODS
    # ============================================================================

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
        """Enhanced status display"""
        is_raised = (self.arm_state == ArmState.RAISED)
        arm_colour = self.colours.GREEN if is_raised else self.colours.BLUE
        
        # Show current mode
        mode_text = "GIMBAL MODE" if is_raised else "CAR MODE"
        arm_text = f"Arm: {self.arm_state.value} ({mode_text})"
        
        arm_surface = self.fonts['medium'].render(arm_text, True, arm_colour)
        self.screen.blit(arm_surface, (30, y_position))
        
        # Show gimbal position when in gimbal mode
        if is_raised:
            pos_text = f"Gimbal: X={self.gimbal_position['x']}° Y={self.gimbal_position['y']}° C={self.gimbal_position['c']}°"
            pos_surface = self.fonts['small'].render(pos_text, True, self.colours.YELLOW)
            self.screen.blit(pos_surface, (30, y_position + 25))

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
        pygame.display.flip()
        self._wait_for_keypress()

    def _draw_help_overlay(self) -> None:
        """Draw help overlay with context-aware instructions"""
        if self.is_gimbal_mode:
            help_lines = [
                "GIMBAL CONTROL MODE (Arm Raised):",
                "  Arrow Keys / WASD - Control gimbal X/Y",
                "  X - Crane up", 
                "  C - Crane down",
                "  Space - Emergency stop",
                "  1, 2 - Toggle cameras",
                "  H - Show/hide this help",
                "  ESC - Exit",
                "",
                "Lower arm to return to car control",
                "Press any key to close help"
            ]
        else:
            help_lines = [
                "CAR CONTROL MODE (Arm Lowered):",
                "  Arrow Keys / WASD - Move car",
                "  X - Raise arm (enables gimbal control)",
                "  Space - Emergency stop", 
                "  1, 2 - Toggle cameras",
                "  H - Show/hide this help",
                "  ESC - Exit",
                "",
                "Press any key to close help"
            ]
        
        starting_y = 150
        line_spacing = 40
        
        for line_index, line_text in enumerate(help_lines):
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
                        self.running = False

    # ============================================================================
    # EVENT HANDLING
    # ============================================================================

    def _handle_movement_keys(self, event: pygame.event.Event, is_key_pressed: bool) -> None:
        """Handle movement keys - now context-aware for car vs gimbal"""
        
        if self.is_gimbal_mode:
            # GIMBAL CONTROL MODE
            self._handle_gimbal_keys(event, is_key_pressed)
        else:
            # CAR CONTROL MODE (existing logic)
            self._handle_car_movement_keys(event, is_key_pressed)
    
    def _handle_gimbal_keys(self, event: pygame.event.Event, is_key_pressed: bool) -> None:
        """Handle gimbal control when arm is raised"""
        if not is_key_pressed:
            return  # Only handle key press, not release for gimbal
            
        gimbal_commands = {
            pygame.K_LEFT: 'x_left',    # Left arrow = gimbal left
            pygame.K_a: 'x_left',       # A = gimbal left  
            pygame.K_RIGHT: 'x_right',  # Right arrow = gimbal right
            pygame.K_d: 'x_right',      # D = gimbal right
            pygame.K_UP: 'y_up',        # Up arrow = gimbal up
            pygame.K_w: 'y_up',         # W = gimbal up
            pygame.K_DOWN: 'y_down',    # Down arrow = gimbal down
            pygame.K_s: 'y_down'        # S = gimbal down
        }
        
        if event.key in gimbal_commands:
            action = gimbal_commands[event.key]
            degrees = DEFAULT_GIMBAL_DEGREES  # Use config value (2 degrees)
            
            # Send MQTT gimbal command
            gimbal_command = {
                "type": "gimbal",
                "action": action,
                "degrees": degrees
            }
            self.send_command(f'GIMBAL_{action.upper()}_{degrees}')
    
    def _handle_car_movement_keys(self, event: pygame.event.Event, is_key_pressed: bool) -> None:
        """Original car movement logic"""
        key_to_direction = {
            pygame.K_UP: 'up', 
            pygame.K_w: 'up',
            pygame.K_DOWN: 'down', 
            pygame.K_s: 'down',
            pygame.K_LEFT: 'left', 
            pygame.K_a: 'left',
            pygame.K_RIGHT: 'right', 
            pygame.K_d: 'right'
        }
        
        if event.key in key_to_direction:
            direction = key_to_direction[event.key]
            self.movement_keys[direction] = is_key_pressed
    
    def _handle_arm_control(self, key: int) -> None:
        """Enhanced arm control with crane functionality"""
        if key == pygame.K_x:
            if self.arm_state == ArmState.LOWERED:
                # Raise the arm (switch to gimbal mode)
                self.arm_state = ArmState.RAISED
                self.send_command('ARM_RAISE')
            else:
                # Arm is raised - X now controls crane up
                self.send_command(f'GIMBAL_C_UP_{DEFAULT_GIMBAL_DEGREES}')
                
        elif key == pygame.K_c:
            if self.arm_state == ArmState.LOWERED:
                # This shouldn't happen, but handle gracefully
                pass  
            else:
                # Arm is raised - C controls crane down
                self.send_command(f'GIMBAL_C_DOWN_{DEFAULT_GIMBAL_DEGREES}')
                
        # Add way to lower arm (maybe hold shift + C or new key)
        # Or add automatic lowering after inactivity

    def _handle_function_keys(self, event: pygame.event.Event) -> None:
        """Enhanced function key handling"""
        key = event.key
        
        if key == pygame.K_SPACE:
            self.send_command('STOP')
        elif key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_h:
            self.show_help()
        elif key in (pygame.K_1, pygame.K_2):
            self._handle_camera_toggle(key)
        elif key in (pygame.K_x, pygame.K_c):
            self._handle_arm_control(key)
        elif key == pygame.K_r:  # New: R key to return to car mode
            if self.arm_state == ArmState.RAISED:
                self.arm_state = ArmState.LOWERED
                self.send_command('ARM_LOWER')
                logger.info("Returned to car control mode")

    def _handle_camera_toggle(self, key: int) -> None:
        camera_index = 0 if key == pygame.K_1 else 1
        self.camera_states[camera_index] = not self.camera_states[camera_index]
        
        # Send appropriate command
        camera_number = camera_index + 1
        state = "ON" if self.camera_states[camera_index] else "OFF"
        command = f'CAMERA_{camera_number}_{state}'
        
        self.send_command(command)

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
        # Cleanup MQTT connection
        if hasattr(self, 'mqtt_client'):
            self.mqtt_client.disconnect()
        
        pygame.quit()
        logger.info("GUI shutdown complete")
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
   
    image_path = "wildlife_explorer.png"
    
    if not os.path.exists(image_path):
        print(f"Image file '{image_path}' not found.")
        print("Place your image in the same folder and update the path.")
        print("Using fallback background for now...")
    
    #TODO: Implement your command callback function
    def command_callback(command: str) -> None:
        logger.info(f"GUI Command: {command}")
    
    # Pi IP address is now configured in config.py
    
    try:
        gui = ExplorerGUI(image_path, PI_IP, command_callback)
        gui.run()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)