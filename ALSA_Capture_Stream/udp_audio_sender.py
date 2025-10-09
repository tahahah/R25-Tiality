import socket
import struct
import logging
from typing import Optional
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UDPAudioSender:
    """Sends encoded audio packets via UDP for low-latency streaming."""
    HEADER_FORMAT = '!IQH'  # seq_num(4), timestamp(8), data_len(2)
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    MAX_UDP_PACKET_SIZE = 1400  # Avoid UDP fragmentation (MTU ~1500)
    
    def __init__(
        self,
        target_host: str,
        target_port: int = 5005,
        local_port: int = 0  # 0 = let OS choose
    ):
        """
        Initialize UDP audio sender.
        
        Args:
            target_host: Destination hostname or IP
            target_port: Destination UDP port
            local_port: Local port to bind (0 for automatic)
        """
        self.target_host = target_host
        self.target_port = target_port
        self.local_port = local_port
        
        # Create non-blocking UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if local_port > 0:
            self.socket.bind(('', local_port))
        self.socket.setblocking(False)
        
        # Statistics
        self.packets_sent = 0
        self.bytes_sent = 0
        self.stats_lock = Lock()
        
        logger.info(f"UDP Audio Sender initialized: {target_host}:{target_port}")
    
    def send_packet(self, header: dict, audio_data: bytes) -> bool:
        """
        Send a single audio packet via UDP.
        
        Args:
            header: Packet header dict with 'sequence_number' and 'timestamp'
            audio_data: Encoded audio data bytes
            
        Returns:
            True if packet sent successfully, False otherwise
        """
        try:
            sequence_number = header.get('sequence_number', 0)
            timestamp = header.get('timestamp', 0)
            data_length = len(audio_data)
            
            # Truncate if packet too large
            total_size = self.HEADER_SIZE + data_length
            if total_size > self.MAX_UDP_PACKET_SIZE:
                logger.warning(f"Packet too large ({total_size}B), truncating")
                max_data_size = self.MAX_UDP_PACKET_SIZE - self.HEADER_SIZE
                audio_data = audio_data[:max_data_size]
                data_length = len(audio_data)
            
            # Pack and send
            packet = struct.pack(
                self.HEADER_FORMAT,
                sequence_number,
                timestamp,
                data_length
            ) + audio_data
            
            self.socket.sendto(packet, (self.target_host, self.target_port))
            
            with self.stats_lock:
                self.packets_sent += 1
                self.bytes_sent += len(packet)
            
            return True
            
        except BlockingIOError:
            logger.debug("Socket buffer full, packet dropped")
            return False
        except Exception as e:
            logger.error(f"Error sending UDP packet: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Get sender statistics."""
        with self.stats_lock:
            return {
                'packets_sent': self.packets_sent,
                'bytes_sent': self.bytes_sent,
                'target': f"{self.target_host}:{self.target_port}"
            }
    
    def reset_stats(self) -> None:
        """Reset statistics counters."""
        with self.stats_lock:
            self.packets_sent = 0
            self.bytes_sent = 0
    
    def close(self) -> None:
        """Close the UDP socket."""
        try:
            self.socket.close()
            logger.info("UDP Audio Sender closed")
        except Exception as e:
            logger.error(f"Error closing UDP sender: {e}")


if __name__ == "__main__":
    sender = UDPAudioSender("localhost", 5005)
    test_header = {'sequence_number': 0, 'timestamp': 123456789}
    test_data = b'\x00' * 100
    
    if sender.send_packet(test_header, test_data):
        print("Test packet sent")
        print(f"Stats: {sender.get_stats()}")
    
    sender.close()
