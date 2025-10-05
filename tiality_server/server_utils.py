import socket
import threading
import queue
from .grpc_video_streaming import server as video_server
from .grpc_video_streaming import decoder_worker as video_decoder
from .grpc_audio_streaming import server as audio_server
from .grpc_audio_streaming import decoder_worker as audio_decoder
from .command_streaming import publisher as command_publisher

def _connection_manager_worker(grpc_port, audio_grpc_port, incoming_video_queue, decoded_video_queue, 
                               incoming_audio_queue, mqtt_broker_host_ip, mqtt_port, 
                               vehicle_tx_topic, gimbal_tx_topic, rx_topic, command_queue, 
                               connection_established_event, shutdown_event, decode_video_func, 
                               num_decode_video_workers, enable_audio):
    """
    Thread to manage all connections including video, audio, and commands.
    
    Threads managed:
        1. gRPC Video Server Thread
        2. gRPC Audio Server Thread (if enabled)
        3. Video Decoder Worker Thread(s)
        4. Audio Decoder Worker Thread (if enabled)
        5. MQTT Command Publisher Thread
    """

    video_producer_thread = None
    audio_producer_thread = None
    video_decoder_threads = [None for _ in range(num_decode_video_workers)]
    audio_decoder_thread = None
    command_sender_thread = None

    try:
        while not shutdown_event.is_set():
            try:
                # Manage video producer thread
                if type(video_producer_thread) == type(None) or not video_producer_thread.is_alive():
                    print("Starting Video Connection...")
                    video_producer_thread = threading.Thread(
                        target=video_server.serve, 
                        args=(
                            grpc_port, 
                            incoming_video_queue,  
                            connection_established_event,
                            shutdown_event
                        ))
                    video_producer_thread.start()

                # Manage video decoder threads
                if None in video_decoder_threads:
                    for thread_id in range(num_decode_video_workers):
                        if type(video_decoder_threads[thread_id]) == type(None) or not video_decoder_threads[thread_id].is_alive():
                            video_decoder_threads[thread_id] = threading.Thread(
                                target=video_decoder.start_decoder_worker,
                                args=(
                                    incoming_video_queue,
                                    decoded_video_queue,
                                    decode_video_func,
                                    shutdown_event
                                )
                            )
                            video_decoder_threads[thread_id].start()

                # Manage audio producer thread (if enabled)
                if enable_audio:
                    # Try to initialize decoder once
                    if type(audio_decoder_thread) == type(None) or not audio_decoder_thread.is_alive():
                        # Import decoder here to handle missing dependencies gracefully
                        try:
                            from .grpc_audio_streaming.opus_decoder import AudioDecoder
                            # Use 1 channel to match the Pi's encoder settings
                            decoder = AudioDecoder(sample_rate=48000, channels=1)
                            
                            audio_decoder_thread = threading.Thread(
                                target=audio_decoder.start_audio_decoder_worker,
                                args=(
                                    incoming_audio_queue,
                                    decoder,
                                    shutdown_event,
                                    48000,  # sample_rate
                                    1       # channels
                                )
                            )
                            audio_decoder_thread.start()
                            print("Audio decoder thread started successfully")
                        except (ImportError, Exception) as e:
                            print(f"\n{'='*60}")
                            print(f"AUDIO DISABLED: {e}")
                            print(f"To enable audio, install PyOgg on the GUI machine:")
                            print(f"  pip install -r requirements.txt")
                            print(f"{'='*60}\n")
                            enable_audio = False  # Disable permanently for this session
                    
                    # Start audio server only if decoder initialized successfully
                    if enable_audio and (type(audio_producer_thread) == type(None) or not audio_producer_thread.is_alive()):
                        print("Starting Audio Connection...")
                        audio_producer_thread = threading.Thread(
                            target=audio_server.serve,
                            args=(
                                audio_grpc_port,
                                incoming_audio_queue,
                                connection_established_event,
                                shutdown_event
                            ))
                        audio_producer_thread.start()

                # Manage command sender thread
                if type(command_sender_thread) == type(None) or not command_sender_thread.is_alive():
                    print("Starting Command Sending Connection...")
                    command_sender_thread = threading.Thread(
                        target=command_publisher.publish_commands_worker, 
                        args=(
                            mqtt_port, 
                            mqtt_broker_host_ip, 
                            command_queue, 
                            vehicle_tx_topic,
                            gimbal_tx_topic, 
                            shutdown_event
                        ))
                    command_sender_thread.start()
                    connection_established_event.set()

            except Exception as e:
                print(f"Exception Encountered in Connection Manager: {e}")
                
    finally:
        print("Ensuring all threads successfully shutdown...")

        # Close video producer thread
        if video_producer_thread is not None and video_producer_thread.is_alive():
            video_producer_thread.join()

        # Close audio producer thread
        if audio_producer_thread is not None and audio_producer_thread.is_alive():
            audio_producer_thread.join()

        # Close video decoder threads
        for video_decoder_thread in video_decoder_threads:
            if video_decoder_thread is not None and video_decoder_thread.is_alive():
                video_decoder_thread.join()

        # Close audio decoder thread
        if audio_decoder_thread is not None and audio_decoder_thread.is_alive():
            audio_decoder_thread.join()

        # Close command sender thread
        if command_sender_thread is not None and command_sender_thread.is_alive():
            command_sender_thread.join()

        print("All connections shut down successfully")