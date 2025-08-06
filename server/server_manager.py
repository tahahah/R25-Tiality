import socket
import threading
import queue
from server_utils import _connection_manager_worker

class TialityServerManager:
    def __init__(self, server_ip, video_server_port, command_server_port):
        """
        Tiality Robot Server Manager

        The instance of this Class will operate on the main thread, while all workers w
        
        Args:
            server_ip (_type_): _description_
            server_port (_type_): _description_
        """
        self.server_ip = server_ip
        self.video_server_port = video_server_port
        self.command_server_port = command_server_port
        self.servers_active = False

        # Define shared, thread-safe queues
        self.video_queue = queue.Queue(maxsize=1)
        self.command_queue = queue.Queue(maxsize=2)

        # Define socket variables
        self._video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._command_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._connection_manager_thread = None

        # Define shutdown event to safely manage any threading issues
        self.shutdown_event = threading.Event()
        self.connection_established_event = threading.Event()

    def get_video_frame(self):
        if self.servers_active:
            try:
                new_frame = self.video_queue.get_nowait()
                return new_frame
            except queue.Empty:
                return None
        return None
    
    def send_command(self, command):
        if self.servers_active:
            try:
                # Clear any old command that hasn't been sent yet.
                self.command_queue.get_nowait() 
            except queue.Empty:
                # This is normal, the queue was already empty.
                pass

            try:
                # Put the newest, most relevant command into the queue.
                self.command_queue.put_nowait(command)
            except queue.Full:
                # Sender is processing a command already.
                pass
                

    def start_servers(self):
        """
        
        """   

        # Setup sockets for designated IP address and server ports
        self._video_socket.bind((self.server_ip, self.video_server_port))
        self._video_socket.listen()
        self._command_socket.bind((self.server_ip, self.command_server_port))
        self._command_socket.listen()

        # Create the command worker for this connection
        self._connection_manager_thread = threading.Thread(target=_connection_manager_worker, args=(self._video_socket, self.video_queue, self._command_socket, self.command_queue, self.connection_established_event, self.shutdown_event))
        self._connection_manager_thread.start()

        self.servers_active = True
            
    def close_servers(self):
        # Set threading event shutdown procedure
        self.shutdown_event.set()

        # Wait for threads to close
        self._connection_manager_thread.join()
        self.servers_active = False


        

