"""
Audio Classifier Module

Integrates real CNN-based audio classification for wildlife sound recognition.
Based on REAL_CLASSIFIER.py with thread-safe, on-demand inference.
"""

import os
import json
import logging
import numpy as np
import torch
import torch.nn as nn
import torchaudio
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ----------------------------------
# Model Architecture
# ----------------------------------

class ConvAudioClassifier(nn.Module):
    """4-layer CNN for audio classification from mel spectrograms."""
    
    def __init__(self, num_classes: int, n_mels: int = 64, overfit_mode: bool = False):
        super().__init__()
        
        if overfit_mode: 
            c1, c2, c3, c4 = 32, 64, 128, 256
            hidden_dim = 256
        else: 
            c1, c2, c3, c4 = 16, 32, 64, 128
            hidden_dim = 64
        
        self.conv_block = nn.Sequential(
            nn.Conv2d(1, c1, kernel_size=(3,3), padding=(1,1)),
            nn.BatchNorm2d(c1),
            nn.ReLU(),
            nn.MaxPool2d((2,2)),
            
            nn.Conv2d(c1, c2, kernel_size=(3,3), padding=(1,1)),
            nn.BatchNorm2d(c2),
            nn.ReLU(),
            nn.MaxPool2d((2,2)),
            
            nn.Conv2d(c2, c3, kernel_size=(3,3), padding=(1,1)),
            nn.BatchNorm2d(c3),
            nn.ReLU(),
            nn.MaxPool2d((2,2)),
            
            nn.Conv2d(c3, c4, kernel_size=(3,3), padding=(1,1)),
            nn.BatchNorm2d(c4),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1,1)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(c4, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, num_classes)
        )
    
    def forward(self, x):
        feats = self.conv_block(x)
        logits = self.classifier(feats)
        return logits


class SpectrogramTransform(nn.Module):
    """Convert raw waveform to normalized mel-spectrogram."""
    
    def __init__(self, sample_rate=16000, n_mels=64, n_fft=1024, hop_length=256):
        super().__init__()
        self.mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=sample_rate, n_fft=n_fft, hop_length=hop_length, 
            n_mels=n_mels, power=2.0
        )
        self.db = torchaudio.transforms.AmplitudeToDB(stype='power', top_db=80.0)
    
    def forward(self, waveform: torch.Tensor) -> torch.Tensor:
        # Normalize shapes into (batch, 1, time)
        if waveform.dim() == 1:
            waveform = waveform.unsqueeze(0).unsqueeze(1)
        elif waveform.dim() == 2:
            waveform = waveform.unsqueeze(1)
        elif waveform.dim() == 3 and waveform.size(1) != 1:
            waveform = waveform.mean(dim=1, keepdim=True)
        
        mel = self.mel(waveform)
        if mel.dim() == 4 and mel.size(1) == 1:
            mel = mel.squeeze(1)
        mel_db = self.db(mel)
        
        # Normalize
        mean = mel_db.mean(dim=[1,2], keepdim=True)
        std = mel_db.std(dim=[1,2], keepdim=True)
        mel_db = (mel_db - mean) / (std + 1e-9)
        
        return mel_db.unsqueeze(1)


# ----------------------------------
# Audio Classifier
# ----------------------------------

