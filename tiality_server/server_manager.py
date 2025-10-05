import threading
import queue
import logging
from typing import Callable
from .server_utils import _connection_manager_worker

class TialityServerManager:
    def __init__(self, grpc_port: int, mqtt_port: int, mqtt_broker_host_ip: str, 
                 decode_video_func, num_decode_video_workers: int,
                 enable_audio: bool = True, audio_grpc_port: int = 50052):
        """
        Tiality Robot Server Manager with Audio Support

        Args:
            grpc_port (int): Port for video streaming
            mqtt_port (int): Port for MQTT commands
            mqtt_broker_host_ip (str): MQTT broker IP
            decode_video_func (Callable): Function to decode video frames
            num_decode_video_workers (int): Number of video decoder workers
            enable_audio (bool): Whether to enable audio streaming
            audio_grpc_port (int): Port for audio streaming
        """
        self.servers_active = False
        self.decode_video_func = decode_video_func
        self.enable_audio = enable_audio
        
        assert num_decode_video_workers >= 1, "Must have at least one worker decoding video"
        self.num_decode_video_workers = num_decode_video_workers

        # Video queues
        self.incoming_video_queue = queue.Queue(maxsize=1)
        self.decoded_video_queue = queue.Queue(maxsize=1)
        
        # Audio queues (larger buffer for audio to prevent dropouts)
        self.incoming_audio_queue = queue.Queue(maxsize=100)  # 2 seconds of audio at 20ms packets
        
        # Command queue
        self.command_queue = queue.Queue(maxsize=5)

        # Network configuration
        self.grpc_port = grpc_port
        self.audio_grpc_port = audio_grpc_port
        self.mqtt_port = mqtt_port
        self.mqtt_broker_host_ip = mqtt_broker_host_ip
        
        # MQTT topics
        self.vehicle_tx_topic = "robot/tx"
        self.vehicle_rx_topic = "robot/rx"
        self.gimbal_tx_topic = "robot/gimbal/tx"
        self.gimbal_rx_topic = "robot/gimbal/rx"
        
        self._connection_manager_thread = None

        # Threading events
        self.shutdown_event = threading.Event()
        self.shutdown_event.clear()
        self.connection_established_event = threading.Event()

    def get_video_frame(self):
        """Get the most recent video frame"""
        if self.servers_active:
            try:
                new_frame = self.decoded_video_queue.get_nowait()
                return new_frame
            except queue.Empty:
                return None
        return None
    
    def get_audio_packet(self):
        """Get the next audio packet (FIFO)"""
        if self.servers_active and self.enable_audio:
            try:
                audio_packet = self.incoming_audio_queue.get_nowait()
                return audio_packet
            except queue.Empty:
                return None
        return None
    
    def send_command(self, command):
        """Send command via MQTT"""
        if self.servers_active:
            try:
                self.command_queue.put_nowait(command)
                logging.debug(f"Command queued successfully: {command[:50]}...")
            except queue.Full:
                try:
                    old_cmd = self.command_queue.get_nowait()
                    self.command_queue.put_nowait(command)
                    logging.warning(f"Queue full - replaced old command")
                except (queue.Empty, queue.Full):
                    logging.error(f"Failed to queue command")
                    pass

    def start_servers(self):
        """Start all server threads"""
        self._connection_manager_thread = threading.Thread(
            target=_connection_manager_worker, 
            args=(
                self.grpc_port,
                self.audio_grpc_port,
                self.incoming_video_queue,
                self.decoded_video_queue,
                self.incoming_audio_queue,
                self.mqtt_broker_host_ip, 
                self.mqtt_port, 
                self.vehicle_tx_topic,
                self.gimbal_tx_topic, 
                self.vehicle_rx_topic, 
                self.command_queue, 
                self.connection_established_event, 
                self.shutdown_event,
                self.decode_video_func,
                self.num_decode_video_workers,
                self.enable_audio
            ))
        self._connection_manager_thread.start()
        self.servers_active = True
            
    def close_servers(self):
        """Shutdown all server threads"""
        self.shutdown_event.set()
        self._connection_manager_thread.join()
        self.servers_active = False