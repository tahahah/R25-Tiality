# Pylance doesn't resolve these local imports correctly, but they do work
import pyogg                    # type: ignore
from pyogg import OpusEncoder   # type: ignore
from time import time
import settings

class EncoderObject:
    def __init__(self, capture_buffer: memoryview | bytearray | bytes, encoder_buffer: memoryview | bytearray) -> None:
        # Check that all encoders and containers are available
        if (not pyogg.PYOGG_OPUS_AVAIL) or \
           (not pyogg.PYOGG_OPUS_ENC_AVAIL) or \
           (not pyogg.PYOGG_OPUS_FILE_AVAIL) or \
           (not pyogg.PYOGG_OGG_AVAIL) or \
           (not pyogg.PYOGG_FLAC_AVAIL):
                raise(pyogg.PyOggError())

        # Configure Opus encoder
        self.encoder = OpusEncoder()
        self.encoder.set_application("audio")
        self.encoder.set_sampling_frequency(settings.sample_rate)
        self.encoder.set_channels(settings.encoded_channels)

        # Save a pointer to the buffer
        self.capture_buffer = memoryview(capture_buffer)
        self.encoder_buffer = memoryview(encoder_buffer)
        self.splice = 1 + (settings.captured_channels - settings.encoded_channels)
        self.offset = 0 if (settings.encoded_channels > 1) else (settings.encoded_channel_pick - 1) % settings.captured_channels

        # Configure other packet information
        self.packet_header = {"timestamp": 0, "sequence_number": -1, "packet_length": 0, "algorithm_delay": self.encoder.get_algorithmic_delay()}

    # Returns a dict packet containing the timestamp (epoch ms after encoding finish), sequence number, and algorithm delay
    def encode(self) -> dict:
        encoded_packet = self.capture_buffer[self.offset::self.splice].tobytes()
        encoded_packet = bytes(self.encoder.encode(encoded_packet))
        self.encoder_buffer[0:len(encoded_packet)] = encoded_packet
        self.packet_header["packet_length"] = len(encoded_packet)
        self.packet_header["sequence_number"] += 1
        self.packet_header["timestamp"] = self.__get_timestamp_ms__()
        return self.packet_header

    def __get_timestamp_ms__(self) -> int:
        return int(time() * 1000)