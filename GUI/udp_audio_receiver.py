import socket
import struct
import logging
import threading
import sounddevice as sd
import numpy as np
from queue import Queue, Empty
from typing import Optional
import sys
import os

# Add parent directory to path to import decoder
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UDPAudioReceiver:
    """Receives and plays encoded audio packets via UDP."""
    
    # Must match sender's header format
    HEADER_FORMAT = '!IQH'  # unsigned int, unsigned long long, unsigned short
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    MAX_PACKET_SIZE = 2048
    
    def __init__(
        self,
        listen_port: int = 5005,
        sample_rate: int = 48000,
        channels: int = 1,
        jitter_buffer_size: int = 10,  # Number of packets to buffer
        playback_enabled: bool = True
    ):
        """
        Initialize UDP audio receiver.
        
        Args:
            listen_port: UDP port to listen on
            sample_rate: Audio sample rate (must match encoder)
            channels: Number of audio channels
            jitter_buffer_size: Number of packets to buffer before playing
            playback_enabled: Whether to enable audio playback
        """
        self.listen_port = listen_port
        self.sample_rate = sample_rate
        self.channels = channels
        self.jitter_buffer_size = jitter_buffer_size
        self.playback_enabled = playback_enabled
        
        # Create UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)  # Increase receive buffer
        self.socket.bind(('', listen_port))
        self.socket.settimeout(0.1)  # Non-blocking with timeout
        
        # Packet queue for jitter buffering
        self.packet_queue = Queue(maxsize=100)
        
        # Playback buffer
        self.playback_queue = Queue(maxsize=50)
        
        # Threading
        self.running = False
        self.receive_thread: Optional[threading.Thread] = None
        self.decode_thread: Optional[threading.Thread] = None
        self.playback_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.packets_received = 0
        self.packets_dropped = 0
        self.bytes_received = 0
        self.last_sequence_number = -1
        
        # Decoder (lazy init)
        self.decoder = None
        
        logger.info(f"UDP Audio Receiver initialized on port {listen_port}")
    
    def _init_decoder(self):
        """Lazy initialize the Opus decoder."""
        if self.decoder is None:
            try:
                # Import here to avoid issues if PyOgg not available on GUI machine
                from ALSA_Capture_Stream.decoder_object import DecoderObject
                import ALSA_Capture_Stream.settings as settings
                
                # Initialize settings
                settings.init()
                settings.sample_rate = self.sample_rate
                settings.encoded_channels = self.channels
                
                self.decoder = DecoderObject()
                logger.info("Opus decoder initialized")
            except ImportError as e:
                logger.error(f"Failed to import decoder: {e}")
                logger.info("Install PyOgg and dependencies on GUI machine for decoding")
                raise
    
    def start(self) -> None:
        """Start receiving and playing audio."""
        if self.running:
            logger.warning("Receiver already running")
            return
        
        self.running = True
        
        # Start receive thread
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        
        # Start decode thread
        self.decode_thread = threading.Thread(target=self._decode_loop, daemon=True)
        self.decode_thread.start()
        
        # Start playback thread if enabled
        if self.playback_enabled:
            self.playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
            self.playback_thread.start()
        
        logger.info("UDP Audio Receiver started")
    
    def stop(self) -> None:
        """Stop receiving and playing audio."""
        self.running = False
        
        # Wait for threads to finish
        if self.receive_thread:
            self.receive_thread.join(timeout=1.0)
        if self.decode_thread:
            self.decode_thread.join(timeout=1.0)
        if self.playback_thread:
            self.playback_thread.join(timeout=1.0)
        
        logger.info("UDP Audio Receiver stopped")
    
    def _receive_loop(self) -> None:
        """Thread loop for receiving UDP packets."""
        logger.info("Receive loop started")
        
        while self.running:
            try:
                # Receive packet
                data, addr = self.socket.recvfrom(self.MAX_PACKET_SIZE)
                
                if len(data) < self.HEADER_SIZE:
                    logger.warning(f"Packet too small: {len(data)} bytes")
                    continue
                
                # Unpack header
                header_bytes = data[:self.HEADER_SIZE]
                sequence_number, timestamp, data_length = struct.unpack(
                    self.HEADER_FORMAT, header_bytes
                )
                
                # Extract audio data
                audio_data = data[self.HEADER_SIZE:self.HEADER_SIZE + data_length]
                
                # Check for packet loss
                if self.last_sequence_number >= 0:
                    expected = self.last_sequence_number + 1
                    if sequence_number != expected:
                        lost = sequence_number - expected
                        self.packets_dropped += lost
                        logger.debug(f"Packet loss detected: {lost} packets")
                
                self.last_sequence_number = sequence_number
                
                # Queue packet for decoding
                packet = {
                    'sequence_number': sequence_number,
                    'timestamp': timestamp,
                    'data': audio_data
                }
                
                try:
                    self.packet_queue.put_nowait(packet)
                    self.packets_received += 1
                    self.bytes_received += len(data)
                except:
                    # Queue full, drop packet
                    self.packets_dropped += 1
                    
            except socket.timeout:
                # No data received, continue
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error in receive loop: {e}")
        
        logger.info("Receive loop stopped")
    
    def _decode_loop(self) -> None:
        """Thread loop for decoding audio packets."""
        logger.info("Decode loop started")
        
        # Initialize decoder
        try:
            self._init_decoder()
        except Exception as e:
            logger.error(f"Failed to initialize decoder: {e}")
            return
        
        while self.running:
            try:
                # Get packet from queue
                packet = self.packet_queue.get(timeout=0.1)
                
                # Decode audio
                decoded_audio = self.decoder.decode(packet['data'])
                
                # Convert to numpy array
                audio_array = np.frombuffer(decoded_audio, dtype=np.int16)
                
                # Reshape for multi-channel if needed
                if self.channels > 1:
                    audio_array = audio_array.reshape(-1, self.channels)
                
                # Queue for playback
                playback_packet = {
                    'sequence_number': packet['sequence_number'],
                    'audio': audio_array
                }
                
                try:
                    self.playback_queue.put_nowait(playback_packet)
                except:
                    # Playback queue full, drop packet
                    pass
                    
            except Empty:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error in decode loop: {e}")
        
        logger.info("Decode loop stopped")
    
    def _playback_loop(self) -> None:
        """Thread loop for playing decoded audio."""
        logger.info("Playback loop started")
        
        # Open audio output stream
        try:
            stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype='int16'
            )
            stream.start()
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}")
            return
        
        while self.running:
            try:
                # Get decoded packet
                packet = self.playback_queue.get(timeout=0.1)
                
                # Play audio
                stream.write(packet['audio'])
                
            except Empty:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error in playback loop: {e}")
        
        # Close stream
        stream.stop()
        stream.close()
        logger.info("Playback loop stopped")
    
    def get_stats(self) -> dict:
        """Get receiver statistics."""
        return {
            'packets_received': self.packets_received,
            'packets_dropped': self.packets_dropped,
            'bytes_received': self.bytes_received,
            'packet_queue_size': self.packet_queue.qsize(),
            'playback_queue_size': self.playback_queue.qsize()
        }
    
    def close(self) -> None:
        """Close the receiver."""
        self.stop()
        try:
            self.socket.close()
            logger.info("UDP Audio Receiver closed")
        except Exception as e:
            logger.error(f"Error closing receiver: {e}")


if __name__ == "__main__":
    # Simple test receiver
    receiver = UDPAudioReceiver(listen_port=5005, playback_enabled=True)
    receiver.start()
    
    print("Listening for audio on port 5005...")
    print("Press Ctrl+C to stop")
    
    try:
        import time
        while True:
            time.sleep(1)
            stats = receiver.get_stats()
            print(f"Stats: {stats}")
    except KeyboardInterrupt:
        print("\nStopping...")
        receiver.close()
