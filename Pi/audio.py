import tiality_server
import queue
import time
import threading
import grpc
import sys
import os

# Add ALSA_Capture_Stream to path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
alsa_path = os.path.join(parent_dir, 'ALSA_Capture_Stream')
sys.path.insert(0, alsa_path)

try:
    import settings
    from capture_object import CaptureObject
    from encoder_object import EncoderObject
except ImportError as e:
    print(f"Error importing ALSA_Capture_Stream modules: {e}")
    print("Make sure ALSA_Capture_Stream dependencies are installed.")
    raise

def pi_audio_manager_worker(server_addr, packet_generator_func, device_config=None):
    """
    Initialize audio capture from ALSA device and continuously capture and encode
    audio packets, keeping only the most recent packet in the provided queue.
    
    Args:
        server_addr: Address of the gRPC server (GUI)
        packet_generator_func: Function to generate AudioPacket messages from queue
        device_config: Dict with 'card' and 'device' keys (default: {"card": 1, "device": 0})
    
    Robust to microphone not being initially available or disconnecting: attempts
    to (re)initialize with exponential backoff and restarts on repeated
    capture failures.
    """
    reconnect_delay_seconds = 0.5
    max_reconnect_delay_seconds = 5.0
    
    # Default device configuration for the 4-channel microphone
    if device_config is None:
        device_config = {"card": 1, "device": 0}
    
    # Setup thread safe queues and start gRPC client
    audio_packet_queue = queue.Queue(maxsize=5)  # Buffer a few packets
    audio_thread = threading.Thread(
        target=tiality_server.audio_client.run_grpc_audio_client,
        args=(server_addr, audio_packet_queue, packet_generator_func),
        daemon=True
    )
    audio_thread.start()
    
    while True:
        capture = None
        encoder = None
        try:
            # Initialize settings
            settings.init()
            settings.captured_channels = 4  # 4-channel microphone
            settings.encoded_channels = 2   # Encode to stereo
            
            # Create buffers
            capture_buffer = bytearray(settings.frame_bytes * settings.captured_channels)
            encoder_buffer = bytearray(settings.frame_bytes * settings.encoded_channels)
            
            # Create capture and encoder objects
            capture = CaptureObject(capture_buffer, device_config)
            encoder = EncoderObject(capture_buffer, encoder_buffer)
            
            # Start capture
            capture.start()
            print(f"Audio capture started: {settings.sample_rate}Hz, "
                  f"{settings.captured_channels} channels → {settings.encoded_channels} channels")
            
            # Reset backoff on successful start
            reconnect_delay_seconds = 0.5
            consecutive_failures = 0
            
            # Capture and encode loop
            while True:
                try:
                    # Fill buffer with audio data
                    capture.read()
                    
                    # Encode buffer to Opus
                    header = encoder.encode()
                    
                    # Create packet with data and metadata
                    packet = {
                        'data': bytes(encoder_buffer[0:header["packet_length"]]),
                        'timestamp': header['timestamp'],
                        'sequence_number': header['sequence_number'],
                        'algorithm_delay': header['algorithm_delay']
                    }
                    
                    # Put packet in queue (drop oldest if full)
                    try:
                        audio_packet_queue.put_nowait(packet)
                    except queue.Full:
                        # Drop oldest packet and add new one
                        try:
                            audio_packet_queue.get_nowait()
                            audio_packet_queue.put_nowait(packet)
                        except (queue.Empty, queue.Full):
                            pass
                    
                    consecutive_failures = 0
                    
                except Exception as e:
                    consecutive_failures += 1
                    print(f"Audio capture error: {e}")
                    time.sleep(0.05)
                    
                    # If too many consecutive failures, force a reconnect
                    if consecutive_failures >= 10:
                        raise RuntimeError("Repeated audio capture failures; restarting")
                        
        except Exception as e:
            # Log and attempt reconnect with backoff
            print(f"Audio manager error (will retry): {e}")
            try:
                if capture is not None:
                    capture.stop()
            except Exception:
                pass
            
            # Exponential backoff capped for Pi Zero 2 friendliness
            time.sleep(reconnect_delay_seconds)
            reconnect_delay_seconds = min(max_reconnect_delay_seconds, reconnect_delay_seconds * 2)
            continue
            
        finally:
            # Ensure capture is stopped before next reconnect attempt
            try:
                if capture is not None:
                    capture.stop()
            except Exception:
                pass


def packet_generator_alsa(packet_queue: queue.Queue):
    """
    A generator function that gets audio packets from a thread-safe queue
    and yields them as AudioPacket messages.
    """
    print("Audio packet generator started. Waiting for packets from the queue...")
    while True:
        # Block until a packet is available in the queue.
        packet = packet_queue.get()
        
        # If a sentinel value (e.g., None) is received, stop the generator.
        if packet is None:
            print("Stopping audio packet generator.")
            break
        
        try:
            # Yield the packet data in the format expected by the .proto file.
            yield tiality_server.audio_streaming_pb2.AudioPacket(
                packet_data=packet['data'],
                timestamp=packet['timestamp'],
                sequence_number=packet['sequence_number'],
                algorithm_delay=packet['algorithm_delay']
            )
            
        except Exception as e:
            print(f"Error creating audio packet: {e}")
