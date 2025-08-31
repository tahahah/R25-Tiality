import pygame
import queue
import threading
import io
import time
import tiality_server
import json
import numpy as np
import cv2

def decode_video_frame_pygame(frame_bytes):
    byte_io = io.BytesIO(frame_bytes)
    frame_surface = pygame.image.load(byte_io)
    return frame_surface

def decode_video_frame_opencv(frame_bytes: bytes) -> pygame.Surface:
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

def run_pygame_display(server_manager: tiality_server.TialityServerManager):
    """
    Main function to run the Pygame display loop.
    This function is intended to be called from a main script.
    It takes a thread-safe queue as an argument and displays frames from it.
    """
    # 1. Initialize Pygame and set up the display.
    pygame.init()
    screen_width, screen_height = 640, 480
    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption("Robot Video Feed")
    font = pygame.font.Font(None, 50)
    clock = pygame.time.Clock()

    # 2. Main Pygame display loop.
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                server_manager.close_servers()

        pygame_keys = pygame.key.get_pressed()
        keys = {}
        keys["up"] = pygame_keys[pygame.K_w] or pygame_keys[pygame.K_UP]
        keys["down"] = pygame_keys[pygame.K_s] or pygame_keys[pygame.K_DOWN]
        keys["rotate_left"] = pygame_keys[pygame.K_q]
        keys["rotate_right"] = pygame_keys[pygame.K_e]
        keys["left"] = pygame_keys[pygame.K_a]
        keys["right"] = pygame_keys[pygame.K_d]
        json_string = json.dumps(keys)
        encoded_string = json_string.encode()
        server_manager.send_command(encoded_string)


        # --- Frame Display Logic ---
        # Try to get the latest frame from the queue without blocking.
        frame_surface = server_manager.get_video_frame()
        if frame_surface is not None:
            try:
                
                # Resize and draw the frame.
                frame_rect = frame_surface.get_rect()
                fit_rect = frame_rect.fit(screen.get_rect())
                screen.fill((0, 0, 0)) # Black background
                screen.blit(pygame.transform.scale(frame_surface, fit_rect.size), fit_rect)
            except pygame.error as e:
                print(f"Pygame Error: {e}")


        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    print("Pygame window closed.")
    quit()


# --- Example Usage ---
# The following code demonstrates how you would use the run_pygame_display function
# in your main application alongside the gRPC server.


if __name__ == '__main__':
    # This is how you would structure your main application script.
    
    # 1. Create the shared queue.
    shared_frame_queue = queue.Queue(maxsize=1)

    # 2. Create and start the gRPC server thread.
    #    (Here we use the placeholder for demonstration).
    manger = tiality_server.TialityServerManager(
        grpc_port = 50051, 
        mqtt_port = 1883, 
        mqtt_broker_host_ip = "localhost",
        decode_video_func = decode_video_frame_opencv,
        num_decode_video_workers = 1 # Don't change this for now
        )
    manger.start_servers()
    # 3. Run the Pygame display on the main thread.
    #    It will now get its frames from the queue populated by the server thread.
    run_pygame_display(manger)

    print("Application shutting down.")
