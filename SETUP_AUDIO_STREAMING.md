# Audio Streaming Setup Guide

## Quick Start

### On GUI Machine (Mac/Linux)
```bash
# Install Opus library (macOS)
brew install opus

# Start GUI with audio enabled
python GUI/gui.py --robot --broker_port 2883 --audio --audio_port 5005
```

### On Raspberry Pi
```bash
# Stream audio to GUI
python main.py -c 1 -e 1 -d 3,0 --stream --host <YOUR_MAC_IP> --port 5005
```

Replace `<YOUR_MAC_IP>` with your Mac's IP address (e.g., `192.168.68.116`).

---

## Complete Setup for a New Mac

### Step 1: Install System Dependencies

**macOS with Homebrew:**
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Opus codec library
brew install opus
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get update
sudo apt-get install libopus0 libopus-dev
```

### Step 2: Install Python Dependencies

```bash
# Navigate to project directory
cd R25-Tiality2

# Install required packages
pip install sounddevice numpy
```

**Note:** PyOgg is NOT required on the GUI machine - we use the system Opus library instead.

### Step 3: Verify Installation

Run the verification test:
```bash
# Check if Opus library is accessible
python -c "import ctypes.util; print('Opus library:', ctypes.util.find_library('opus'))"

# On macOS, you might need to check Homebrew paths directly:
ls -la /opt/homebrew/lib/libopus*    # Apple Silicon (M1/M2)
ls -la /usr/local/lib/libopus*       # Intel Mac
```

Expected output:
```
Opus library: /opt/homebrew/lib/libopus.dylib
```

### Step 4: Get Your Mac's IP Address

```bash
# Option 1: Using ifconfig
ifconfig | grep "inet " | grep -v 127.0.0.1

# Option 2: Using hostname
hostname -I

# Option 3: From System Preferences
# System Preferences → Network → Advanced → TCP/IP
```

Example output: `192.168.68.116`

### Step 5: Configure Firewall (macOS)

```bash
# Allow Python through firewall
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add $(which python)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp $(which python)

# Or disable firewall temporarily for testing
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
```

### Step 6: Test Audio Streaming

**Terminal 1 (GUI Machine):**
```bash
python GUI/gui.py --robot --broker_port 2883 --audio --audio_port 5005
```

Look for these log messages:
```
INFO:GUI.udp_audio_receiver:UDP Audio Receiver initialized on port 5005
INFO:GUI.udp_audio_receiver:Using system Opus library: /opt/homebrew/lib/libopus.dylib
INFO:udp_audio_receiver:Opus decoder created: 48000Hz, 1 channel(s)
INFO:GUI.udp_audio_receiver:Opus decoder initialized
INFO:GUI.udp_audio_receiver:UDP Audio Receiver started
```

**Terminal 2 (Raspberry Pi):**
```bash
python main.py -c 1 -e 1 -d 3,0 --stream --host 192.168.68.116 --port 5005
```

Look for:
```
INFO:udp_audio_sender:UDP Audio Sender initialized: 192.168.68.116:5005
UDP Streaming enabled: 192.168.68.116:5005
Streaming audio to 192.168.68.116:5005...
Sent 100 packets, 14361 bytes
```

🎉 You should now hear audio from the Pi playing on your Mac!

---

## Understanding PyOgg and Architecture Differences

### The Challenge: Cross-Platform Audio Codec

The system uses the **Opus codec** for audio encoding/decoding. Opus is implemented in C and requires platform-specific compiled libraries.

**The Problem:**
- **Raspberry Pi**: ARM architecture (32-bit or 64-bit ARM)
- **Mac Intel**: x86_64 architecture
- **Mac Apple Silicon (M1/M2)**: ARM64 architecture (different from Pi's ARM)
- **Compiled libraries cannot be shared between different architectures**

### Our Solution: Hybrid Approach

We use **different strategies** on Pi vs GUI to avoid architecture conflicts:

#### On Raspberry Pi (Sender)
```
Pi uses PyOgg → Includes bundled ARM libraries → Opus encoder
```

- Location: `ALSA_Capture_Stream/PyOgg/`
- Contains pre-compiled libraries for Raspberry Pi ARM architecture
- Self-contained, no system installation needed

#### On GUI Machine (Receiver)
```
GUI uses system libopus → Direct ctypes bindings → Opus decoder
```

- Uses Homebrew-installed Opus (`brew install opus`)
- Native ARM64 libraries for M1/M2 Macs
- Native x86_64 libraries for Intel Macs
- No PyOgg dependency on GUI side

### How the System Opus Decoder Works

File: `GUI/udp_audio_receiver.py`

```python
class SimpleOpusDecoder:
    """Simple Opus decoder using system libopus."""
    
    def __init__(self, libopus, sample_rate, channels):
        # Direct ctypes wrapper around system libopus
        # Calls C functions: opus_decoder_create(), opus_decode()
