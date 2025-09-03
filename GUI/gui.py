import pygame
import sys
import logging
import asyncio
import json
import threading
from typing import Callable, Optional, List
import cv2
import numpy as np
import paho.mqtt.client as mqtt
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration
from gui_config import ConnectionStatus, ArmState, Colour, GuiConfig

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
        pi_ip: str = "10.1.1.124",
        command_callback: Optional[Callable[[str], None]] = None
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
        
        # Setup display and resources
        self._load_background(background_image_path)
        self._init_display()
        self._init_fonts()
        self._init_camera_layout()
        
        # Initialise application state
        self._init_state()
        
        # Initialize WebRTC frame storage
        self.current_frame = None
        
        # Setup callback and timing
        self.command_callback = command_callback
        self.clock = pygame.time.Clock()
        self.running = True
        
        # WebRTC setup
        self.pi_ip = pi_ip
        self.mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.peer_connection: Optional[RTCPeerConnection] = None
        self.webrtc_connected = False
        self.frame_queue = asyncio.Queue(maxsize=5)
        self.webrtc_loop = None
        self.webrtc_thread = None
        
        # MQTT event handlers
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        
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
        # Camera feed position (single camera)
        self.camera_positions = [
            (35, 255),   # Camera 1 position
        ]
        
        self.camera_surfaces = [None] * self.config.NUM_CAMERAS
        self.camera_threads = []
        
        # Status indicator position for camera
        self.camera_indicator_positions = [
            (370, self.config.SCREEN_HEIGHT - 500),   # Camera 1 indicator
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
        self.arm_state = ArmState.RETRACTED
        self.connection_status = ConnectionStatus.DISCONNECTED

    # ============================================================================
    # COMMAND AND STATUS METHODS
    # ============================================================================

    def send_command(self, command: str) -> None:
        """
        Send command to Pi via callback function 
        """
        if self.command_callback:
            try:
                self.command_callback(command)
                logger.debug(f"Command sent: {command}")
            except Exception as e:
                logger.error(f"Command callback error: {e}")
        else:
            logger.info(f"Command (no callback): {command}")

    def set_connection_status(self, status: ConnectionStatus) -> None:
        """TODO: Set connection for GUI idk if you want to open a socket and send over on a port"""
        self.connection_status = status

    def start_camera_streams(self) -> None:
        """Initialize WebRTC camera stream."""
        try:
            self.webrtc_thread = threading.Thread(target=self._run_webrtc_client)
            self.webrtc_thread.daemon = True
            self.webrtc_thread.start()
            logger.info("WebRTC client thread started")
        except Exception as e:
            logger.error(f"Failed to start camera streams: {e}")

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
        """Process current movement key states and send commands."""
        active_movements = self._get_active_movements()
        
        if active_movements:
            # Build movement command from active directions
            command = 'MOVE_' + '_'.join(active_movements)
            self.send_command(command)

    # ============================================================================
    # DRAWING METHODS
    # ============================================================================

    def _draw_cameras(self) -> None:
        """Draw camera feeds and their status indicators."""
        for camera_index in range(self.config.NUM_CAMERAS):
            self._draw_single_camera(camera_index)
            self._draw_camera_status(camera_index)

    def _draw_single_camera(self, camera_index: int) -> None:
        # Display WebRTC stream in the single camera position
        if camera_index == 0 and hasattr(self, 'current_frame') and self.current_frame is not None:
            # Convert OpenCV frame to pygame surface
            frame_rgb = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
            # Resize frame to fit camera display area (510x230)
            frame_resized = cv2.resize(frame_rgb, (510, 230))
            frame_surface = pygame.surfarray.make_surface(frame_resized.swapaxes(0, 1))
            
            camera_position = self.camera_positions[camera_index]
            self.screen.blit(frame_surface, camera_position)
        elif camera_index == 0:
            # Draw placeholder when no video feed
            camera_position = self.camera_positions[camera_index]
            placeholder_surface = pygame.Surface((510, 230))
            placeholder_surface.fill(self.colours.BLACK)
            self.screen.blit(placeholder_surface, camera_position)

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
            "  Space - Emergency stop",
            "  1 - Toggle camera",
            "  X - Extend arm",
            "  C - Contract arm",
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

    def _handle_function_keys(self, event: pygame.event.Event) -> None:
        key = event.key
        
        if key == pygame.K_SPACE:
            self.send_command('STOP')
        elif key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_h:
            self.show_help()
        elif key == pygame.K_1:
            self._handle_camera_toggle(key)
        elif key in (pygame.K_x, pygame.K_c):
            self._handle_arm_control(key)

    def _handle_camera_toggle(self, key: int) -> None:
        camera_index = 0  # Only one camera now
        self.camera_states[camera_index] = not self.camera_states[camera_index]
        
        # Send appropriate command
        state = "ON" if self.camera_states[camera_index] else "OFF"
        command = f'CAMERA_1_{state}'
        
        self.send_command(command)

    def _handle_arm_control(self, key: int) -> None:
        if key == pygame.K_x:
            self.arm_state = ArmState.EXTENDED
            self.send_command('ARM_EXTEND')
        elif key == pygame.K_c:
            self.arm_state = ArmState.RETRACTED
            self.send_command('ARM_CONTRACT')

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
        
        # Stop WebRTC client
        if hasattr(self, 'mqtt_client'):
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        pygame.quit()
        sys.exit()

    # ============================================================================
    # WEBRTC METHODS
    # ============================================================================

    def _run_webrtc_client(self):
        """Run WebRTC client in separate thread."""
        asyncio.run(self._start_webrtc_client())

    async def _start_webrtc_client(self):
        """Start the WebRTC client connection."""
        self.webrtc_loop = asyncio.get_running_loop()
        
        try:
            self.mqtt_client.connect(self.pi_ip, 1883, 60)
            self.mqtt_client.loop_start()
            
            # Start frame update task
            asyncio.create_task(self._update_frames())
            
            # Keep the WebRTC loop running
            while self.running:
                await asyncio.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Error in WebRTC client: {e}")

    def _on_mqtt_connect(self, client, userdata, flags, rc, properties):
        """Callback when MQTT connects."""
        if rc == 0:
            logger.info("Connected to MQTT broker for WebRTC")
            client.subscribe("webrtc/answer")
            if self.webrtc_loop:
                self.webrtc_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._initiate_webrtc())
                )
        else:
            logger.error(f"Failed to connect to MQTT broker: {rc}")

    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        try:
            if msg.topic == "webrtc/answer":
                answer_data = json.loads(msg.payload.decode())
                if self.webrtc_loop:
                    self.webrtc_loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(self._handle_answer(answer_data))
                    )
        except Exception as e:
            logger.error(f"Error handling MQTT message: {e}")

    async def _initiate_webrtc(self):
        """Initiate WebRTC connection by sending offer."""
        try:
            logger.info("Initiating WebRTC connection")
            
            configuration = RTCConfiguration(iceServers=[])
            self.peer_connection = RTCPeerConnection(configuration)
            
            from aiortc import RTCRtpTransceiver
            self.peer_connection.addTransceiver("video", direction="recvonly")
            
            @self.peer_connection.on("track")
            async def on_track(track):
                logger.info(f"Received track: {track.kind}")
                if track.kind == "video":
                    asyncio.create_task(self._process_video_track(track))
            
            @self.peer_connection.on("connectionstatechange")
            async def on_connectionstatechange():
                logger.info(f"Connection state: {self.peer_connection.connectionState}")
                if self.peer_connection.connectionState == "connected":
                    self.webrtc_connected = True
                elif self.peer_connection.connectionState in ["failed", "closed"]:
                    self.webrtc_connected = False
            
            offer = await self.peer_connection.createOffer()
            await self.peer_connection.setLocalDescription(offer)
            
            offer_data = {
                "sdp": self.peer_connection.localDescription.sdp,
                "type": self.peer_connection.localDescription.type
            }
            self.mqtt_client.publish("webrtc/offer", json.dumps(offer_data))
            logger.info("Sent WebRTC offer")
            
        except Exception as e:
            logger.error(f"Error initiating WebRTC: {e}")

    async def _handle_answer(self, answer_data):
        """Handle WebRTC answer from server."""
        try:
            logger.info("Received WebRTC answer from server")
            if self.peer_connection:
                await self.peer_connection.setRemoteDescription(
                    RTCSessionDescription(
                        sdp=answer_data["sdp"],
                        type=answer_data["type"]
                    )
                )
                logger.info("Set remote description from answer")
        except Exception as e:
            logger.error(f"Error handling WebRTC answer: {e}")

    async def _process_video_track(self, track):
        """Process incoming video frames from WebRTC track."""
        try:
            while self.running:
                frame = await track.recv()
                if frame:
                    img = frame.to_ndarray(format="bgr24")
                    try:
                        self.frame_queue.put_nowait(img)
                    except asyncio.QueueFull:
                        try:
                            self.frame_queue.get_nowait()
                            self.frame_queue.put_nowait(img)
                        except asyncio.QueueEmpty:
                            pass
        except Exception as e:
            logger.error(f"Error processing video track: {e}")

    async def _update_frames(self):
        """Update current frame from queue for GUI display."""
        while self.running:
            try:
                frame = await asyncio.wait_for(self.frame_queue.get(), timeout=0.1)
                self.current_frame = frame
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Error updating frames: {e}")
            await asyncio.sleep(0.033)  # ~30 FPS


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
    
    try:
        pi_ip = "10.1.1.124"  # Change this to your Pi's IP address
        gui = ExplorerGUI(image_path, pi_ip, command_callback)
        gui.run()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)