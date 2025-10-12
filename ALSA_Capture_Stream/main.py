import settings
import argparse
import sounddevice as sd
import numpy as np
from time import time
from queue import Queue
from copy import deepcopy
from scipy.io import wavfile
from capture_object import CaptureObject
from encoder_object import EncoderObject
from decoder_object import DecoderObject
from udp_audio_sender import UDPAudioSender

def device_parser(user_input: str) -> argparse.ArgumentTypeError | dict[str, int]:
    """Parse ALSA device argument in format 'card,device'."""
    if ',' not in user_input:
        raise argparse.ArgumentTypeError("Device must be in format: card,device")
    parts = user_input.split(',')
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("Device must have exactly 2 parts")
    card, device = parts
    if not (card.isdigit() and device.isdigit()):
        raise argparse.ArgumentTypeError("Card and device must be integers")
    return {"card": int(card), "device": int(device)}

parser = argparse.ArgumentParser(
    prog="PiAudioStream",
    description="Captures and encodes audio from ALSA device."
)
parser.add_argument('-d', '--device', type=device_parser,
                    help='ALSA device as <card>,<device>, e.g., 1,0')
parser.add_argument('-c', '--capch', type=int, default=1, choices=[1, 2, 4],
                    help='Number of channels to capture')
parser.add_argument('-e', '--encch', type=int, default=1, choices=[1, 2],
                    help='Number of channels to encode')
parser.add_argument('-s', '--stream', action='store_true',
                    help='Enable UDP streaming mode')
parser.add_argument('--host', type=str, default='localhost',
                    help='Target host/IP for streaming (default: localhost)')
parser.add_argument('--port', type=int, default=5005,
                    help='Target UDP port (default: 5005)')
parser.add_argument('--duration', type=int, default=5,
                    help='Test recording duration in seconds (default: 5)')
parser.add_argument('--save', type=str, metavar='FILENAME',
                    help='Save recorded audio to file (WAV format). Example: --save output.wav')
args = parser.parse_args()

# Use provided device or default
interface = args.device if args.device else {"card": 0, "device": 6}

# Initialize global settings
settings.init()
settings.captured_channels = args.capch
settings.encoded_channels = min(args.encch, args.capch)
if settings.captured_channels < settings.encoded_channel_pick:
    settings.encoded_channel_pick = settings.captured_channels

# Create audio buffers
capture_buffer = bytearray(settings.frame_bytes * settings.captured_channels)
encoder_buffer = bytearray(settings.frame_bytes * settings.encoded_channels)
packet_queue = Queue(settings.queue_size)  # 100-packet FIFO (2 seconds @ 20ms frames)

# Initialize audio processing objects
capture = CaptureObject(capture_buffer, interface)
capture.start()
encoder = EncoderObject(capture_buffer, encoder_buffer)
decoder = DecoderObject()

# Initialize UDP sender for streaming mode
udp_sender = None
if args.stream:
    udp_sender = UDPAudioSender(args.host, args.port)
    print(f"UDP streaming to: {args.host}:{args.port}")

record_start_time = time()
record_duration = args.duration

print(f"""
==================
Audio Settings
==================
Mode:              {'STREAMING' if args.stream else 'TEST'}
Packet size:       20 ms
Queue size:        {settings.queue_size} packets
Interface:         {interface}
Sample rate:       {settings.sample_rate} Hz
Capture channels:  {settings.captured_channels}
Encode channels:   {settings.encoded_channels}
Save to file:      {args.save if args.save else 'No'}
""")

if args.stream:
    print(f"Streaming to {args.host}:{args.port}...")
    print("Press Ctrl+C to stop")
    try:
        while True:
            capture.read()
            packet_start_time = time()
            header = encoder.encode()
            
            # Send encoded audio via UDP
            audio_data = bytes(encoder_buffer[:header["packet_length"]])
            udp_sender.send_packet(header, audio_data)
            
            # Warn if processing exceeds frame duration
            packet_duration = time() - packet_start_time
            if packet_duration > settings.frame_duration:
                print(f"Warning: Processing time {packet_duration:.3f}s > frame duration {settings.frame_duration}s")
            
            # Log stats periodically
            if header["sequence_number"] % 100 == 0:
                stats = udp_sender.get_stats()
                print(f"Sent: {stats['packets_sent']} packets, {stats['bytes_sent']} bytes")
    except KeyboardInterrupt:
        print("\nStopping...")
        udp_sender.close()
        capture.stop()
else:
    # Test mode: record and playback
    print(f"Recording {record_duration} seconds...")
    while time() - record_start_time < record_duration:
        capture.read()
        packet_start_time = time()
        header = encoder.encode()
        
        # Queue with FIFO behavior
        if packet_queue.full():
            packet_queue.get_nowait()
        packet_queue.put_nowait({
            "header": deepcopy(header),
            "data": bytes(encoder_buffer[:header["packet_length"]])
        })
        
        # Warn if processing exceeds frame duration
        packet_duration = time() - packet_start_time
        if packet_duration > settings.frame_duration:
            print(f"Warning: Processing time {packet_duration:.3f}s > frame duration {settings.frame_duration}s")
    
    # Playback queued audio
    print("Playing back last 2 seconds...")
    silence_bytes = bytes(settings.frame_bytes)
    audio_data = [silence_bytes] * settings.queue_size
    initial_seq_number = -1
    
    while not packet_queue.empty():
        encoded_packet = packet_queue.get_nowait()
        sequence_number = encoded_packet["header"]["sequence_number"]
        
        if initial_seq_number == -1:
            initial_seq_number = sequence_number
            offset = 0
        else:
            offset = sequence_number - initial_seq_number
        
        # Handle out-of-order packets
        if offset < 0:
            audio_data = audio_data[offset:] + audio_data[:offset]
        
        audio_data[offset] = decoder.decode(encoded_packet["data"])
    
    # Prepare decoded audio
    audio_array = np.frombuffer(b''.join(audio_data), dtype=np.int16)
    if settings.encoded_channels > 1:
        audio_array = audio_array.reshape(-1, settings.encoded_channels)
    
    # Save audio file if requested
    if args.save:
        wavfile.write(args.save, settings.sample_rate, audio_array)
        print(f"Audio saved to: {args.save}")
    
    # Play decoded audio (optional)
    # sd.play(audio_array, samplerate=settings.sample_rate, blocking=True)