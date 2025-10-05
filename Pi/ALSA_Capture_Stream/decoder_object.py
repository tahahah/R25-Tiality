# Pylance doesn't resolve these local imports correctly, but they do work
import pyogg                    # type: ignore
from pyogg import OpusDecoder   # type: ignore
from time import time
import settings

class DecoderObject:
    def __init__(self) -> None:
        # Check that all encoders and containers are available
        if (not pyogg.PYOGG_OPUS_AVAIL) or \
           (not pyogg.PYOGG_OPUS_ENC_AVAIL) or \
           (not pyogg.PYOGG_OPUS_FILE_AVAIL) or \
           (not pyogg.PYOGG_OGG_AVAIL) or \
           (not pyogg.PYOGG_FLAC_AVAIL):
                raise(pyogg.PyOggError())

        # Configure Opus encoder
        self.decoder = OpusDecoder()
        self.decoder.set_sampling_frequency(settings.sample_rate)
        self.decoder.set_channels(settings.encoded_channels)

    def decode(self, decode_buffer: memoryview | bytearray | bytes) -> bytes:
        # Make a mutable copy of the encoded packet
        mutable_buffer = bytearray(decode_buffer)

        # Decode, then return an immutable copy of the decoded packet
        return bytes(self.decoder.decode(mutable_buffer))