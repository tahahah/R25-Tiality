import sounddevice as sd
import sys
import os
import queue
import time
import threading

# Add your audio modules to path so they can be imported directly
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ALSA_Capture_Stream'))

# Import your existing audio modules (direct imports work because we added to sys.path)
from capture_object import CaptureObject
from encoder_object import EncoderObject
import settings

def pi_audio_manager_worker(server_addr, packet_generator_func):
    """
    Captures audio from ALSA device, encodes with Opus, and streams via gRPC
    """
    import tiality_server
    
    reconnect_delay_seconds = 0.5
    max_reconnect_delay_seconds = 5.0
    
    # Setup queues and threads
    audio_packet_queue = queue.Queue(maxsize=100)  # Buffer for 2 seconds of audio
    audio_thread = threading.Thread(
        target=tiality_server.audio_client.run_grpc_audio_client,
        args=(server_addr, audio_packet_queue, packet_generator_func),
        daemon=True
    )
    audio_thread.start()
    
    while True:
        capture = None
        try:
            # Initialize settings
            settings.init()
            
            # Configure channel settings (must be after init())
            settings.captured_channels = 1
            settings.encoded_channels = 1
            
            # Setup your interface (adjust as needed)
            interface = {"card": 3, "device": 0}
            
            # Create buffers
            capture_buffer = bytearray(settings.frame_bytes * settings.captured_channels)
            encoder_buffer = bytearray(settings.frame_bytes * settings.encoded_channels)
            
            # Create capture and encoder objects
            capture = CaptureObject(capture_buffer, interface)
            encoder = EncoderObject(capture_buffer, encoder_buffer)
            
            capture.start()
            print("Audio capture started")
            
            # Reset backoff
            reconnect_delay_seconds = 0.5
            consecutive_failures = 0
            
            # Capture loop
            while True:
                try:
                    # Read from audio device
                    capture.read()
                    
                    # Encode the audio
                    header = encoder.encode()
                    
                    # Create packet
                    packet = {
                        'audio_data': bytes(encoder_buffer[0:header["packet_length"]]),
                        'timestamp': header["timestamp"],
                        'sequence_number': header["sequence_number"],
                        'packet_length': header["packet_length"],
                        'algorithm_delay': header["algorithm_delay"]
                    }
                    
                    # Put packet in queue
                    try:
                        # Remove old packet if queue is full
                        if audio_packet_queue.full():
                            audio_packet_queue.get_nowait()
                        audio_packet_queue.put_nowait(packet)
                    except queue.Full:
                        pass  # Drop packet if still full
                    
                    consecutive_failures = 0
                    
                except Exception as e:
                    consecutive_failures += 1
                    print(f"Audio capture error: {e}")
                    time.sleep(0.05)
                    
                    if consecutive_failures >= 10:
                        raise RuntimeError("Repeated audio capture failures")
                        
        except Exception as e:
            print(f"Audio manager error (will retry): {e}")
            if capture:
                try:
                    capture.stop()
                except:
                    pass
            time.sleep(reconnect_delay_seconds)
            reconnect_delay_seconds = min(max_reconnect_delay_seconds, reconnect_delay_seconds * 2)
            continue
        finally:
            if capture:
                try:
                    capture.stop()
                except:
                    pass


def audio_packet_generator(packet_queue: queue.Queue):
    """
    Generator function that yields AudioPacket messages from queue
    """
    import tiality_server
    
    print("Audio packet generator started...")
    while True:
        packet_data = packet_queue.get()
        
        if packet_data is None:
            print("Stopping audio packet generator.")
            break
        
        try:
            yield tiality_server.audio_streaming_pb2.AudioPacket(
                audio_data=packet_data['audio_data'],
                timestamp=packet_data['timestamp'],
                sequence_number=packet_data['sequence_number'],
                packet_length=packet_data['packet_length'],
                algorithm_delay=packet_data['algorithm_delay']
            )
        except Exception as e:
            print(f"Error creating audio packet: {e}")