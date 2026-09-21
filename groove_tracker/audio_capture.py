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

Recordings are also digitally amplified by a fixed CAPTURE_GAIN factor
(see config.py) before being saved — some audio interfaces (e.g. the
Behringer UCA202) have no hardware capture-level control, and a clean but
quiet signal is otherwise hard for fingerprinting services to match
reliably.
"""
import array
import os
import tempfile
import time
import wave

import numpy as np

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

    audio = _apply_gain(audio, config.CAPTURE_GAIN)

    tmp = tempfile.NamedTemporaryFile(dir=TEMP_AUDIO_DIR, suffix=".wav", delete=False)
    sf.write(tmp.name, audio, config.SAMPLE_RATE)
    return tmp.name


def _apply_gain(samples, gain):
    """Multiplies 16-bit audio samples by a fixed linear gain, hard-clipping
    to the valid int16 range to avoid wraparound distortion if the gain is
    set too high. Pure function, no MOCK_MODE dependency — safe to unit
    test directly.

    A no-op (gain == 1.0) returns the input unchanged, so this is always
    safe to call even when no gain is configured.
    """
    if gain == 1.0:
        return samples
    boosted = samples.astype(np.float64) * gain
    clipped = np.clip(boosted, -32768, 32767)
    return clipped.astype(np.int16)


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


def cleanup_stale_clips(max_age_seconds=None, directory=None, now=None):
    """Deletes leftover recordings from TEMP_AUDIO_DIR older than
    max_age_seconds. Returns how many were removed.

    Recordings are normally deleted right after use by main.py's
    process_once() (within the same poll cycle, so normally seconds old
    at most) -- this is the periodic safety net for the case that doesn't
    catch: a hard crash or SIGKILL mid-pipeline, after record_clip() has
    already written the file but before process_once()'s cleanup runs.
    Called roughly hourly from main_loop(), alongside the DVinyl cache
    refresh.

    Deliberately conservative (default measured in hours, not minutes) --
    anything old enough to be swept up here was never going to be used
    anyway, so there's no risk of deleting a clip still in flight.

    No MOCK_MODE branch: MOCK_MODE never writes to TEMP_AUDIO_DIR in the
    first place, so this is naturally a no-op there (the directory won't
    exist) without needing to special-case it.
    """
    if max_age_seconds is None:
        max_age_seconds = config.TMP_AUDIO_MAX_AGE_SECONDS
    if directory is None:
        directory = TEMP_AUDIO_DIR
    if now is None:
        now = time.time()

    if not os.path.isdir(directory):
        return 0

    removed = 0
    for name in os.listdir(directory):
        if not name.endswith(".wav"):
            continue
        path = os.path.join(directory, name)
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age >= max_age_seconds:
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass

    return removed
