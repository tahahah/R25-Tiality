# Audio Testing Without USB Microphone

This guide shows how to test the end-to-end audio workflow without a physical USB microphone using the dummy audio sender.

## Quick Start

### Terminal 1: Start GUI in Test Mode

```bash
python GUI/gui.py --robot --audio --audio_test_mode
```

**Key flag:** `--audio_test_mode` tells the receiver to accept raw PCM instead of Opus-encoded audio.

### Terminal 2: Start Dummy Audio Sender

```bash
# Sine wave (440Hz tone) CHANGE HOST TO YOUR PC
python test_audio_sender.py --host YOURPC --port 5005 --signal sine

# White noise
python test_audio_sender.py --host YOURPC --signal noise

# Chirp (frequency sweep)
python test_audio_sender.py --host YOURPC  --signal chirp


### Test Audio Classification

1. Wait 5 seconds for the buffer to fill
2. Press **R** key in the GUI
3. Check console output for classification results

## Signal Types

### Sine Wave (`sine`)
- Pure tone at specified frequency (default: 440Hz)
- Good for testing audio pipeline clarity
- Continuous smooth signal
```bash
python test_audio_sender.py --signal sine --frequency 880
```

### White Noise (`noise`)
- Random noise signal
- Tests noise handling and buffer stability
- Useful for stress testing
```bash
python test_audio_sender.py --signal noise
```

### Chirp (`chirp`)
- Frequency sweep from 200Hz to 2000Hz
- Tests frequency response
- Repeats every 2 seconds
```bash
python test_audio_sender.py --signal chirp
```

### Silence (`silence`)
- Zero amplitude signal
- Tests buffer behavior with no input
```bash
python test_audio_sender.py --signal silence
```

## Test Mode vs Production Mode

### Test Mode (`--audio_test_mode`)
- **Use when:** Testing without real hardware
- **Data format:** Raw PCM (int16)
- **Encoding:** None (bypasses Opus)
- **Sender:** `test_audio_sender.py`
- **Pros:** No Opus dependency, fast testing
- **Cons:** Not realistic encoding/decoding

### Production Mode (default)
- **Use when:** Real deployment with Pi
- **Data format:** Opus-encoded packets
- **Encoding:** Opus codec
- **Sender:** Pi with `main.py --stream`
- **Pros:** Realistic, compressed, production-ready
- **Cons:** Requires Opus libraries

## Command Reference

### GUI Commands

```bash
# Basic usage
python GUI/gui.py --robot --audio --audio_test_mode

# Custom port
python GUI/gui.py --robot --audio --audio_port 6000 --audio_test_mode

# Disable audio
python GUI/gui.py --robot --no-audio
```

### Dummy Sender Commands

```bash
# Basic sine wave
python test_audio_sender.py

# Custom frequency
python test_audio_sender.py --signal sine --frequency 1000

# Different signal types
python test_audio_sender.py --signal noise
python test_audio_sender.py --signal chirp
python test_audio_sender.py --signal silence

# Custom target
python test_audio_sender.py --host 192.168.1.100 --port 6000

# Time-limited streaming
python test_audio_sender.py --duration 30  # Stop after 30 seconds
```

## Testing Workflow

### 1. Basic Connectivity Test

```bash
# Terminal 1
python GUI/gui.py --robot --audio --audio_test_mode

# Terminal 2
python test_audio_sender.py --signal sine --duration 10
```

**Expected:** Hear a 440Hz tone for 10 seconds

### 2. Buffer Fill Test

```bash
# Terminal 1
python GUI/gui.py --robot --audio --audio_test_mode

# Terminal 2
python test_audio_sender.py --signal noise

# Wait 5 seconds, then press 'R' key in GUI
```

**Expected:** Classification output in console showing 5 seconds of captured audio

### 3. Classification Test

```bash
# Terminal 1
python GUI/gui.py --robot --audio --audio_test_mode

# Terminal 2
python test_audio_sender.py --signal chirp

# After 5 seconds, press 'R' multiple times
```

**Expected:** Each press shows classification result with consistent duration (~5.0s)

### 4. Stress Test

```bash
# Terminal 1
python GUI/gui.py --robot --audio --audio_test_mode

# Terminal 2
python test_audio_sender.py --signal noise --duration 60

