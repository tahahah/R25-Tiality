# Audio Inference Manager

Placeholder module for wildlife audio classification and inference.

## Overview

This module provides audio classification capabilities for the Wildlife Explorer system. It captures and classifies audio from the environment to identify wildlife species.

## Current Status: **Placeholder Mode**

The classifier is currently in placeholder mode with mock predictions. Real ML model integration is planned for future development.

## Features

### ✅ Implemented
- **5-Second Audio Buffer** - Continuously stores the last 5 seconds of audio
- **On-Demand Classification** - Classify audio by pressing 'R' key
- **WAV Export** - Export buffered audio as WAV file
- **Classification History** - Track recent classification results
- **Thread-Safe** - Audio buffer is thread-safe for real-time streaming

### 🔜 Planned
- Real ML model integration (TensorFlow/PyTorch)
- Species-specific wildlife sound models
- Confidence thresholding and filtering
- Audio preprocessing (noise reduction, normalization)
- Real-time continuous classification
- Audio augmentation for training
- GUI overlay for classification results

## Usage

### Basic Classification

**Keyboard Shortcut:**
Press `R` key in the GUI to classify the last 5 seconds of audio.

**Programmatic Usage:**
```python
from inference_manager import AudioClassifier

# Initialize classifier
classifier = AudioClassifier()

# Classify numpy array
result = classifier.classify_audio(audio_data, sample_rate=48000)
print(f"Prediction: {result['top_prediction']}")
print(f"Confidence: {result['top_confidence']:.1%}")

# Classify from WAV bytes
wav_bytes = audio_receiver.export_audio_wav(duration=5.0)
result = classifier.classify_from_wav(wav_bytes)

# Get classification history
history = classifier.get_history(limit=10)
```

## Architecture

### Audio Flow

```
Pi Microphone
    ↓ (ALSA Capture)
Opus Encoder
    ↓ (UDP Packets)
GUI Audio Receiver
    ↓ (Decode + Store)
Circular Buffer (5 sec)
    ↓ (On 'R' key press)
Audio Classifier
    ↓ (ML Inference)
Classification Result
```

### Buffer Implementation

- **Type**: `collections.deque` (circular buffer)
- **Capacity**: 240,000 samples (5 seconds @ 48kHz)
- **Thread-Safety**: Protected by `threading.Lock`
- **Memory**: ~480KB for int16 mono audio
- **Behavior**: Oldest samples automatically discarded when full

## API Reference

### `AudioClassifier`

#### Methods

**`__init__(model_path: Optional[str] = None)`**
- Initialize classifier with optional model path

**`classify_audio(audio_data: np.ndarray, sample_rate: int = 48000) -> Dict`**
- Classify audio from numpy array
- Returns: Classification result dictionary

**`classify_from_wav(wav_bytes: bytes) -> Dict`**
- Classify audio from WAV file bytes
- Returns: Classification result dictionary

**`get_history(limit: int = 10) -> List[Dict]`**
- Get recent classification history
- Returns: List of classification results

**`save_audio(audio_data: np.ndarray, filename: str, sample_rate: int = 48000)`**
- Save audio data to WAV file

### `UDPAudioReceiver` (Extended)

#### New Methods

**`get_audio_buffer(duration: float = 5.0) -> np.ndarray`**
- Get the last N seconds of audio
- Returns: numpy array of int16 samples

**`export_audio_wav(duration: float = 5.0) -> bytes`**
- Export audio as WAV file bytes
- Returns: WAV file as bytes

**`clear_buffer()`**
- Clear the audio history buffer

## Classification Result Format

```python
{
    'timestamp': '2025-10-08T00:25:44.123456',
    'duration': 5.0,
    'sample_rate': 48000,
    'num_samples': 240000,
    'predictions': [
        {'animal': 'Cockatoo', 'confidence': 0.94, 'type': 'Audio'},
        {'animal': 'Kookaburra', 'confidence': 0.76, 'type': 'Audio'},
        {'animal': 'Magpie', 'confidence': 0.52, 'type': 'Audio'}
    ],
    'top_prediction': 'Cockatoo',
    'top_confidence': 0.94
}
```

## Future ML Integration

### Recommended Models

1. **YAMNet** - Google's pretrained audio event classifier
2. **BirdNET** - Specialized for bird calls
3. **Custom CNN** - Train on wildlife dataset
4. **Transformer-based** - For complex audio patterns

### Integration Steps

1. Replace `classify_audio()` mock logic with real inference
2. Add preprocessing pipeline:
   - Convert to mel spectrogram
   - Normalize audio levels
   - Apply noise reduction
3. Load trained model in `__init__()`
4. Add confidence thresholding
5. Implement real-time sliding window classification

### Example Pseudocode

```python
def classify_audio(self, audio_data: np.ndarray, sample_rate: int) -> Dict:
    # Preprocess
    mel_spec = self.audio_to_mel_spectrogram(audio_data, sample_rate)
    normalized = self.normalize(mel_spec)
    
    # Inference
    with torch.no_grad():
        logits = self.model(normalized)
        probs = torch.softmax(logits, dim=-1)
    
    # Post-process
    top_k = torch.topk(probs, k=5)
    predictions = [
        {'animal': self.labels[idx], 'confidence': prob.item()}
        for idx, prob in zip(top_k.indices, top_k.values)
    ]
    
    return {'predictions': predictions, ...}
```

## File Structure

```
inference_manager/
├── __init__.py           # Module exports
├── audio_classifier.py   # Main classifier class
├── README.md            # This file
└── models/              # (Future) Trained model files
    └── wildlife_v1.pt
```

## Dependencies

**Current:**
- numpy
- wave (stdlib)
- logging (stdlib)

**Future:**
- torch or tensorflow
- librosa (audio processing)
- scipy (signal processing)

## Testing

To test the classifier:

1. Start the GUI with audio enabled:
   ```bash
   python GUI/gui.py --robot --audio
   ```

2. Start audio streaming from Pi:
   ```bash
   python ALSA_Capture_Stream/main.py -s --host <MAC_IP> --port 5005
   ```

3. Wait for 5 seconds of audio to buffer

4. Press `R` key to classify

5. Check console output for classification results

## Troubleshooting

**"No audio in buffer"**
- Wait at least 5 seconds after starting audio stream
- Check that audio streaming is enabled and working

**"Audio receiver not available"**
- Install audio dependencies: `pip install sounddevice numpy`
- Ensure audio streaming is enabled with `--audio` flag

**"Audio classifier not available"**
- Check that `inference_manager/` module is in Python path
- Verify module imports work: `from inference_manager import AudioClassifier`

## Performance

**Buffer Memory:**
- 5 seconds @ 48kHz mono = 240,000 samples
- int16 = 2 bytes per sample
- Total: ~480 KB RAM

**Classification Speed:**
- Current (mock): <1ms
- Expected with ML: 50-200ms depending on model size

## Contributing

When adding real ML models:

1. Keep the same API interface
2. Add model files to `.gitignore` (they're large)
3. Document model architecture and training data
4. Provide confidence calibration
5. Add unit tests for edge cases

## License

Part of R25-Tiality Wildlife Explorer project.