class AudioClassifier:
    """Real CNN-based audio classifier for wildlife sounds."""
    
    def __init__(
        self, 
        checkpoint_path: str = "Inference/audio_weights.ckpt",
        label_map_path: str = "Inference/audio_label_map.json",
        lazy_load: bool = True,
        ignore_noise: bool = True,
        noise_label: str = "Noise",
        noise_dominance_threshold: float = 0.95,
        renormalize_after_removal: bool = True
    ):
        """
        Initialize audio classifier.
        
        Args:
            checkpoint_path: Path to model checkpoint
            label_map_path: Path to label mapping JSON
            lazy_load: If True, delay model loading until first inference
            ignore_noise: If True, ignore noise class when finding top animal
            noise_label: Exact label name for noise class (case-insensitive)
            noise_dominance_threshold: Only report noise if confidence >= this
            renormalize_after_removal: Renormalize probabilities after removing noise
        """
        self.checkpoint_path = checkpoint_path
        self.label_map_path = label_map_path
        self.model_loaded = False
        self.classification_history: List[Dict] = []
        
        # Model parameters (must match training config)
        self.sample_rate = 16000
        self.window_seconds = 1.0
        self.hop_seconds = 0.02
        self.n_mels = 64
        self.n_fft = 1024
        self.hop_length = 256
        self.inference_batch_size = 64
        
        # Noise handling parameters (matches classify_audio.py)
        self.ignore_noise = ignore_noise
        self.noise_label = noise_label
        self.noise_dominance_threshold = noise_dominance_threshold
        self.renormalize_after_removal = renormalize_after_removal
        
        # Will be set on load
        self.model = None
        self.transform = None
        self.device = None
        self.idx_to_label = None
        self.num_classes = None
        self.noise_idx = None  # Index of noise class
        
        if not lazy_load:
            self._load_model()
        
        logger.info(f"AudioClassifier initialized (lazy_load={lazy_load}, ignore_noise={ignore_noise})")
    
    def _pick_device(self):
        """Select best available device."""
        if torch.cuda.is_available():
            return "cuda"
        mps_available = (
            getattr(torch.backends, "mps", None) is not None 
            and torch.backends.mps.is_available() 
            and torch.backends.mps.is_built()
        )
        if mps_available:
            return "mps"
        return "cpu"
    
    def _load_model(self):
        """Load model and label map."""
        if self.model_loaded:
            return
        
        try:
            # Check files exist
            if not os.path.exists(self.checkpoint_path):
                raise FileNotFoundError(f"Checkpoint not found: {self.checkpoint_path}")
            if not os.path.exists(self.label_map_path):
                raise FileNotFoundError(f"Label map not found: {self.label_map_path}")
            
            # Load label map
            with open(self.label_map_path, "r") as f:
                label_to_idx = json.load(f)
            label_to_idx = {k: int(v) for k, v in label_to_idx.items()}
            self.idx_to_label = {v: k for k, v in label_to_idx.items()}
            self.num_classes = len(self.idx_to_label)
            
            # Find noise class index (case-insensitive)
            self.noise_idx = None
            if self.ignore_noise:
                for idx, lbl in self.idx_to_label.items():
                    if lbl.lower() == self.noise_label.lower():
                        self.noise_idx = int(idx)
                        logger.info(f"Noise class found at index {self.noise_idx}")
                        break
                if self.noise_idx is None:
                    logger.warning(f"Noise class '{self.noise_label}' not found in label map")
            
            # Select device
            self.device = self._pick_device()
            logger.info(f"Using device: {self.device}")
            
            # Load model
            self.model = ConvAudioClassifier(num_classes=self.num_classes, n_mels=self.n_mels)
            ckpt = torch.load(self.checkpoint_path, map_location="cpu")
            state_dict = ckpt.get("state_dict", ckpt)
            
            # Clean Lightning prefixes
            cleaned_state = {}
            for k, v in state_dict.items():
                new_k = k[len("model."):] if k.startswith("model.") else k
                if new_k in self.model.state_dict():
                    cleaned_state[new_k] = v
            
            self.model.load_state_dict(cleaned_state)
            self.model.to(self.device)
            self.model.eval()
            
            # Load transform
            self.transform = SpectrogramTransform(
                sample_rate=self.sample_rate,
                n_mels=self.n_mels,
                n_fft=self.n_fft,
                hop_length=self.hop_length
            )
            self.transform.to(self.device)
            
            self.model_loaded = True
            logger.info(f"Model loaded: {self.num_classes} classes")
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    def _waveform_to_windows(self, waveform: torch.Tensor) -> torch.Tensor:
        """Convert waveform to overlapping windows."""
        if waveform.dim() == 2 and waveform.size(0) > 1:
            waveform = waveform.mean(dim=0)
        waveform = waveform.flatten()
        
        window_samples = int(self.window_seconds * self.sample_rate)
        hop_samples = int(self.hop_seconds * self.sample_rate)
        total = waveform.shape[-1]
        
        # Pad if too short
        if total < window_samples:
            pad_needed = window_samples - total
            waveform = torch.nn.functional.pad(waveform, (0, pad_needed))
            total = waveform.shape[-1]
        
        # Create windows
        starts = list(range(0, total - window_samples + 1, hop_samples))
        windows = [waveform[s:s + window_samples].unsqueeze(0) for s in starts]
        return torch.stack(windows, dim=0)
    
    def classify_audio(self, audio_data: np.ndarray, sample_rate: int = 48000) -> Dict:
        """
        Classify audio data using real CNN model.
        
        Args:
            audio_data: Audio samples as numpy array (int16)
            sample_rate: Sample rate in Hz
            
        Returns:
            Classification result dictionary
        """
        # Lazy load model
        if not self.model_loaded:
            self._load_model()
        
        try:
            # Convert to torch tensor and resample if needed
            waveform = torch.from_numpy(audio_data).float()
            if waveform.dim() == 1:
                waveform = waveform.unsqueeze(0)
            
            # Normalize int16 to [-1, 1]
            waveform = waveform / 32768.0
            
            # Resample to model's sample rate if needed
            if sample_rate != self.sample_rate:
                waveform = torchaudio.functional.resample(
                    waveform, orig_freq=sample_rate, new_freq=self.sample_rate
                )
            
            # Create windows
            windows = self._waveform_to_windows(waveform)
            if windows.size(0) == 0:
                raise RuntimeError("No windows produced from audio")
            
            # Run inference in batches
            self.model.eval()
            probs_list = []
            
            with torch.inference_mode():
                for i in range(0, windows.size(0), self.inference_batch_size):
                    chunk = windows[i:i+self.inference_batch_size]
                    chunk = chunk.to(self.device)
                    batch_mels = self.transform(chunk)
                    logits = self.model(batch_mels)
                    probs = torch.softmax(logits, dim=1).cpu()
                    probs_list.append(probs)
            
            # Aggregate predictions across windows
            all_probs = torch.cat(probs_list, dim=0).numpy()
            mean_probs = all_probs.mean(axis=0)
            
            # Apply noise handling logic (matches classify_audio.py)
            final_pred_idx = None
            final_pred_label = None
            final_pred_prob = None
            noise_prob = None
            processed_probs = mean_probs.copy()
            
            if self.ignore_noise and self.noise_idx is not None:
                noise_prob = float(mean_probs[self.noise_idx])
                nonnoise_probs = mean_probs.copy()
                nonnoise_probs[self.noise_idx] = 0.0
                
                # Check if all non-noise probabilities are zero
                if nonnoise_probs.sum() == 0.0:
                    # All probability is in noise class
                    final_pred_idx = int(self.noise_idx)
                    final_pred_label = self.idx_to_label[final_pred_idx]
                    final_pred_prob = float(noise_prob)
                    processed_probs = mean_probs
                else:
                    # Optionally renormalize after removing noise
                    if self.renormalize_after_removal:
                        nonnoise_probs = nonnoise_probs / nonnoise_probs.sum()
                    
                    final_pred_idx = int(nonnoise_probs.argmax())
                    final_pred_label = self.idx_to_label[final_pred_idx]
                    final_pred_prob = float(nonnoise_probs[final_pred_idx])
                    processed_probs = nonnoise_probs
                    
                    # Check noise dominance: if noise is overwhelming, report it instead
                    if noise_prob >= self.noise_dominance_threshold:
                        final_pred_idx = int(self.noise_idx)
                        final_pred_label = self.idx_to_label[final_pred_idx]
                        final_pred_prob = float(noise_prob)
                        processed_probs = mean_probs
            else:
                # No noise handling - use raw predictions
                final_pred_idx = int(mean_probs.argmax())
                final_pred_label = self.idx_to_label[final_pred_idx]
                final_pred_prob = float(mean_probs[final_pred_idx])
            
            # Get top 3 predictions from processed probabilities
            top_indices = np.argsort(processed_probs)[::-1][:3]
            predictions = [
                {
                    'animal': self.idx_to_label[int(idx)],
                    'confidence': float(processed_probs[idx]),
                    'type': 'Audio'
                }
                for idx in top_indices
            ]
            
            # Build result
            result = {
                'timestamp': datetime.now().isoformat(),
                'duration': len(audio_data) / sample_rate,
                'sample_rate': sample_rate,
                'num_samples': len(audio_data),
                'predictions': predictions,
                'top_prediction': final_pred_label if final_pred_label else predictions[0]['animal'],
                'top_confidence': final_pred_prob if final_pred_prob else predictions[0]['confidence']
            }
            
            # Add noise information if available
            if noise_prob is not None:
                result['noise_probability'] = noise_prob
                result['noise_handling_enabled'] = self.ignore_noise
            
            # Store in history
            self.classification_history.append(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            raise
    
    def get_history(self, limit: int = 10) -> List[Dict]:
        """Get recent classification history."""
        return self.classification_history[-limit:]
    
    def clear_history(self) -> None:
        """Clear classification history."""
        self.classification_history.clear()
        logger.info("Classification history cleared")
