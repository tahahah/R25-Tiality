import socket
import threading
import queue

def process_incoming_frame(encoded_frame):
    return encoded_frame.decode()

def _video_producer_worker(video_conn, video_queue, shutdown_event):
    
    with video_conn:
        video_conn.settimeout(1.0)
    
        # Maintain socket communication until a shutdown event is called
        while not shutdown_event.is_set():
            try:            
                # Wait for incoming data
                data = video_conn.recv(1024)

                # Decode incoming data into a frame
                decoded_frame = process_incoming_frame(data)
                if not data:
                    break
                # Clear queue if not empty
                try:
                    video_queue.get_nowait()
                except queue.Empty:
                    pass

                # Add decoded frame to video queue
                video_queue.put_nowait(decoded_frame)
            except socket.timeout:
                continue


def _command_sender_worker(command_conn, command_queue, shutdown_event):
    with command_conn:
        command_conn.settimeout(1.0)
    
        # Maintain socket communication until a shutdown event is called
        while not shutdown_event.is_set():
            try:            
                # Attempt to retrieve new command
                command = command_queue.get_nowait()

                # Send command when available
                command_conn.sendall(command.encode())
            except queue.Empty:
                # No command in queue
                continue
            except socket.timeout:
                continue

def _connection_manager_worker(video_socket, video_queue, command_socket, command_queue, connection_established_event, shutdown_event):

    video_producer_thread = None
    command_sender_thread = None

    try:
        while not shutdown_event.is_set():
            print("Waiting for Connection")
            try:
                # Await connections from the Tiality
                video_conn, __ = video_socket.accept()
                command_conn, __ = command_socket.accept()
                connection_established_event.set()

                # Create the video worker for this connection
                video_producer_thread = threading.Thread(target=_video_producer_worker, args=(video_conn, video_queue, shutdown_event))
                video_producer_thread.start()

                # Create the command worker for this connection
                command_sender_thread = threading.Thread(target=_command_sender_worker, args=(command_conn, command_queue, shutdown_event))
                command_sender_thread.start()

            finally:
                connection_established_event.clear()
    finally:
        # Close video thread and socket
        if video_producer_thread is not None and video_producer_thread.is_alive():
            video_producer_thread.join()
        video_socket.close()

        # Close command thread and socket
        if command_sender_thread is not None and command_sender_thread.is_alive():
            command_sender_thread.join()
        command_socket.close()



    