# Press 'R' every few seconds
```

**Expected:** No dropped packets, consistent buffer, no memory leaks

## Troubleshooting

### No Audio Playback

**Problem:** Sender running but no sound

**Check:**
1. Is audio enabled? (`--audio` flag)
2. Is test mode enabled? (`--audio_test_mode` flag)
3. Are both processes on same host/port?
4. Is system audio working? (`python -c "import sounddevice; print(sounddevice.query_devices())"`)

**Solution:**
```bash
# Verify audio devices
python -c "import sounddevice; print(sounddevice.query_devices())"

# Check GUI logs for "Audio streaming on port 5005"
# Check sender logs for "Sent X frames"
```

### "No audio in buffer" Error

**Problem:** Pressing 'R' shows no audio available

**Cause:** Buffer not filled yet or sender not running

**Solution:**
- Wait at least 5 seconds after starting sender
- Verify sender is running with `ps aux | grep test_audio_sender`
- Check sender logs for frame count

### Packet Loss

**Problem:** Logs show dropped packets

**Cause:** CPU overload, network congestion, or queue overflow

**Solution:**
```bash
# Reduce frame rate (modify test_audio_sender.py)
FRAME_DURATION = 0.040  # 40ms instead of 20ms

# Increase queue sizes in udp_audio_receiver.py
self.packet_queue = Queue(maxsize=200)  # Was 100
```

### Classification Not Working

**Problem:** 'R' key does nothing

**Cause:** Missing inference_manager module

**Solution:**
```bash
# Verify module exists
ls inference_manager/

# Check import
python -c "from inference_manager import AudioClassifier; print('OK')"

# Check GUI logs for "Audio classifier initialized"
```

## Performance Metrics

### Expected Values

| Metric | Value |
|--------|-------|
| Frame Rate | ~50 fps (20ms frames) |
| Packet Size | ~2KB per packet |
| Bandwidth | ~15-20 KB/s |
| Buffer Size | 480KB (5 seconds) |
| CPU Usage | <5% |
| Latency | <100ms |

### Monitoring

```bash
# Terminal 1: GUI with verbose logging
python GUI/gui.py --robot --audio --audio_test_mode

# Terminal 2: Sender with stats
python test_audio_sender.py --signal sine

# Watch sender logs for:
#   "Sent X frames (Y.Ys, Z.Z fps)"
#   Should be ~50 fps steady

# Watch GUI logs for:
#   No "Packet loss" warnings
#   "Audio buffer contains X.X seconds" when pressing R
```

## Advanced: Adding Opus Encoding

For more realistic testing, you can add Opus encoding to the dummy sender:

```bash
# Install PyOgg (Pi-side library)
pip install pyogg

# Use Opus mode
python test_audio_sender.py --signal sine --use-opus
```

**Note:** This requires the same Opus setup as the Pi (bundled libraries or system installation).

## Integration with Real Pi

Once dummy testing is complete, switch to real Pi:

```bash
# Terminal 1: GUI (remove test mode flag)
python GUI/gui.py --robot --audio --audio_port 5005

# Pi: Start real audio streaming
python ALSA_Capture_Stream/main.py -s --host <YOUR_MAC_IP> --port 5005
```

The transition should be seamless - same port, same workflow, just real Opus encoding!

## Files

- `test_audio_sender.py` - Dummy audio generator and sender
- `test_audio.sh` - Quick test script
- `GUI/udp_audio_receiver.py` - Receiver with test mode support
- `GUI/gui.py` - GUI with test mode flag
- `inference_manager/` - Classification module

## Tips

1. **Always use test mode for dummy sender:** `--audio_test_mode`
2. **Start GUI first, then sender** - Easier to see connection logs
3. **Wait 5 seconds** before first classification
4. **Use different signals** to verify audio pipeline works correctly
5. **Check stats** - Press 'R' to see buffer duration
6. **Monitor logs** - Both terminals should show activity

## Next Steps

After successful dummy testing:

1. ✅ Test with real Pi microphone
2. ✅ Integrate real ML model in `inference_manager/`
3. ✅ Add GUI overlay for classification results
4. ✅ Implement continuous classification mode
5. ✅ Add confidence thresholding

Happy testing! 🎵
