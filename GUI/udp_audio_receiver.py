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

# Note: PyOgg directory check kept for backwards compatibility
# but not required when using system Opus libraries
gui_dir = os.path.dirname(os.path.abspath(__file__))
pyogg_dir = os.path.join(gui_dir, 'PyOgg')
if os.path.exists(pyogg_dir):
    sys.path.insert(0, pyogg_dir)

# Add parent directory to path
parent_dir = os.path.abspath(os.path.join(gui_dir, '..'))
sys.path.append(parent_dir)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleOpusDecoder:
    """Simple Opus decoder using system libopus."""
    
    def __init__(self, libopus, sample_rate: int, channels: int):
        """Initialize Opus decoder with system library."""
        import ctypes
        
        self.libopus = libopus
        self.sample_rate = sample_rate
        self.channels = channels
        
        # Opus constants
        OPUS_OK = 0
        
        # Define C function signatures
        self.libopus.opus_decoder_get_size.argtypes = [ctypes.c_int]
        self.libopus.opus_decoder_get_size.restype = ctypes.c_int
        
        self.libopus.opus_decoder_create.argtypes = [
            ctypes.c_int,  # sample_rate
            ctypes.c_int,  # channels
            ctypes.POINTER(ctypes.c_int)  # error
        ]
        self.libopus.opus_decoder_create.restype = ctypes.c_void_p
        
        self.libopus.opus_decode.argtypes = [
            ctypes.c_void_p,  # decoder
            ctypes.POINTER(ctypes.c_ubyte),  # data
            ctypes.c_int,  # len
            ctypes.POINTER(ctypes.c_int16),  # pcm
            ctypes.c_int,  # frame_size
            ctypes.c_int  # decode_fec
        ]
        self.libopus.opus_decode.restype = ctypes.c_int
        
        # Create decoder
        error = ctypes.c_int()
        self.decoder = self.libopus.opus_decoder_create(
            sample_rate,
            channels,
            ctypes.byref(error)
        )
        
        if error.value != OPUS_OK or not self.decoder:
            raise RuntimeError(f"Failed to create Opus decoder: {error.value}")
        
        logger.info(f"Opus decoder created: {sample_rate}Hz, {channels} channel(s)")
    
    def decode(self, encoded_packet: bytearray) -> bytes:
        """Decode an Opus packet to PCM audio."""
        import ctypes
        
        # Maximum frame size for Opus (120ms at 48kHz)
        max_frame_size = 5760
        
        # Create output buffer
        pcm_buffer = (ctypes.c_int16 * (max_frame_size * self.channels))()
        
        # Convert input to ctypes
        encoded_data = (ctypes.c_ubyte * len(encoded_packet)).from_buffer(encoded_packet)
        
        # Decode
        num_samples = self.libopus.opus_decode(
            self.decoder,
            encoded_data,
            len(encoded_packet),
            pcm_buffer,
            max_frame_size,
            0  # decode_fec = 0
        )
        
        if num_samples < 0:
            raise RuntimeError(f"Opus decode error: {num_samples}")
        
        # Convert int16 array to bytes properly
        # Calculate total bytes (2 bytes per int16 sample)
        total_samples = num_samples * self.channels
        total_bytes = total_samples * 2
        
        # Use ctypes.string_at to get raw bytes from the buffer
        return ctypes.string_at(ctypes.addressof(pcm_buffer), total_bytes)


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
                # Use system Opus library directly (works on macOS with Homebrew)
                import ctypes
                import ctypes.util
                
                # Find system Opus library
                opus_lib_path = ctypes.util.find_library('opus')
                
                # If not found, try common Homebrew paths on macOS
                if not opus_lib_path:
                    import platform
                    if platform.system() == 'Darwin':
                        homebrew_paths = [
                            '/opt/homebrew/lib/libopus.dylib',  # Apple Silicon
                            '/usr/local/lib/libopus.dylib',      # Intel Mac
                            '/opt/homebrew/opt/opus/lib/libopus.dylib',  # Homebrew opt
                            '/usr/local/opt/opus/lib/libopus.dylib'
                        ]
                        for path in homebrew_paths:
                            if os.path.exists(path):
                                opus_lib_path = path
                                break
                
                if not opus_lib_path:
                    raise ImportError("System Opus library not found. Install via: brew install opus")
                
                logger.info(f"Using system Opus library: {opus_lib_path}")
                libopus = ctypes.CDLL(opus_lib_path)
                
                # Create a simple Opus decoder wrapper
                self.decoder = SimpleOpusDecoder(libopus, self.sample_rate, self.channels)
                
                logger.info("Opus decoder initialized")
            except ImportError as e:
                logger.error(f"Failed to import decoder: {e}")
                logger.info("Install Opus: brew install opus")
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
                
                # Decode audio (decoder expects mutable buffer)
                mutable_buffer = bytearray(packet['data'])
                decoded_audio = bytes(self.decoder.decode(mutable_buffer))
                
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
