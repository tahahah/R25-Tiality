import queue
import numpy as np

def start_decoder_worker(incoming_audio_queue: queue.Queue, decoded_audio_queue: queue.Queue, decode_audio_func, shutdown_event):
    """
    Worker thread that decodes incoming Opus audio packets to PCM.
    
    Args:
        incoming_audio_queue: Queue containing encoded Opus packets
        decoded_audio_queue: Queue for decoded PCM audio data
        decode_audio_func: Function to decode Opus to PCM
        shutdown_event: Event to signal shutdown
    """
    print("Audio decoder thread started")
    while not shutdown_event.is_set():
        # Get packet from incoming queue
        try:
            packet_info = incoming_audio_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        try:
            # Decode the audio packet
            decoded_audio = decode_audio_func(packet_info['data'])
            
            # Prepare decoded packet with metadata
            decoded_packet = {
                'audio_data': decoded_audio,
                'timestamp': packet_info['timestamp'],
                'sequence_number': packet_info['sequence_number'],
                'algorithm_delay': packet_info['algorithm_delay']
            }
            
            # Use a "dumping" pattern on the queue to ensure it only holds
            # the single most recent packet.
            try:
                # Clear any old packet that hasn't been processed yet.
                decoded_audio_queue.get_nowait()
            except queue.Empty:
                # The queue was already empty, which is fine.
                pass
            
            # Put the new, most recent packet into the queue.
            decoded_audio_queue.put_nowait(decoded_packet)
            
        except Exception as e:
            print(f"Error decoding audio packet: {e}")
            continue
    
    print("Audio decoder thread ending...")
