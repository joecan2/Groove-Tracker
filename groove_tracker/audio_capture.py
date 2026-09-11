"""Records a short audio clip from the turntable line-in tap.

Imports of hardware-specific libraries (sounddevice) are deferred to
inside the function so this module can be imported on any machine —
including one with no audio hardware — without raising ImportError.
"""
import tempfile

from . import config


def record_clip():
    """Records CLIP_SECONDS of audio and returns the path to a WAV file.

    In MOCK_MODE, skips real recording and returns the bundled fixture
    clip instead, so the rest of the pipeline can be exercised without a
    turntable or audio hardware attached.
    """
    if config.MOCK_MODE:
        return config.MOCK_AUDIO_FIXTURE

    import sounddevice as sd
    import soundfile as sf

    frames = int(config.CLIP_SECONDS * config.SAMPLE_RATE)
    audio = sd.rec(
        frames,
        samplerate=config.SAMPLE_RATE,
        channels=config.CHANNELS,
        device=config.AUDIO_DEVICE,
        dtype="int16",
    )
    sd.wait()

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(tmp.name, audio, config.SAMPLE_RATE)
    return tmp.name
