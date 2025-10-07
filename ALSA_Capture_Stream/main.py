import settings
import argparse
import sounddevice as sd
import numpy as np
from time import time
from queue import Queue
from copy import deepcopy
from capture_object import CaptureObject
from encoder_object import EncoderObject
from decoder_object import DecoderObject
from udp_audio_sender import UDPAudioSender

# Create argument parser
def device_parser(user_input: str) -> argparse.ArgumentTypeError | dict[str, int]:
    if (',' not in user_input):
        raise argparse.ArgumentTypeError
    user_input_split = user_input.split(',')
    if (len(user_input_split) != 2):
        raise argparse.ArgumentTypeError
    card = user_input_split[0]
    device = user_input_split[1]
    if ((not card.isdigit()) or (not device.isdigit())):
        raise argparse.ArgumentTypeError
    return {"card": int(card), "device": int(device)}

parser = argparse.ArgumentParser(
    prog="PiAudioThread",
    description="Captures and encodes audio packets from the supplied ALSA device."
)
parser.add_argument('-d', '--device', help='ALSA device to use, specified as <card>,<device>, e.g., `1,0`', type=device_parser)
parser.add_argument('-c', '--capch', help='Number of channels to capture', default=1, choices=[1,2,4], type=int)
parser.add_argument('-e', '--encch', help='Number of channels to encode', default=1, choices=[1,2], type=int)
parser.add_argument('-s', '--stream', help='Enable UDP streaming mode (sends to GUI)', action='store_true')
parser.add_argument('--host', help='Target host/IP for UDP streaming (default: localhost)', default='localhost', type=str)
parser.add_argument('--port', help='Target UDP port for streaming (default: 5005)', default=5005, type=int)
parser.add_argument('--duration', help='Recording duration in seconds for test mode (default: 5)', default=5, type=int)
args = parser.parse_args()

# If no device is supplied, use the default
if (args.device):
    interface = args.device
else:
    interface = {"card": 0, "device": 6}

# Initialise global settings
settings.init()
settings.captured_channels = args.capch
settings.encoded_channels = args.encch
if (settings.captured_channels < settings.encoded_channels):
    settings.encoded_channels = settings.captured_channels
if (settings.captured_channels < settings.encoded_channel_pick):
    settings.encoded_channel_pick = settings.captured_channels

# Create buffer
capture_buffer = bytearray(settings.frame_bytes * settings.captured_channels)
encoder_buffer = bytearray(settings.frame_bytes * settings.encoded_channels)

# Create a 100-packet FIFO queue
# For 20 ms packets, this is two seconds of audio
packet_queue = Queue(settings.queue_size)

# Create capture object
capture = CaptureObject(capture_buffer, interface)
capture.start()

# Create encoder object
encoder = EncoderObject(capture_buffer, encoder_buffer)

# Create a decoder object
decoder = DecoderObject()

# Create UDP sender if streaming mode is enabled
udp_sender = None
if args.stream:
    udp_sender = UDPAudioSender(args.host, args.port)
    print(f"UDP Streaming enabled: {args.host}:{args.port}")

# Forever:
# 1. Fill encoder buffer with raw data
# 2. Encode buffer in place
# 3. Copy buffer to queue (or send via UDP)
# Time duration to complete steps after data buffer fills and raise warning if > 20 ms

record_start_time = time()
record_duration = args.duration

print("""
==================
Recording settings
==================
Mode: {}
Packet size: {} ms
Queue size: {} packets
Interface: {}
Sample rate: {}
Captured channels: {}
Encoded channels: {}
""".format("STREAMING" if args.stream else "TEST", 20, settings.queue_size, interface, settings.sample_rate, settings.captured_channels, settings.encoded_channels))

if args.stream:
    print(f"Streaming audio to {args.host}:{args.port}...")
    print("Press Ctrl+C to stop")
    try:
        while True:
            # Fill buffer
            capture.read()
            packet_start_time = time()

            # Encode buffer
            header = encoder.encode()

            # Send via UDP
            audio_data = bytes(encoder_buffer[0:header["packet_length"]])
            udp_sender.send_packet(header, audio_data)

            # Check time
            packet_duration = time() - packet_start_time
            if (packet_duration > settings.frame_duration):
                print("Wall-to-wall time is greater than frame duration (expected: <{}, actual: {})".format(settings.frame_duration, packet_duration))
            
            # Print stats every 100 packets
            if header["sequence_number"] % 100 == 0:
                stats = udp_sender.get_stats()
                print(f"Sent {stats['packets_sent']} packets, {stats['bytes_sent']} bytes")
    except KeyboardInterrupt:
        print("\nStopping stream...")
        udp_sender.close()
        capture.stop()
else:
    print(f"Recording {record_duration} seconds...")
    while time() - record_start_time < record_duration:
        # Fill buffer
        capture.read()
        packet_start_time = time()

        # Encode buffer
        header = encoder.encode()

        # Queue
        if (packet_queue.full()):
            packet_queue.get_nowait() # Discard first item
        packet_queue.put_nowait({"header": deepcopy(header), "data": bytes(encoder_buffer[0:header["packet_length"]])})

        # Check time
        packet_duration = time() - packet_start_time
        if (packet_duration > settings.frame_duration):
            print("Wall-to-wall time is greater than frame duration (expected: <{}, actual: {})".format(settings.frame_duration, packet_duration))

    print("Playing queue of last two seconds...")
    # Create a silent buffer
    silence_bytes = bytes(settings.frame_bytes)
    audio_data = [silence_bytes]*(settings.queue_size)
    initial_seq_number = -1
    while (not packet_queue.empty()):
        encoded_packet = packet_queue.get_nowait()
        sequence_number = encoded_packet["header"]["sequence_number"]
        offset = sequence_number - initial_seq_number

        # Set the initial sequence number
        if (initial_seq_number == -1):
            initial_seq_number = sequence_number
            offset = 0

        # Pad the audio data in case packets were queued out-of-order (shouldn't happen here, but could over network)
        if (offset < 0):
            audio_data = audio_data[offset:] + audio_data[:offset]
        
        # Decode
        audio_data[offset] = decoder.decode(encoded_packet["data"])
    audio_array = np.frombuffer(b''.join(audio_data), dtype=np.int16)
    if (settings.encoded_channels > 1):
        audio_array = audio_array.reshape(-1, settings.encoded_channels)
    sd.play(audio_array, samplerate=settings.sample_rate, blocking=True)