import pygame
import math

# --- Initialization ---
# Initialize Pygame modules
pygame.init()

# --- Screen Setup ---
# Define screen dimensions
SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480
# Create the display surface
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("2D Top-Down Vehicle")

# --- Colors ---
# Define some basic colors for drawing
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
BACKGROUND_COLOR = (40, 40, 50) # A dark blue-grey

# --- Player Class ---
# This class will manage the vehicle's state and behavior
class Vehicle(pygame.sprite.Sprite):
    def __init__(self, x, y):
        """
        Initializes the vehicle.
        Args:
            x (int): The initial x-coordinate.
            y (int): The initial y-coordinate.
        """
        super().__init__()

        # --- Image and Rectangle ---
        # Create the original image of the vehicle (a rectangle).
        # We keep this original image to prevent quality loss during rotation.
        self.original_image = pygame.Surface((40, 20), pygame.SRCALPHA)
        pygame.draw.rect(self.original_image, RED, (0, 0, 40, 20))
        # Add a small triangle at the front to indicate direction
        pygame.draw.polygon(self.original_image, WHITE, [(40, 10), (30, 5), (30, 15)])
        
        # This is the image that will be rotated and drawn
        self.image = self.original_image
        # The rect is used for positioning the image
        self.rect = self.image.get_rect(center=(x, y))

        # --- Movement Attributes ---
        # Use a vector for more precise position tracking
        self.position = pygame.math.Vector2(x, y)
        self.direction = pygame.math.Vector2(1, 0) # Start facing right
        self.speed = 0.0
        self.tangential_speed = 0.0
        self.angle = 0.0
        
        # --- Control Constants ---
        self.max_speed = 2.0
        self.acceleration = 0.15
        self.friction = 0.05
        self.rotation_speed = 3.0

    def update(self):
        """
        Updates the vehicle's state each frame based on user input.
        """
        # Get the state of all keyboard buttons
        keys = pygame.key.get_pressed()

        # --- Acceleration and Deceleration ---
        # Accelerate forward
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            self.speed += self.acceleration
            # Clamp the speed to the maximum value
            if self.speed > self.max_speed:
                self.speed = self.max_speed
        # Accelerate backward (brake/reverse)
        elif keys[pygame.K_s] or keys[pygame.K_DOWN]:
            self.speed -= self.acceleration
            # Clamp the reverse speed
            if self.speed < -self.max_speed / 2:
                self.speed = -self.max_speed / 2
        # Apply friction if no acceleration key is pressed
        else:
            if self.speed > 0:
                self.speed -= self.friction
                if self.speed < 0:
                    self.speed = 0
            elif self.speed < 0:
                self.speed += self.friction
                if self.speed > 0:
                    self.speed = 0

        # Accelerate right
        if keys[pygame.K_d]:
            self.tangential_speed += self.acceleration
            # Clamp the speed to the maximum value
            if self.tangential_speed > self.max_speed:
                self.tangential_speed = self.max_speed
        # Accelerate backward (brake/reverse)
        elif keys[pygame.K_a]:
            self.tangential_speed -= self.acceleration
            # Clamp the reverse speed
            if self.tangential_speed < -self.max_speed / 2:
                self.tangential_speed = -self.max_speed / 2
        # Apply friction if no acceleration key is pressed
        else:
            if self.tangential_speed > 0:
                self.tangential_speed -= self.friction
                if self.tangential_speed < 0:
                    self.tangential_speed = 0
            elif self.tangential_speed < 0:
                self.tangential_speed += self.friction
                if self.tangential_speed > 0:
                    self.tangential_speed = 0

        # --- Rotation ---
        # Rotate left
        if keys[pygame.K_q]:
            self.angle += self.rotation_speed
        # Rotate right
        if keys[pygame.K_e]:
            self.angle -= self.rotation_speed
        
        # Keep angle between 0 and 360
        self.angle %= 360

        # --- Update Direction and Position ---
        # Rotate the direction vector based on the angle
        self.direction = pygame.math.Vector2(1, 0).rotate(-self.angle)
        tangential_direction = self.direction.rotate(90)
        
        # Update the position based on the direction and speed
        self.position += self.direction * self.speed
        self.position += tangential_direction * self.tangential_speed
        
        # --- Update Image and Rect for Drawing ---
        # Rotate the original image to prevent distortion
        self.image = pygame.transform.rotate(self.original_image, self.angle)
        # Update the rect's center to the new position
        self.rect = self.image.get_rect(center=self.position)

        # --- Screen Wrapping ---
        # If the vehicle goes off-screen, make it appear on the opposite side.
        if self.position.x > SCREEN_WIDTH:
            self.position.x = 0
        if self.position.x < 0:
            self.position.x = SCREEN_WIDTH
        if self.position.y > SCREEN_HEIGHT:
            self.position.y = 0
        if self.position.y < 0:
            self.position.y = SCREEN_HEIGHT


# --- Game Setup ---
# Create an instance of the vehicle
player = Vehicle(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
# Create a sprite group to manage the player
all_sprites = pygame.sprite.Group()
all_sprites.add(player)

# Create a clock to control the frame rate
clock = pygame.time.Clock()
running = True

# --- Main Game Loop ---
while running:
    # --- Event Handling ---
    # Process all events in the queue
    for event in pygame.event.get():
        # Check if the user wants to quit
        if event.type == pygame.QUIT:
            running = False

    # --- Update ---
    # Update all sprites in the group
    all_sprites.update()

    # --- Drawing ---
    # Fill the background with a solid color
    screen.fill(BACKGROUND_COLOR)
    
    # Draw all sprites onto the screen
    all_sprites.draw(screen)
    
    # --- Display Update ---
    # Flip the display to show the new frame
    pygame.display.flip()

    # --- Frame Rate Control ---
    # Limit the game to 60 frames per second
    clock.tick(60)

# --- Shutdown ---
# Quit Pygame and exit the program
pygame.quit()
