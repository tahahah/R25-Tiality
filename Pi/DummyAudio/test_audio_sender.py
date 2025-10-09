#!/usr/bin/env python3
"""
Dummy Audio Sender for Testing

Generates synthetic audio (sine waves, noise, etc.) and streams it to the GUI
via UDP, simulating the Pi's audio streaming without requiring actual hardware.

Usage:
    python test_audio_sender.py --host localhost --port 5005 --signal sine
    python test_audio_sender.py --signal noise
    python test_audio_sender.py --signal chirp
"""

import numpy as np
import struct
import socket
import time
import argparse
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DummyAudioSender:
    """Generates and sends dummy audio for testing."""
    
    HEADER_FORMAT = '!IQH'  # Must match UDPAudioReceiver
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    SAMPLE_RATE = 48000
    FRAME_DURATION = 0.020  # 20ms frames
    FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_DURATION)  # 960 samples
    
    def __init__(
        self,
        target_host: str = 'localhost',
        target_port: int = 5005,
        signal_type: str = 'sine',
        frequency: float = 440.0
    ):
        """
        Initialize dummy audio sender.
        
        Args:
            target_host: Target hostname/IP
            target_port: Target UDP port
            signal_type: Type of signal ('sine', 'noise', 'chirp', 'silence')
            frequency: Frequency for sine wave (Hz)
        """
        self.target_host = target_host
        self.target_port = target_port
        self.signal_type = signal_type
        self.frequency = frequency
        
        # Create socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # State
        self.sequence_number = 0
        self.phase = 0.0  # For continuous sine wave
        self.running = False
        
        logger.info(f"Dummy Audio Sender initialized")
        logger.info(f"Target: {target_host}:{target_port}")
        logger.info(f"Signal: {signal_type} @ {frequency}Hz")
        logger.info(f"Format: {self.SAMPLE_RATE}Hz, 20ms frames ({self.FRAME_SAMPLES} samples)")
    
    def generate_audio_frame(self) -> np.ndarray:
        """
        Generate one frame of audio based on signal type.
        
        Returns:
            Audio frame as int16 numpy array
        """
        if self.signal_type == 'sine':
            return self._generate_sine_wave()
        elif self.signal_type == 'noise':
            return self._generate_white_noise()
        elif self.signal_type == 'chirp':
            return self._generate_chirp()
        elif self.signal_type == 'silence':
            return self._generate_silence()
        else:
            logger.warning(f"Unknown signal type: {self.signal_type}, using sine")
            return self._generate_sine_wave()
    
    def _generate_sine_wave(self) -> np.ndarray:
        """Generate sine wave frame."""
        t = np.arange(self.FRAME_SAMPLES) / self.SAMPLE_RATE
        # Continue phase from last frame for smooth signal
        audio = np.sin(2 * np.pi * self.frequency * t + self.phase)
        self.phase = (self.phase + 2 * np.pi * self.frequency * self.FRAME_DURATION) % (2 * np.pi)
        
        # Scale to int16 range (leave headroom)
        audio = audio * 16000
        return audio.astype(np.int16)
    
    def _generate_white_noise(self) -> np.ndarray:
        """Generate white noise frame."""
        audio = np.random.randn(self.FRAME_SAMPLES) * 4000
        return audio.astype(np.int16)
    
    def _generate_chirp(self) -> np.ndarray:
        """Generate chirp (frequency sweep) frame."""
        t = np.arange(self.FRAME_SAMPLES) / self.SAMPLE_RATE
        # Sweep from 200Hz to 2000Hz over 2 seconds (repeats)
        sweep_time = self.sequence_number * self.FRAME_DURATION
        f_start = 200
        f_end = 2000
        sweep_duration = 2.0
        k = (f_end - f_start) / sweep_duration
        
        # Linear chirp
        instantaneous_freq = f_start + k * ((sweep_time + t) % sweep_duration)
        phase = 2 * np.pi * (f_start * t + 0.5 * k * t**2)
        audio = np.sin(phase) * 16000
        return audio.astype(np.int16)
    
    def _generate_silence(self) -> np.ndarray:
        """Generate silence frame."""
        return np.zeros(self.FRAME_SAMPLES, dtype=np.int16)
    
    def encode_frame(self, audio_frame: np.ndarray) -> bytes:
        """
        Encode audio frame to bytes (simulates Opus encoding).
        
        For testing, we just convert to raw PCM bytes.
        In reality, the Pi encodes with Opus.
        
        Args:
            audio_frame: int16 audio samples
            
        Returns:
            Encoded audio bytes
        """
        # For simplicity, just return raw PCM
        # This works because the receiver expects decoded audio to be int16
        # In production, this would be Opus-encoded
        return audio_frame.tobytes()
    
    def send_frame(self, audio_data: bytes) -> bool:
        """
        Send one audio frame via UDP.
        
        Args:
            audio_data: Encoded audio data
            
        Returns:
            True if sent successfully
        """
        try:
            # Get timestamp in microseconds
            timestamp = int(time.time() * 1_000_000)
            data_length = len(audio_data)
            
            # Pack header
            header = struct.pack(
                self.HEADER_FORMAT,
                self.sequence_number,
                timestamp,
                data_length
            )
            
            # Send packet
            packet = header + audio_data
            self.socket.sendto(packet, (self.target_host, self.target_port))
            
            self.sequence_number += 1
            return True
            
        except Exception as e:
            logger.error(f"Error sending frame: {e}")
            return False
    
    def stream(self, duration: Optional[float] = None):
        """
        Stream dummy audio continuously.
        
        Args:
            duration: Stream duration in seconds (None = infinite)
        """
        logger.info("Starting dummy audio stream...")
        logger.info("Press Ctrl+C to stop")
        
        self.running = True
        start_time = time.time()
        frame_count = 0
        
        try:
            while self.running:
                frame_start = time.time()
                
                # Generate audio frame
                audio_frame = self.generate_audio_frame()
                
                # For testing without Opus: send raw PCM as if it were decoded
                # We'll modify this to actually send through the decode pipeline
                encoded_data = self.encode_frame(audio_frame)
                
                # Send frame
                if self.send_frame(encoded_data):
                    frame_count += 1
                
                # Check duration limit
                if duration and (time.time() - start_time) >= duration:
                    logger.info(f"Duration limit reached: {duration}s")
                    break
                
                # Log stats periodically
                if frame_count % 100 == 0:
                    elapsed = time.time() - start_time
                    fps = frame_count / elapsed
                    logger.info(f"Sent {frame_count} frames ({elapsed:.1f}s, {fps:.1f} fps)")
                
                # Sleep to maintain frame rate
                frame_duration = time.time() - frame_start
                sleep_time = self.FRAME_DURATION - frame_duration
                if sleep_time > 0:
                    time.sleep(sleep_time)
                elif sleep_time < -0.005:
                    logger.warning(f"Frame took too long: {frame_duration*1000:.1f}ms > 20ms")
                    
        except KeyboardInterrupt:
            logger.info("\nStopping stream...")
        finally:
            self.running = False
            elapsed = time.time() - start_time
            logger.info(f"Sent {frame_count} frames in {elapsed:.1f}s ({frame_count/elapsed:.1f} fps)")
            self.socket.close()


