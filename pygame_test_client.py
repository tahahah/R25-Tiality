import pygame
from pygame.locals import *
import math
import threading
import io
import queue
import grpc
import time
from OpenGL.GL import *
from OpenGL.GLU import *
import tiality_server

def frame_generator_pygame(frame_queue: queue.Queue):
    """
    A generator function that gets Pygame surfaces from a thread-safe queue,
    encodes them as JPEG, and yields them as VideoFrame messages.
    """
    print("Frame generator started. Waiting for frames from the queue...")
    while True:
        # Block until a frame is available in the queue.
        frame_surface = frame_queue.get()
        print(frame_surface)
        
        # If a sentinel value (e.g., None) is received, stop the generator.
        if frame_surface is None:
            print("Stopping frame generator.")
            break

        try:
            # --- Preprocessing ---
            # Use an in-memory binary stream to hold the JPEG data.
            byte_io = io.BytesIO()
            pygame.image.save(frame_surface, byte_io, 'jpeg')
            print(byte_io)
            # Get the byte value from the stream.
            frame_bytes = byte_io.getvalue()
            # ---------------------
            print(frame_bytes)

            # BYTES Convert to test--------
            # Convert the JPEG bytes into a Pygame surface.
            byte_io2 = io.BytesIO(frame_bytes)
            #print(byte_io)
            frame_surface2 = pygame.image.load(byte_io2)
            print(frame_surface2)
            try:
                with open("debug_frame_client.jpg", "wb") as f:
                    f.write(frame_bytes)
                print("Saved problematic frame to debug_frame.jpg")
            except Exception as save_e:
                print(f"Could not save debug frame: {save_e}")

            #--------------- REMOVE


            # Yield the frame data in the format expected by the .proto file.
            yield tiality_server.video_streaming_pb2.VideoFrame(frame_data=frame_bytes)

        except Exception as e:
            print(f"Error encoding frame: {e}")

# --- Helper function to draw a Cuboid ---
def Cuboid():
    """Draws a unit cuboid centered at the origin."""
    # Vertices of the cuboid
    vertices = (
        (1, -0.5, -1),   # 0
        (1, 0.5, -1),    # 1
        (-1, 0.5, -1),   # 2
        (-1, -0.5, -1),  # 3
        (1, -0.5, 1),    # 4
        (1, 0.5, 1),     # 5
        (-1, -0.5, 1),   # 6
        (-1, 0.5, 1)     # 7
    )
    # Edges of the cuboid (vertex indices)
    edges = (
        (0, 1), (0, 3), (0, 4),
        (2, 1), (2, 3), (2, 7),
        (6, 3), (6, 4), (6, 7),
        (5, 1), (5, 4), (5, 7)
    )
    # Surfaces of the cuboid (vertex indices)
    surfaces = (
        (0, 1, 2, 3), # Back
        (3, 2, 7, 6), # Left
        (6, 7, 5, 4), # Front
        (4, 5, 1, 0), # Right
        (1, 5, 7, 2), # Top
        (4, 0, 3, 6)  # Bottom
    )
    
    # --- Draw Surfaces ---
    glBegin(GL_QUADS)
    # Use a different color for each face for better 3D visualization
    colors = [(1,0,0), (0,1,0), (0,0,1), (1,1,0), (1,0,1), (0,1,1)]
    for i, surface in enumerate(surfaces):
        glColor3fv(colors[i])
        for vertex in surface:
            glVertex3fv(vertices[vertex])
    glEnd()

    # --- Draw Edges (Outline) ---
    # This makes the shape clearer
    glColor3fv((0, 0, 0)) # Black color for edges
    glBegin(GL_LINES)
    for edge in edges:
        for vertex in edge:
            glVertex3fv(vertices[vertex])
    glEnd()

def Ground():
    """Draws a large ground plane."""
    glBegin(GL_QUADS)
    glColor3fv((0.2, 0.6, 0.2)) # Greenish color for the ground
    glVertex3f(-50.0, -0.5, -50.0)
    glVertex3f(-50.0, -0.5, 50.0)
    glVertex3f(50.0, -0.5, 50.0)
    glVertex3f(50.0, -0.5, -50.0)
    glEnd()


