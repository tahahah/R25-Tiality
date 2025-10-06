from math import ceil

def init():
    global sample_rate
    sample_rate = 48000

    global captured_channels
    captured_channels = 2
    
    global encoded_channels
    encoded_channels = 2

    # First channel is `1`
    # Only used if `encoded_channels = 1`
    global encoded_channel_pick
    encoded_channel_pick = 2

    global frame_duration
    frame_duration = 20/1000

    global frame_samples
    frame_samples = ceil(frame_duration * sample_rate)

    global frame_format
    frame_format = 'int16'

    global format_bytes
    format_bytes = 2

    global frame_bytes
    frame_bytes = frame_samples * format_bytes

    global queue_size
    queue_size = 100