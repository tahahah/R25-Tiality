import socket
import struct
import logging
import threading
import sounddevice as sd
import numpy as np
from queue import Queue, Empty
from typing import Optional
from collections import deque
import os
import wave
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleOpusDecoder:
    """Simple Opus decoder using system libopus."""
    OPUS_OK = 0
    
    def __init__(self, libopus, sample_rate: int, channels: int):
        """Initialize Opus decoder with system library."""
        import ctypes
        
        self.libopus = libopus
        self.sample_rate = sample_rate
        self.channels = channels
        
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
        
        if error.value != self.OPUS_OK or not self.decoder:
            raise RuntimeError(f"Failed to create Opus decoder: {error.value}")
        
        logger.info(f"Opus decoder created: {sample_rate}Hz, {channels} channel(s)")
    
    def decode(self, encoded_packet: bytearray) -> bytes:
        """Decode an Opus packet to PCM audio."""
        import ctypes
        
        max_frame_size = 5760  # Maximum frame size for Opus (120ms at 48kHz)
        pcm_buffer = (ctypes.c_int16 * (max_frame_size * self.channels))()
        encoded_data = (ctypes.c_ubyte * len(encoded_packet)).from_buffer(encoded_packet)
        
        num_samples = self.libopus.opus_decode(
            self.decoder,
            encoded_data,
            len(encoded_packet),
            pcm_buffer,
            max_frame_size,
            0  # decode_fec
        )
        
        if num_samples < 0:
            raise RuntimeError(f"Opus decode error: {num_samples}")
        
        total_bytes = num_samples * self.channels * 2  # 2 bytes per int16 sample
        return ctypes.string_at(ctypes.addressof(pcm_buffer), total_bytes)


