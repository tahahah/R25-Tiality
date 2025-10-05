import socket
import threading
import queue
from .grpc_video_streaming import server as video_server
from .grpc_video_streaming import decoder_worker
from .command_streaming import publisher as command_publisher

def _connection_manager_worker(grpc_port, incoming_video_queue, decoded_video_queue, grpc_audio_port, incoming_audio_queue, decoded_audio_queue, mqtt_broker_host_ip, mqtt_port, vehicle_tx_topic, gimbal_tx_topic, rx_topic, command_queue, connection_established_event, shutdown_event, decode_video_func, num_decode_video_workers):
    """
    Thread to manage all connections.
    These threads include:
        1. GRPC Video Server Thread
        2. GRPC Audio Server Thread

    Args:
        grpc_port (_type_): _description_
        incoming_video_queue (_type_): _description_
        decoded_video_queue (_type_): _description_
        grpc_audio_port (_type_): _description_
        incoming_audio_queue (_type_): _description_
        decoded_audio_queue (_type_): _description_
        mqtt_broker_host_ip (_type_): _description_
        mqtt_port (_type_): _description_
        vehicle_tx_topic (_type_): Vehicle movement commands topic
        gimbal_tx_topic (_type_): Gimbal control commands topic
        rx_topic (_type_): _description_
        command_queue (_type_): _description_
        connection_established_event (_type_): _description_
        shutdown_event (_type_): _description_
        decode_video_func (_type_): _description_
        num_decode_video_workers (_type_): _description_
    """

    video_producer_thread = None
    video_decoder_threads = [None for _ in range(num_decode_video_workers)]
    command_sender_thread = None
    audio_producer_thread = None
    audio_decoder_threads = [None]

    try:
        while not shutdown_event.is_set():
            try:
                if type(video_producer_thread) == type(None) or not video_producer_thread.is_alive():
                    print("Waiting for Video Connection")
                    # Create the video worker for this connection
                    video_producer_thread = threading.Thread(
                        target=video_server.serve, 
                        args=(
                            grpc_port, 
                            incoming_video_queue,  
                            connection_established_event,
                            shutdown_event
                            ))
                    video_producer_thread.start()

                if type(audio_producer_thread) == type(None) or not audio_producer_thread.is_alive():
                    from .grpc_audio_streaming import server as audio_server
                    audio_producer_thread = threading.Thread(
                        target=audio_server.serve,
                        args=(grpc_audio_port, incoming_audio_queue, connection_established_event, shutdown_event)
                    )
                    audio_producer_thread.start()

                if None in video_decoder_threads:
                    for thread_id in range(num_decode_video_workers):
                        if type(video_decoder_threads[thread_id]) == type(None) or not video_decoder_threads[thread_id].is_alive():
                            video_decoder_threads[thread_id] = threading.Thread(
                                target=decoder_worker.start_decoder_worker,
                                args=(
                                    incoming_video_queue,
                                    decoded_video_queue,
                                    decode_video_func,
                                    shutdown_event
                                )
                            )
                            video_decoder_threads[thread_id].start()
                        
                if None in audio_decoder_threads:
                    for thread_id in range(num_decode_audio_workers):
                        if type(audio_decoder_threads[thread_id]) == type(None) or not audio_decoder_threads[thread_id].is_alive():
                            audio_decoder_threads[thread_id] = threading.Thread(
                                target=decoder_worker.start_decoder_worker,
                                args=(
                                    incoming_audio_queue,
                                    decoded_audio_queue,
                                    decode_audio_func,
                                    shutdown_event
                                )
                            )
                            audio_decoder_threads[thread_id].start()

                # Close command thread and socket
                if type(command_sender_thread) == type(None) or not command_sender_thread.is_alive():
                    print("Waiting for Command Sending Connection")
                    # Create the command worker for this connection
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
                print(f"Exception Encountered: {e}")
    finally:
        print("Ensuring Threads successfully shutdown")

        # Close video thread and socket
        if video_producer_thread is not None and video_producer_thread.is_alive():
            video_producer_thread.join()

        # Close video thread and socket
        for video_decoder_thread in video_decoder_threads:
            if video_decoder_thread is not None and video_decoder_thread.is_alive():
                video_decoder_thread.join()

        # Close command thread and socket
        if command_sender_thread is not None and command_sender_thread.is_alive():
            command_sender_thread.join()

        print("Connections shut down")


    