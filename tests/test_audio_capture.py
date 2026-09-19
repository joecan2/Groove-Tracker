"""
Tests the pure WAV-analysis function directly (_compute_rms_level), not
the public get_audio_level/is_signal_present wrappers — those branch on
config.MOCK_MODE, which is fixed at first import of the config module and
would make these tests fragile to test-file import order. See CLAUDE.md's
testing conventions.
"""
import os

import numpy as np

from groove_tracker.audio_capture import _apply_gain, _compute_rms_level

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SILENT_CLIP = os.path.join(FIXTURES, "sample_clip.wav")
LOUD_CLIP = os.path.join(FIXTURES, "loud_clip.wav")


def test_silent_clip_has_near_zero_level():
    assert _compute_rms_level(SILENT_CLIP) < 0.01


def test_loud_clip_has_high_level():
    assert _compute_rms_level(LOUD_CLIP) > 0.1


def test_loud_clip_exceeds_default_threshold():
    from groove_tracker import config

    assert _compute_rms_level(LOUD_CLIP) >= config.SILENCE_THRESHOLD


def test_silent_clip_below_default_threshold():
    from groove_tracker import config

    assert _compute_rms_level(SILENT_CLIP) < config.SILENCE_THRESHOLD


def test_gain_of_one_is_a_noop():
    samples = np.array([100, -200, 5000], dtype=np.int16)
    result = _apply_gain(samples, 1.0)
    assert result is samples


def test_gain_scales_samples_linearly():
    samples = np.array([100, -200, 5000], dtype=np.int16)
    result = _apply_gain(samples, 4.0)
    assert list(result) == [400, -800, 20000]


def test_gain_hard_clips_instead_of_wrapping():
    # Without clipping, 20000 * 3 = 60000, which overflows int16 (max
    # 32767) and would wrap around to a large negative number — exactly
    # the kind of digital distortion this function exists to prevent.
    samples = np.array([20000, -20000], dtype=np.int16)
    result = _apply_gain(samples, 3.0)
    assert list(result) == [32767, -32768]


def test_gain_preserves_silence_to_signal_ratio():
    # A fixed gain scales quiet background noise and real signal by the
    # same factor, so a threshold tuned against the un-gained recording
    # stays meaningful after gain is applied — unlike per-clip
    # normalization, which would flatten this ratio out.
    quiet_noise = np.array([10, -15, 8], dtype=np.int16)
    real_signal = np.array([5000, -6000, 4500], dtype=np.int16)
    gain = 5.0

    gained_noise = _apply_gain(quiet_noise, gain)
    gained_signal = _apply_gain(real_signal, gain)

    assert _rms(gained_noise) < _rms(gained_signal)
    # ratio should match the un-gained ratio (within floating point/int
    # rounding tolerance)
    raw_ratio = _rms(quiet_noise) / _rms(real_signal)
    gained_ratio = _rms(gained_noise) / _rms(gained_signal)
    assert abs(raw_ratio - gained_ratio) < 0.01


def _rms(samples):
    arr = np.asarray(samples, dtype=np.float64)
    return float(np.sqrt(np.mean(arr**2)))
