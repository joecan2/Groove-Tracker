"""Records a short audio clip from the turntable line-in tap, and checks
whether it actually contains signal (vs. silence between records).

Imports of hardware-specific libraries (sounddevice) are deferred to
inside the function so this module can be imported on any machine —
including one with no audio hardware — without raising ImportError.

Signal-level detection uses only the stdlib `wave` and `array` modules,
not `audioop` — that module was removed in Python 3.13.

Temp recordings are written under the project directory rather than the
system /tmp — on at least one real Pi Zero, /tmp turned out to be a small,
possibly RAM-backed area that filled up from accumulated temp files (see
main.py's cleanup in process_once, which deletes each clip after use —
this project-local location is a second line of defense in case that
cleanup is ever skipped, e.g. by a crash).
"""
import array
import os
import tempfile
import wave

from . import config

TEMP_AUDIO_DIR = os.path.join(os.path.dirname(__file__), "..", ".tmp_audio")


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

    os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

    frames = int(config.CLIP_SECONDS * config.SAMPLE_RATE)
    audio = sd.rec(
        frames,
        samplerate=config.SAMPLE_RATE,
        channels=config.CHANNELS,
        device=config.AUDIO_DEVICE,
        dtype="int16",
    )
    sd.wait()

    tmp = tempfile.NamedTemporaryFile(dir=TEMP_AUDIO_DIR, suffix=".wav", delete=False)
    sf.write(tmp.name, audio, config.SAMPLE_RATE)
    return tmp.name


def _compute_rms_level(wav_path):
    """Pure WAV analysis, no MOCK_MODE dependency — safe to unit test directly
    regardless of module import order.
    """
    with wave.open(wav_path, "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError("Expected 16-bit audio")
        raw = wf.readframes(wf.getnframes())

    samples = array.array("h")
    samples.frombytes(raw)
    if not samples:
        return 0.0

    mean_square = sum(s * s for s in samples) / len(samples)
    rms = mean_square**0.5
    return rms / 32768.0


def get_audio_level(wav_path):
    """Returns the RMS amplitude of a 16-bit WAV clip, normalized to ~0-1.

    In MOCK_MODE, returns a fixed "strong signal" value regardless of the
    actual fixture content, so the mock pipeline can exercise the
    "music is playing" path consistently.
    """
    if config.MOCK_MODE:
        return 1.0
    return _compute_rms_level(wav_path)


def is_signal_present(wav_path, threshold=None):
    """True if the clip's audio level is above the silence threshold —
    i.e. something is actually playing, as opposed to the turntable
    being stopped/idle.
    """
    if threshold is None:
        threshold = config.SILENCE_THRESHOLD
    return get_audio_level(wav_path) >= threshold
