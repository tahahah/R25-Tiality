"""
Audio Worker Module

Runs audio classification on a separate thread to prevent GUI blocking.
One-shot classification triggered by requests.
"""

import threading
import queue
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def run_audio_worker(
    audio_receiver,
    audio_trigger_queue: queue.Queue,
    audio_results_queue: queue.Queue,
    audio_classifier,
    shutdown_event: threading.Event
):
    """
    Audio worker that runs one-shot inference on a separate thread.
    
    Waits for classification requests from the trigger queue, then classifies
    the requested duration of audio and puts the result in the results queue.
    
    Args:
        audio_receiver: UDPAudioReceiver instance with audio buffer
        audio_trigger_queue: Queue to receive classification requests (duration in seconds)
        audio_results_queue: Queue to put classification results into
        audio_classifier: AudioClassifier instance (lazy loaded)
        shutdown_event: Event to signal worker shutdown
    """
    logger.info("Audio worker starting (one-shot mode)...")
    
    while not shutdown_event.is_set():
        try:
            # Wait for a classification request (with timeout to check shutdown)
            try:
                duration = audio_trigger_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            
            # Check if audio receiver is available
            if audio_receiver is None:
                logger.warning("Audio receiver not available")
                continue
            
            # Check if classifier is loaded (lazy loading handled by classifier)
            if audio_classifier is None:
                logger.warning("Audio classifier not available")
                continue
            
            # Get audio buffer stats
            stats = audio_receiver.get_stats()
            buffer_duration = stats.get('buffer_duration', 0)
            
            logger.info(f"Audio buffer contains {buffer_duration:.1f} seconds")
            
            # Need at least 1 second of audio to classify
            if buffer_duration < 1.0:
                logger.warning("Insufficient audio in buffer (need at least 1 second)")
                continue
            
            # Get audio data (requested duration or whatever is available)
            actual_duration = min(duration, buffer_duration)
            audio_data = audio_receiver.get_audio_buffer(duration=actual_duration)
            
            if len(audio_data) == 0:
                logger.warning("No audio available in buffer")
                continue
            
            # Run classification
            logger.info(f"Classifying {len(audio_data)} audio samples ({actual_duration:.1f}s)...")
            result = audio_classifier.classify_audio(
                audio_data,
                sample_rate=audio_receiver.sample_rate
            )
            
            # Put result in queue (dumping pattern - keep only most recent)
            try:
                audio_results_queue.get_nowait()
            except queue.Empty:
                pass
            
            audio_results_queue.put_nowait(result)
            
            logger.info(f"Audio classified: {result['top_prediction']} ({result['top_confidence']:.0%})")
            
        except Exception as e:
            logger.error(f"Error in audio worker: {e}", exc_info=True)
            time.sleep(0.5)  # Back off on error
    
    logger.info("Audio worker ending...")
