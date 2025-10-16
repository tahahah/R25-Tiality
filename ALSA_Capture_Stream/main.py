import settings
import argparse
import sounddevice as sd
import numpy as np
from time import time
from math import atan2
from queue import Queue
from copy import deepcopy
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
capture_buffer = np.ndarray((settings.frame_samples, settings.captured_channels), dtype=np.int16)
encoder_buffer = bytearray(settings.frame_bytes * settings.encoded_channels)

# Create data storage for direction sensing
max_lag = 20
max_lag_array = np.arange(-max_lag,max_lag+1, dtype=np.int16)
max_lag_idx = max_lag_array + (settings.frame_samples//2-1)
correlation_array = np.zeros((max_lag*4+1, settings.captured_channels - 1), dtype=np.int16)

packet_queue = Queue(settings.queue_size)  # 100-packet FIFO (2 seconds @ 20ms frames)

# Initialize audio processing objects
capture = CaptureObject(capture_buffer, interface)
encoder = EncoderObject(capture_buffer.data, encoder_buffer)
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

capture.start()
if args.stream:
    print(f"Streaming to {args.host}:{args.port}...")
    print("Press Ctrl+C to stop")
    try:
        while True:
            capture.read()

            # Start timer
            packet_start_time = time()

            # Encode buffer
            header = encoder.encode()

            # Calculate direction (amplitude method)
            amplitude_array = np.sqrt(np.mean(capture_buffer.astype(np.int32)**2, axis=0))
            loudest_index = np.argsort(amplitude_array)[::-1]
            if (settings.captured_channels == 4):
                direction_amp = atan2(amplitude_array[1]-amplitude_array[2],amplitude_array[3]-amplitude_array[0])-(np.pi/4)-(np.pi/2)
                direction_amp *= (180/np.pi)
                if direction_amp < -180: direction_amp += 360
            else:
                direction_amp = 90 if (loudest_index[0] == 0) else -90

            # Calculate direction (samples method)
            for i in range(1,settings.captured_channels):
                correlation_array[:,i-1] = np.correlate(capture_buffer[max_lag_idx,0],capture_buffer[max_lag_idx,i], 'full')
            delay_array = np.argmax(correlation_array, axis=0) - max_lag
            if (settings.captured_channels == 4):
                # Account for the distance between microphones in the four-mic system
                delay_array[0] = 2*delay_array[0]
                delay_array[2] += (delay_array[2]-delay_array[1])
                # Calculate the angle
                direction_time = atan2(delay_array[0]-delay_array[1],delay_array[2])-(np.pi/4)-(np.pi/2)
                direction_time *= (180/np.pi)
                if direction_time < -180: direction_time += 360
            else:
                direction_time = 90 if (delay_array < 0) else -90

            # Add information to header
            #header["direction_amp"] = direction_amp
            #header["direction_time"] = direction_time
            #header["amplitude"] = np.mean(amplitude_array)
            
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
                print("Whole packet duration: {:.1f} ms".format(packet_duration*1000))

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

        amplitude_array = np.sqrt(np.mean(capture_buffer.astype(np.int32)**2, axis=0))
        loudest_index = np.argsort(amplitude_array)[::-1]
        if (settings.captured_channels == 4):
            direction_amp = atan2(amplitude_array[1]-amplitude_array[2],amplitude_array[3]-amplitude_array[0])-(np.pi/4)-(np.pi/2)
            direction_amp *= (180/np.pi)
            if direction_amp < -180: direction_amp += 360
        else:
            direction_amp = 90 if (loudest_index[0] == 0) else -90

        for i in range(1,settings.captured_channels):
            correlation_array[:,i-1] = np.correlate(capture_buffer[max_lag_idx,0],capture_buffer[max_lag_idx,i], 'full')
        delay_array = np.argmax(correlation_array, axis=0) - max_lag
        if (settings.captured_channels == 4):
            delay_array[0] = 2*delay_array[0]
            delay_array[2] += (delay_array[2]-delay_array[1])
            direction_time = atan2(delay_array[0]-delay_array[1],delay_array[2])-(np.pi/4)-(np.pi/2)
            direction_time *= (180/np.pi)
            if direction_time < -180: direction_time += 360
        else:
            direction_time = 90 if (delay_array < 0) else -90

        header["direction_amp"] = direction_amp
        header["direction_time"] = direction_time
        header["amplitude"] = np.mean(amplitude_array)
                
        if (packet_queue.full()):
            packet_queue.get_nowait()
        packet_queue.put_nowait({"header": deepcopy(header), "data": bytes(encoder_buffer[0:header["packet_length"]])})

        packet_duration = time() - packet_start_time
        if (packet_duration > settings.frame_duration):
            print("Wall-to-wall time is greater than frame duration (expected: <{}, actual: {})".format(settings.frame_duration, packet_duration))
        if (header["sequence_number"] % 100 == 0):
            print("Whole packet duration: {:.1f} ms".format(packet_duration*1000))
            print("Direction: (amplitude) {:0.1f} deg (samples) {:0.1f} deg".format(direction_amp, direction_time))
            print("Amplitude: {:0.1f}".format(np.mean(amplitude_array)))
    
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
    
    # Play decoded audio (optional)
    # sd.play(audio_array, samplerate=settings.sample_rate, blocking=True)