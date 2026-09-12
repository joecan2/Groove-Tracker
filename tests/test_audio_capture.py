"""
Tests the pure WAV-analysis function directly (_compute_rms_level), not
the public get_audio_level/is_signal_present wrappers — those branch on
config.MOCK_MODE, which is fixed at first import of the config module and
would make these tests fragile to test-file import order. See CLAUDE.md's
testing conventions.
"""
import os

from groove_tracker.audio_capture import _compute_rms_level

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
