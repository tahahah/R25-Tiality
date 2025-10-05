"""
Standalone Opus decoder for GUI audio playback
Does not depend on the Pi's settings module
"""
import os

# Help PyOgg find Homebrew libraries on macOS
if os.path.exists('/opt/homebrew/lib'):
    os.environ.setdefault('DYLD_LIBRARY_PATH', '/opt/homebrew/lib')

try:
    import pyogg
    from pyogg import OpusDecoder
    OPUS_AVAILABLE = True
except ImportError:
    OPUS_AVAILABLE = False
    print("Warning: PyOgg not available. Audio decoding will be disabled.")


class AudioDecoder:
    def __init__(self, sample_rate=48000, channels=1):
        """
        Initialize Opus decoder for audio playback
        
        Args:
            sample_rate: Sample rate in Hz (default: 48000)
            channels: Number of channels (default: 1)
        """
        if not OPUS_AVAILABLE:
            raise ImportError("PyOgg is not available. Cannot decode audio.")
            
        # Check that required components are available (only decoding, not encoding)
        if (not pyogg.PYOGG_OPUS_AVAIL) or \
           (not pyogg.PYOGG_OPUS_FILE_AVAIL) or \
           (not pyogg.PYOGG_OGG_AVAIL):
            raise pyogg.PyOggError(
                f"Required Opus components not available:\n"
                f"  OPUS_AVAIL: {pyogg.PYOGG_OPUS_AVAIL}\n"
                f"  OPUS_FILE_AVAIL: {pyogg.PYOGG_OPUS_FILE_AVAIL}\n"
                f"  OGG_AVAIL: {pyogg.PYOGG_OGG_AVAIL}\n"
                f"On macOS, ensure Homebrew libraries are installed:\n"
                f"  brew install opus libogg opusfile"
            )

        # Configure Opus decoder
        self.decoder = OpusDecoder()
        self.decoder.set_sampling_frequency(sample_rate)
        self.decoder.set_channels(channels)
        self.sample_rate = sample_rate
        self.channels = channels

    def decode(self, encoded_packet: memoryview | bytearray | bytes) -> bytes:
        """
        Decode an Opus-encoded packet
        
        Args:
            encoded_packet: Opus-encoded audio data
            
        Returns:
            Decoded PCM audio data as bytes
        """
        # Make a mutable copy of the encoded packet
        mutable_buffer = bytearray(encoded_packet)
        
        # Decode and return an immutable copy
        return bytes(self.decoder.decode(mutable_buffer))