class UDPAudioReceiver:
    """Receives and plays encoded audio packets via UDP."""
    HEADER_FORMAT = '!IQH'  # Must match sender: seq_num(4), timestamp(8), data_len(2)
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    MAX_PACKET_SIZE = 2048
    
    def __init__(
        self,
        listen_port: int = 5005,
        sample_rate: int = 48000,
        channels: int = 1,
        jitter_buffer_size: int = 10,  # Number of packets to buffer
        playback_enabled: bool = True,
        test_mode: bool = False,  # Skip Opus decoding for raw PCM testing
        buffer_duration: float = 5.0  # Duration of audio to buffer in seconds
    ):
        """
        Initialize UDP audio receiver.
        
        Args:
            listen_port: UDP port to listen on
            sample_rate: Audio sample rate (must match encoder)
            channels: Number of audio channels
            jitter_buffer_size: Number of packets to buffer before playing
            playback_enabled: Whether to enable audio playback
            test_mode: Skip Opus decoding for raw PCM testing
            buffer_duration: Duration of audio to buffer in seconds
        """
        self.listen_port = listen_port
        self.sample_rate = sample_rate
        self.channels = channels
        self.jitter_buffer_size = jitter_buffer_size
        self.playback_enabled = playback_enabled
        self.test_mode = test_mode
        self.buffer_duration = buffer_duration
        
        # Circular buffer for audio history
        max_samples = int(sample_rate * buffer_duration)
        self.audio_history = deque(maxlen=max_samples)
        self.history_lock = threading.Lock()
        
        # Create UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
        self.socket.bind(('', listen_port))
        self.socket.settimeout(0.1)
        
        # Processing queues
        self.packet_queue = Queue(maxsize=100)  # Jitter buffer
        self.playback_queue = Queue(maxsize=50)  # Decoded audio buffer
        
        # Threading control
        self.running = False
        self.receive_thread: Optional[threading.Thread] = None
        self.decode_thread: Optional[threading.Thread] = None
        self.playback_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.packets_received = 0
        self.packets_dropped = 0
        self.bytes_received = 0
        self.last_sequence_number = -1
        
        self.decoder = None  # Lazy initialized
        
        mode_str = "TEST MODE (raw PCM)" if test_mode else "normal (Opus)"
        logger.info(f"UDP Audio Receiver initialized on port {listen_port} [{mode_str}]")
    
    def _init_decoder(self):
        """Lazy initialize the Opus decoder."""
        if self.decoder is not None:
            return
            
        try:
            import ctypes
            import ctypes.util
            import platform
            
            opus_lib_path = ctypes.util.find_library('opus')
            
            # Try common Homebrew paths on macOS if not found
            if not opus_lib_path and platform.system() == 'Darwin':
                homebrew_paths = [
                    '/opt/homebrew/lib/libopus.dylib',
                    '/usr/local/lib/libopus.dylib',
                    '/opt/homebrew/opt/opus/lib/libopus.dylib',
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
                data, _ = self.socket.recvfrom(self.MAX_PACKET_SIZE)
                
                if len(data) < self.HEADER_SIZE:
                    logger.warning(f"Packet too small: {len(data)} bytes")
                    continue
                
                # Unpack header
                sequence_number, timestamp, data_length = struct.unpack(
                    self.HEADER_FORMAT, data[:self.HEADER_SIZE]
                )
                
                # Extract audio data
                audio_data = data[self.HEADER_SIZE:self.HEADER_SIZE + data_length]
                
                # Check for packet loss
                if self.last_sequence_number >= 0:
                    expected = self.last_sequence_number + 1
                    if sequence_number != expected:
                        lost = sequence_number - expected
                        self.packets_dropped += lost
                        logger.debug(f"Packet loss: {lost} packets")
                
                self.last_sequence_number = sequence_number
                
                # Queue packet for decoding
                try:
                    self.packet_queue.put_nowait({
                        'sequence_number': sequence_number,
                        'timestamp': timestamp,
                        'data': audio_data
                    })
                    self.packets_received += 1
                    self.bytes_received += len(data)
                except:
                    self.packets_dropped += 1
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error in receive loop: {e}")
        
        logger.info("Receive loop stopped")
    
    def _decode_loop(self) -> None:
        """Thread loop for decoding audio packets."""
        logger.info("Decode loop started")
        
        # Initialize decoder only if not in test mode
        if not self.test_mode:
            try:
                self._init_decoder()
            except Exception as e:
                logger.error(f"Failed to initialize decoder: {e}")
                return
        
        while self.running:
            try:
                packet = self.packet_queue.get(timeout=0.1)
                
                # Decode audio (or use raw PCM in test mode)
                if self.test_mode:
                    # Test mode: data is already raw PCM
                    audio_array = np.frombuffer(packet['data'], dtype=np.int16)
                else:
                    # Normal mode: decode Opus
                    mutable_buffer = bytearray(packet['data'])
                    decoded_audio = self.decoder.decode(mutable_buffer)
                    audio_array = np.frombuffer(decoded_audio, dtype=np.int16)
                
                if self.channels > 1:
                    audio_array = audio_array.reshape(-1, self.channels)
                
                # Store in circular buffer for history
                with self.history_lock:
                    for sample in audio_array:
                        self.audio_history.append(sample)
                
                # Queue for playback
                try:
                    self.playback_queue.put_nowait({
                        'sequence_number': packet['sequence_number'],
                        'audio': audio_array
                    })
                except:
                    pass  # Queue full, drop packet
                    
            except Empty:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error in decode loop: {e}")
        
        logger.info("Decode loop stopped")
    
    def _playback_loop(self) -> None:
        """Thread loop for playing decoded audio."""
        logger.info("Playback loop started")
        
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
                packet = self.playback_queue.get(timeout=0.1)
                stream.write(packet['audio'])
            except Empty:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error in playback loop: {e}")
        
        stream.stop()
        stream.close()
        logger.info("Playback loop stopped")
    
    def get_stats(self) -> dict:
        """Get receiver statistics."""
        with self.history_lock:
            buffer_duration = len(self.audio_history) / self.sample_rate
        return {
            'packets_received': self.packets_received,
            'packets_dropped': self.packets_dropped,
            'bytes_received': self.bytes_received,
            'packet_queue_size': self.packet_queue.qsize(),
            'playback_queue_size': self.playback_queue.qsize(),
            'buffer_duration': buffer_duration
        }
    
    def get_audio_buffer(self, duration: float = 5.0) -> np.ndarray:
        """
        Get the last N seconds of audio from the circular buffer.
        
        Args:
            duration: Number of seconds to retrieve (max 5.0)
            
        Returns:
            numpy array of int16 audio samples
        """
        duration = min(duration, 5.0)
        num_samples = int(self.sample_rate * duration)
        
        with self.history_lock:
            available = len(self.audio_history)
            samples_to_get = min(num_samples, available)
            
            if samples_to_get == 0:
                logger.warning("No audio in buffer")
                return np.array([], dtype=np.int16)
            
            # Get the most recent samples
            audio_data = list(self.audio_history)[-samples_to_get:]
            return np.array(audio_data, dtype=np.int16)
    
    def export_audio_wav(self, duration: float = 5.0) -> bytes:
        """
        Export the last N seconds of audio as WAV file bytes.
        
        Args:
            duration: Number of seconds to export (max 5.0)
            
        Returns:
            WAV file as bytes
        """
        audio_data = self.get_audio_buffer(duration)
        
        if len(audio_data) == 0:
            logger.warning("No audio to export")
            return b''
        
        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)  # 2 bytes for int16
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        return wav_buffer.getvalue()
    
    def clear_buffer(self) -> None:
        """Clear the audio history buffer."""
        with self.history_lock:
            self.audio_history.clear()
        logger.info("Audio buffer cleared")
    
    def close(self) -> None:
        """Close the receiver and cleanup resources."""
        self.stop()
        try:
            self.socket.close()
            logger.info("UDP Audio Receiver closed")
        except Exception as e:
            logger.error(f"Error closing socket: {e}")


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
