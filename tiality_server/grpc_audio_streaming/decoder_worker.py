import queue
import sounddevice as sd
import numpy as np

def start_audio_decoder_worker(incoming_audio_queue, decoder, shutdown_event, sample_rate=48000, channels=1):
    """
    Worker that decodes Opus audio packets and plays them
    """
    print("Audio decoder thread started")
    
    # Create audio output stream
    output_stream = sd.RawOutputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype='int16'
    )
    output_stream.start()
    
    try:
        while not shutdown_event.is_set():
            try:
                # Get audio packet from queue (blocking with timeout)
                packet_data = incoming_audio_queue.get(timeout=0.1)
                
                # Decode the Opus packet
                decoded_audio = decoder.decode(packet_data['audio_data'])
                
                # Play the decoded audio
                output_stream.write(decoded_audio)
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error decoding/playing audio: {e}")
                continue
                
    finally:
        output_stream.stop()
        output_stream.close()
        print("Audio decoder thread ending...")