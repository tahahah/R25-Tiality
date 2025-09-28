from typing import Callable
import numpy as np
import pygame
import queue
import io
import time

def start_decoder_worker(incoming_video_queue: queue.Queue, decoded_video_queue: queue.Queue, decode_video_func, shutdown_event):
    print("Decoder thread started")
    while not shutdown_event.is_set():
        # Get frame from incoming queue
        try:
            frame_bytes = incoming_video_queue.get_nowait()
        except queue.Empty:
            continue

        decoded_frame = decode_video_func(frame_bytes)

        # Use a "dumping" pattern on the queue to ensure it only holds
        # the single most recent frame.
        try:
            # Clear any old frame that the GUI hasn't processed yet.
            decoded_video_queue.get_nowait()
        except queue.Empty:
            # The queue was already empty, which is fine.
            pass
        
        # Put the new, most recent frame into the queue.
        decoded_video_queue.put_nowait(decoded_frame)
    
    print("Decoder thread ending...")