```

**Library Detection:**
1. Try `ctypes.util.find_library('opus')`
2. If not found, check common Homebrew paths:
   - `/opt/homebrew/lib/libopus.dylib` (Apple Silicon)
   - `/usr/local/lib/libopus.dylib` (Intel Mac)
   - `/opt/homebrew/opt/opus/lib/libopus.dylib`
   - `/usr/local/opt/opus/lib/libopus.dylib`

**Why This Approach?**

✅ **No architecture conflicts** - Uses native libraries for your Mac's architecture  
✅ **Simpler setup** - Just `brew install opus`, no PyOgg copying  
✅ **Better performance** - Optimized for your specific CPU  
✅ **Smaller project** - No need to bundle multiple PyOgg versions  
✅ **Easier maintenance** - System package manager handles updates

### What If I Want to Use PyOgg on GUI?

You can, but you'll need:

1. **Copy PyOgg from a Mac with same architecture**
   ```bash
   # This WON'T work - Pi's ARM libraries are incompatible
   scp -r pi@<PI_IP>:~/R25-Tiality/ALSA_Capture_Stream/PyOgg ./GUI/
   
   # You'd need PyOgg compiled for macOS ARM64/x86_64
   ```

2. **Install PyOgg from source**
   ```bash
   # May work but requires compiling
   pip install PyOgg
   ```

3. **Deal with architecture mismatches**
   - Pi libraries won't work on Mac
   - Intel Mac libraries won't work on M1/M2
   - Requires separate PyOgg installations

**Our system Opus approach avoids all this complexity.**

---

## Command Reference

### GUI (gui.py)

```bash
python GUI/gui.py [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--robot` | Enable robot control mode | - |
| `--broker HOST` | MQTT broker hostname/IP | - |
| `--broker_port PORT` | MQTT broker port | 1883 |
| `--audio` | Enable audio receiver | True |
| `--no-audio` | Disable audio receiver | - |
| `--audio_port PORT` | UDP port for audio | 5005 |

**Examples:**
```bash
# Standard usage
python GUI/gui.py --robot --broker_port 2883 --audio

# Custom port
python GUI/gui.py --robot --broker_port 2883 --audio_port 5010

# Disable audio
python GUI/gui.py --robot --broker_port 2883 --no-audio
```

### Pi Audio Streaming (main.py)

```bash
python main.py [OPTIONS]
```

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--capch` | `-c` | Capture channels (1/2/4) | 2 |
| `--encch` | `-e` | Encode channels (1/2) | 1 |
| `--device` | `-d` | ALSA device `<card>,<device>` | 0,6 |
| `--stream` | `-s` | Enable UDP streaming | False |
| `--host` | - | Target IP for streaming | localhost |
| `--port` | - | Target UDP port | 5005 |
| `--duration` | - | Test mode duration (seconds) | 5 |

**Examples:**
```bash
# Stream mono audio
python main.py -c 1 -e 1 -d 3,0 --stream --host 192.168.1.100

# Stream stereo audio
python main.py -c 2 -e 2 -d 3,0 --stream --host 192.168.1.100 --port 5005

# Test mode - no streaming, save to file
python main.py -c 1 -e 1 -d 3,0 --duration 10
```

---

## Troubleshooting

### No Audio Output

**Check 1: Verify Opus library is installed**
```bash
# macOS
brew list opus
ls -la /opt/homebrew/lib/libopus*

# Should show: /opt/homebrew/lib/libopus.0.dylib
```

**Check 2: Test library detection**
```bash
python -c "
import ctypes.util
import os

path = ctypes.util.find_library('opus')
print(f'Found: {path}')

if not path:
    for p in ['/opt/homebrew/lib/libopus.dylib', '/usr/local/lib/libopus.dylib']:
        if os.path.exists(p):
            print(f'Homebrew path exists: {p}')
"
```

**Check 3: Verify network connectivity**
```bash
# From Mac, ping Pi
ping <PI_IP>

# Check if port is listening
netstat -an | grep 5005
```

**Check 4: Check firewall**
```bash
# macOS - check status
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# Temporarily disable for testing
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
```

### Decoder Errors

**Error: "byte must be in range(0, 256)"**
- This was fixed in the latest version
- Update your `udp_audio_receiver.py`

**Error: "Opus library not found"**
```bash
# Reinstall Opus
brew reinstall opus

# Verify
python GUI/test_decoder.py  # If file exists
```

### Audio Dropouts / Stuttering

**Solution 1: Increase jitter buffer**

Edit `GUI/udp_audio_receiver.py`:
```python
self.audio_receiver = UDPAudioReceiver(
    listen_port=audio_port,
    jitter_buffer_size=20,  # Increased from 10
    playback_enabled=True
)
```

**Solution 2: Check network**
```bash
# Test packet loss
ping -c 100 <PI_IP>

# Check for WiFi issues - use Ethernet if available
```

**Solution 3: Monitor statistics**
```python
# In GUI console or add to gui.py
stats = gui.audio_receiver.get_stats()
print(f"Loss rate: {stats.get('loss_rate', 0):.2%}")
print(f"Dropped: {stats.get('packets_dropped', 0)}")
```

### High Latency

**Reduce jitter buffer (trade-off: more dropouts)**
```python
jitter_buffer_size=5  # Reduced from 10
```

**Use wired network instead of WiFi**

**Check CPU usage**
```bash
# On Pi
top

# On Mac
Activity Monitor → CPU
```

---

## Network Configuration

### Bandwidth Requirements

- **Mono (1 channel)**: ~13-20 KB/s (~104-160 Kbps)
- **Stereo (2 channels)**: ~26-40 KB/s (~208-320 Kbps)

### Latency Breakdown

| Component | Typical Latency |
|-----------|----------------|
| Audio capture (20ms frames) | 20ms |
| Encoding | 1-5ms |
| Network transmission (LAN) | 1-10ms |
| Jitter buffer (10 packets) | 200ms |
| Decoding | 1-5ms |
| Audio playback buffer | 20-50ms |
| **Total** | **~250-300ms** |

**To reduce latency:** Decrease jitter buffer (increases dropout risk)

### Firewall Ports

**Incoming on GUI machine:**
- UDP port 5005 (or custom via `--audio_port`)

**Outgoing from Pi:**
- UDP to GUI IP:5005

---

## Performance Monitoring

### View Statistics

Add to `gui.py` or run in debug console:

```python
import threading
import time

def log_audio_stats():
    while True:
        if hasattr(gui, 'audio_receiver') and gui.audio_receiver:
            stats = gui.audio_receiver.get_stats()
            print(f"[Audio] Packets: {stats['packets_received']}, "
                  f"Lost: {stats['packets_lost']}, "
                  f"Loss: {stats['loss_rate']:.2%}")
        time.sleep(5)

# Start stats thread
threading.Thread(target=log_audio_stats, daemon=True).start()
```

### Packet Format

Each UDP packet (binary format):
```
┌──────────────┬──────────────┬──────────┬──────────────┐
│ Seq (4B)     │ Timestamp    │ Len (2B) │ Opus Data    │
│ uint32 BE    │ (8B) uint64  │ uint16   │ (variable)   │
└──────────────┴──────────────┴──────────┴──────────────┘

Header: 14 bytes
Payload: ~80-150 bytes (typical)
Total: ~94-164 bytes per packet
Rate: ~50 packets/second (20ms frames)
```

---

## Advanced Configuration

### Custom Opus Settings (Pi Side)

Edit `ALSA_Capture_Stream/encoder_object.py`:

```python
# After encoder creation
self.encoder.set_bitrate(32000)      # Higher quality (default: auto)
self.encoder.set_complexity(10)       # Max quality (0-10, default: 10)
self.encoder.set_application("audio") # For music vs "voip" for speech
```

### Custom Playback Buffer

Edit `GUI/udp_audio_receiver.py`:

```python
# In __init__
self.playback_queue = Queue(maxsize=50)  # Increase from 100
```

### Change Sample Rate

**Both Pi and GUI must match!**

Edit `ALSA_Capture_Stream/settings.py`:
```python
sample_rate = 44100  # Or 16000, 24000, 48000
```

Edit `GUI/gui.py`:
```python
self.audio_receiver = UDPAudioReceiver(
    sample_rate=44100,  # Match Pi setting
    ...
)
```

---

## File Structure

```
R25-Tiality2/
├── ALSA_Capture_Stream/
│   ├── main.py                      # Modified with --stream support
│   ├── udp_audio_sender.py          # UDP sender implementation
│   ├── encoder_object.py            # Opus encoder (uses PyOgg)
│   ├── capture_object.py            # ALSA audio capture
│   ├── settings.py                  # Audio configuration
│   ├── PyOgg/                       # PyOgg with ARM libraries (Pi only)
│   └── README_AUDIO_STREAMING.md    # Original README
│
├── GUI/
│   ├── gui.py                       # Modified with audio integration
│   ├── udp_audio_receiver.py        # UDP receiver + SimpleOpusDecoder
│   └── gui_config.py                # GUI configuration
│
└── SETUP_AUDIO_STREAMING.md         # This file
```

---

## Credits & Technical Details

**Audio Codec:** Opus (RFC 6716) - https://opus-codec.org/  
**Opus Implementation:** xiph.org libopus  
**PyOgg:** Team PyOgg - https://github.com/TeamPyOgg/PyOgg  
**Streaming Architecture:** Custom UDP implementation for R25-Tiality

**Key Technologies:**
- Opus codec for efficient audio compression
- UDP for low-latency transmission
- sounddevice for cross-platform audio I/O
- ctypes for direct C library bindings

---

## FAQ

**Q: Why not use PyOgg on both Pi and GUI?**  
A: Different CPU architectures (ARM vs x86_64/ARM64) require different compiled libraries. Using system Opus is simpler and architecture-agnostic.

**Q: Can I use this over the internet?**  
A: Yes, but you'll need port forwarding and increased jitter buffer. VPN recommended for security.

**Q: Why UDP instead of TCP?**  
A: UDP has lower latency and no retransmission delays. Some packet loss is acceptable for real-time audio.

**Q: What's the maximum range?**  
A: Works on any network where Pi and GUI can communicate. Limited by network latency and reliability.

**Q: Can I stream to multiple GUIs?**  
A: Not currently - sender broadcasts to single destination. Would need multicast implementation.

**Q: How do I record the streamed audio?**  
A: Add recording to `udp_audio_receiver.py` playback loop or use system audio recording tools.

---

## Support

If you encounter issues:

1. **Check this guide** - Most issues covered in Troubleshooting
2. **Verify setup** - Run through installation steps
3. **Check logs** - Both Pi and GUI show detailed error messages
4. **Test network** - Use `ping` and check firewall
5. **Test components** - Verify Opus library, audio devices independently

For system-specific issues, check:
- macOS: Homebrew installation, firewall settings
- Linux: apt packages, ALSA configuration
- Network: Firewall rules, router settings
