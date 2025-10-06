import socket
import struct
import logging
from typing import Optional
from threading import Lock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UDPAudioSender:
    """Sends encoded audio packets via UDP for low-latency streaming."""
    
    # Packet structure: [sequence_number (4 bytes)][timestamp (8 bytes)][data_length (2 bytes)][audio_data]
    HEADER_FORMAT = '!IQH'  # unsigned int, unsigned long long, unsigned short
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    MAX_UDP_PACKET_SIZE = 1400  # Safe size to avoid fragmentation (MTU is typically 1500)
    
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
        
        # Create UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if local_port > 0:
            self.socket.bind(('', local_port))
        
        # Set socket to non-blocking mode for better performance
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
            # Extract header info
            sequence_number = header.get('sequence_number', 0)
            timestamp = header.get('timestamp', 0)
            data_length = len(audio_data)
            
            # Check if packet would be too large
            total_size = self.HEADER_SIZE + data_length
            if total_size > self.MAX_UDP_PACKET_SIZE:
                logger.warning(f"Packet too large ({total_size} bytes), truncating to {self.MAX_UDP_PACKET_SIZE}")
                max_data_size = self.MAX_UDP_PACKET_SIZE - self.HEADER_SIZE
                audio_data = audio_data[:max_data_size]
                data_length = len(audio_data)
            
            # Pack header + data
            packet_header = struct.pack(
                self.HEADER_FORMAT,
                sequence_number,
                timestamp,
                data_length
            )
            packet = packet_header + audio_data
            
            # Send packet
            self.socket.sendto(packet, (self.target_host, self.target_port))
            
            # Update statistics
            with self.stats_lock:
                self.packets_sent += 1
                self.bytes_sent += len(packet)
            
            return True
            
        except BlockingIOError:
            # Socket buffer full, skip this packet
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
    # Simple test
    sender = UDPAudioSender("localhost", 5005)
    
    # Send test packet
    test_header = {'sequence_number': 0, 'timestamp': 123456789}
    test_data = b'\x00' * 100
    
    if sender.send_packet(test_header, test_data):
        print("Test packet sent successfully")
        print(f"Stats: {sender.get_stats()}")
    
    sender.close()