# Note: The receiver expects Opus-encoded data, but for testing we need to modify approach
# Let's create a version that actually works with the current receiver

class DummyAudioSenderWithOpus(DummyAudioSender):
    """
    Dummy sender that uses actual Opus encoding.
    Falls back to raw PCM if Opus not available.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Try to initialize Opus encoder
        self.encoder = None
        try:
            import pyogg
            from pyogg import OpusEncoder
            self.encoder = OpusEncoder()
            self.encoder.set_application("audio")
            self.encoder.set_sampling_frequency(self.SAMPLE_RATE)
            self.encoder.set_channels(1)
            logger.info("Using Opus encoder")
        except ImportError:
            logger.warning("PyOgg not available - using raw PCM (receiver may not decode properly)")
        except Exception as e:
            logger.warning(f"Could not initialize Opus encoder: {e}")
    
    def encode_frame(self, audio_frame: np.ndarray) -> bytes:
        """Encode with Opus if available, otherwise raw PCM."""
        if self.encoder:
            try:
                # PyOgg expects bytes
                pcm_bytes = audio_frame.tobytes()
                encoded = self.encoder.encode(pcm_bytes)
                return bytes(encoded)
            except Exception as e:
                logger.error(f"Opus encoding failed: {e}")
                return audio_frame.tobytes()
        else:
            # Fallback to raw PCM
            return audio_frame.tobytes()


def main():
    parser = argparse.ArgumentParser(
        description="Dummy audio sender for testing without USB microphone"
    )
    parser.add_argument('--host', default='localhost',
                        help='Target host (default: localhost)')
    parser.add_argument('--port', type=int, default=5005,
                        help='Target UDP port (default: 5005)')
    parser.add_argument('--signal', choices=['sine', 'noise', 'chirp', 'silence'],
                        default='sine', help='Signal type (default: sine)')
    parser.add_argument('--frequency', type=float, default=440.0,
                        help='Sine wave frequency in Hz (default: 440)')
    parser.add_argument('--duration', type=float,
                        help='Stream duration in seconds (default: infinite)')
    parser.add_argument('--use-opus', action='store_true',
                        help='Try to use Opus encoding (requires pyogg)')
    
    args = parser.parse_args()
    
    # Choose sender class
    if args.use_opus:
        sender = DummyAudioSenderWithOpus(
            target_host=args.host,
            target_port=args.port,
            signal_type=args.signal,
            frequency=args.frequency
        )
    else:
        sender = DummyAudioSender(
            target_host=args.host,
            target_port=args.port,
            signal_type=args.signal,
            frequency=args.frequency
        )
    
    # Stream audio
    sender.stream(duration=args.duration)


if __name__ == "__main__":
    main()
