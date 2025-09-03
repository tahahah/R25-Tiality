import threading
import queue
from typing import Callable
from .server_utils import _connection_manager_worker

class TialityServerManager:
    def __init__(self, grpc_port: int, mqtt_port: int, mqtt_broker_host_ip: str, decode_video_func, num_decode_video_workers: int):
        """
        Tiality Robot Server Manager

        The instance of this Class will operate on the main thread, while all workers spawned will be controlled by the Connection Manager THread

        Args:
            grpc_port (int): _description_
            mqtt_port (int): _description_
            mqtt_broker_host_ip (str): _description_
            decode_video_func (Callable): _description_
            num_decode_video_workers (int): KEEP THIS AT 1 FOR NOW, DOES NOT SCALE WELL
        """
        self.servers_active = False
        self.decode_video_func = decode_video_func
        assert num_decode_video_workers >= 1, "Must have at least one worker decoding video"
        self.num_decode_video_workers = num_decode_video_workers

        # Define shared, thread-safe queues
        self.incoming_video_queue = queue.Queue(maxsize=1)
        self.decoded_video_queue = queue.Queue(maxsize=1)
        self.command_queue = queue.Queue(maxsize=1)

        # Change to your Raspberry Pi's IP
        self.grpc_port = grpc_port
        self.mqtt_port = mqtt_port
        self.mqtt_broker_host_ip = mqtt_broker_host_ip  # Change to your laptop/host running Mosquitto
        self.tx_topic = "robot/tx"
        self.rx_topic = "robot/rx"
        
        self._connection_manager_thread = None

        # Define shutdown event to safely manage any threading issues
        self.shutdown_event = threading.Event()
        self.shutdown_event.clear()
        self.connection_established_event = threading.Event()

    def get_video_frame(self):
        if self.servers_active:
            try:
                new_frame = self.decoded_video_queue.get_nowait()
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

        # Create the command worker for this connection
        self._connection_manager_thread = threading.Thread(
            target=_connection_manager_worker, 
            args=(
                self.grpc_port, 
                self.incoming_video_queue,
                self.decoded_video_queue, 
                self.mqtt_broker_host_ip, 
                self.mqtt_port, 
                self.tx_topic, 
                self.rx_topic, 
                self.command_queue, 
                self.connection_established_event, 
                self.shutdown_event,
                self.decode_video_func,
                self.num_decode_video_workers))
        self._connection_manager_thread.start()

        self.servers_active = True
            
    def close_servers(self):
        # Set threading event shutdown procedure
        self.shutdown_event.set()

        # Wait for threads to close
        self._connection_manager_thread.join()
        self.servers_active = False