# --- Player Class ---
class Vehicle:
    def __init__(self, x, y, z):
        """
        Initializes the vehicle in 3D space.
        Args:
            x, y, z (float): The initial coordinates.
        """
        # --- Movement Attributes ---
        # Position is now a 3D vector
        self.position = [x, y, z]
        self.angle = 0.0 # Rotation around the Y-axis
        self.speed = 0.0
        
        # --- Control Constants ---
        self.max_speed = 0.2
        self.acceleration = 0.005
        self.friction = 0.0025
        self.rotation_speed = 2.0

    def update(self, keys = None):
        """
        Updates the vehicle's state each frame based on user input.
        """
        # --- Detect keyboard input if keys not supplied ---
        if keys == None:
            pygame_keys = pygame.key.get_pressed()
            keys = {}
            keys["up"] = pygame_keys[pygame.K_w] or pygame_keys[pygame.K_UP]
            keys["down"] = pygame_keys[pygame.K_s] or pygame_keys[pygame.K_DOWN]
            keys["rotate_left"] = pygame_keys[pygame.K_q]
            keys["rotate_right"] = pygame_keys[pygame.K_e]
            keys["left"] = pygame_keys[pygame.K_a]
            keys["right"] = pygame_keys[pygame.K_d]

        # --- Acceleration and Deceleration (Forward/Backward on W/S) ---
        if keys["up"]:
            self.speed += self.acceleration
            if self.speed > self.max_speed: self.speed = self.max_speed
        elif keys["down"]:
            self.speed -= self.acceleration
            if self.speed < -self.max_speed / 2: self.speed = -self.max_speed / 2
        else: # Apply friction
            if self.speed > 0:
                self.speed -= self.friction
                if self.speed < 0: self.speed = 0
            elif self.speed < 0:
                self.speed += self.friction
                if self.speed > 0: self.speed = 0

        # --- Rotation (now on Q and E) ---
        if keys["rotate_left"]:
            self.angle += self.rotation_speed
        if keys["rotate_right"]:
            self.angle -= self.rotation_speed
        self.angle %= 360

        # --- Calculate movement vectors ---
        angle_rad = math.radians(self.angle)
        # In OpenGL's default coordinate system, "forward" is along the negative Z axis.
        # A rotation of `angle` around the Y axis transforms the forward vector (0,0,-1)
        # and the right vector (1,0,0) as follows:
        forward_x = -math.sin(angle_rad)
        forward_z = -math.cos(angle_rad)
        
        right_x = math.cos(angle_rad)
        right_z = -math.sin(angle_rad)

        # --- Update Position ---
        # 1. Apply forward/backward movement
        self.position[0] += self.speed * forward_x
        self.position[2] += self.speed * forward_z

        # 2. Apply strafing (Side-to-side) movement (now on A and D)
        strafe_velocity = 0
        # Strafe left
        if keys["left"]:
            strafe_velocity -= self.max_speed * 0.8 # Use a constant speed for strafing
        # Strafe right
        if keys["right"]:
            strafe_velocity += self.max_speed * 0.8
            
        self.position[0] += strafe_velocity * right_x
        self.position[2] += strafe_velocity * right_z

    def draw(self):
        """Applies transformations and draws the vehicle."""
        glPushMatrix() # Save the current matrix state
        
        # 1. Translate to the vehicle's position
        glTranslatef(self.position[0], self.position[1], self.position[2])
        # 2. Rotate around the Y axis. We add 180 because the model's "front" is along its +Z,
        # but we want it to face world -Z at angle 0.
        glRotatef(self.angle, 0, 1, 0)
        # 3. Scale the cuboid to look more like a vehicle
        glScalef(0.5, 0.5, 1.0)
        
        # Draw the actual cuboid shape
        Cuboid()
        
        glPopMatrix() # Restore the matrix state

# --- Main Function ---
def main():
    
    # --- Setup thread safe queues, vars  and start gRPC client---
    frame_queue = queue.Queue(maxsize = 1)
    server_addr = 'localhost:50051'
    client_thread = threading.Thread(
        target=tiality_server.client.run_grpc_client, 
        args=(server_addr, frame_queue, frame_generator_pygame),
        daemon=True  # A daemon thread will exit when the main program exits.
    )
    client_thread.start()
    
    # --- Pygame Initialization ---
    pygame.init()
    display = (640, 480)
    # Set display mode for OpenGL. DOUBLEBUF means we have two display buffers
    # to prevent flickering. OPENGL specifies we're using OpenGL.
    screen = pygame.display.set_mode(display, DOUBLEBUF | OPENGL)
    pygame.display.set_caption("3D Vehicle Movement")

    # --- OpenGL Setup ---
    # Set a background color (light blue for a sky)
    glClearColor(0.5, 0.8, 1.0, 1.0)
    
    # Enable depth testing to make sure objects in front occlude objects behind
    glEnable(GL_DEPTH_TEST)

    # Set the perspective projection matrix
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    # Field of view = 45 degrees, aspect ratio, near clip, far clip
    gluPerspective(45, (display[0] / display[1]), 0.1, 150.0)
    
    # Switch back to the modelview matrix for object transformations
    glMatrixMode(GL_MODELVIEW)


    # --- Game Object Creation ---
    player = Vehicle(0, 0, 0)
    clock = pygame.time.Clock()

    # --- Main Game Loop ---
    while True:
        # --- Event Handling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                quit()

        # --- Update ---
        player.update()

        # --- Drawing ---
        # Reset the modelview matrix for this frame. This is crucial.
        glLoadIdentity()
        
        # --- Camera Setup ---
        # The camera should be positioned behind the player.
        # camera_pos = player_pos - (forward_vector * distance)
        # This translates to:
        cam_x = player.position[0] - 10 * (-math.sin(math.radians(player.angle)))
        cam_z = player.position[2] - 10 * (-math.cos(math.radians(player.angle)))
        gluLookAt(
            cam_x, 5, cam_z, # Camera Position (eye)
            player.position[0], player.position[1], player.position[2], # Look At point (center)
            0, 1, 0           # Up vector
        )

        # Clear the color and depth buffers
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # --- Draw Scene ---
        Ground()
        player.draw()

        # --- Display Update ---
        # This is where the OpenGL buffer is swapped to the screen
        pygame.display.flip() 
        
        # --- Frame Capture for gRPC ---
        # Get the dimensions of the Pygame window
        width, height = display

        # Read the raw pixel data directly from the OpenGL front buffer
        glReadBuffer(GL_FRONT)
        pixels = glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE)

        # Create a Pygame surface from the raw pixel data
        frame_surface = pygame.image.fromstring(pixels, (width, height), 'RGB')

        # OpenGL's origin is at the bottom-left, Pygame's is at the top-left.
        # We need to flip the image vertically.
        frame_surface_flipped = pygame.transform.flip(frame_surface, False, True)
        
        # Now, put the CORRECT surface into the queue
        try:
            frame_queue.get_nowait() # Clear old frame
        except queue.Empty:
            pass

        try:
            # Put the flipped surface, which contains the actual rendered image
            frame_queue.put_nowait(frame_surface_flipped)
        except queue.Full:
            pass

        clock.tick(60)

# --- Run the game ---
if __name__ == "__main__":
    main()
