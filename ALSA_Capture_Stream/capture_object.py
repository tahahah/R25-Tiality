import sounddevice as sd
import numpy as np
import settings

class CaptureObject:
    def __init__(self, capture_buffer: np.ndarray, interface: dict[str, int]) -> None:
        self.stream = sd.InputStream(
            samplerate=settings.sample_rate,
            blocksize=settings.frame_samples,
            device='hw:{},{}'.format(interface["card"], interface["device"]),
            channels=settings.captured_channels,
            dtype=settings.frame_format,
            callback=None
        )
        self.capture_buffer = capture_buffer.view()

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop()

    def read(self) -> None:
        (indata, overflowed) = self.stream.read(settings.frame_samples)
        if (overflowed):
            print("Input overflow (processing is too slow!)")
            raise sd.CallbackAbort
        self.capture_buffer[:] = indata
    
    def __callback__(self, indata, frames: int, time, status: sd.CallbackFlags) -> None:
        if (frames != settings.frame_samples):
            print("Frame size mismatch (expected: {}, actual: {}".format(settings.frame_samples, frames))
            raise sd.CallbackAbort
        if (status.input_underflow):
            print("Input underflow (processing is too fast!)")
            raise sd.CallbackAbort
        if (status.input_overflow):
            print("Input overflow (processing is too slow!)")
            raise sd.CallbackAbort
        self.capture_buffer[:] = indata