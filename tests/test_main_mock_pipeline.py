"""
End-to-end test of the full pipeline in MOCK_MODE -- no real hardware, no
network calls, no MongoDB connection required. Confirms the pieces are
wired together correctly, including the debounced silence/unrecognized
clearing logic that keeps a stale song from staying on the display
forever.
"""
import os
import time

os.environ["MOCK_MODE"] = "true"

from groove_tracker import config  # noqa: E402  (must set env var before import)
from groove_tracker.main import (  # noqa: E402
    _initial_state,
    _maybe_clear_for_silence,
    _maybe_clear_for_unrecognized,
    process_once,
)


def test_process_once_renders_and_returns_state():
    state = process_once(_initial_state())

    assert state["last_shown"] == ("Queen", "Bohemian Rhapsody")
    assert state["displaying"] is True

    out_path = os.path.join(config.MOCK_DISPLAY_OUTPUT_DIR, "now_playing.png")
    assert os.path.exists(out_path)


def test_process_once_skips_render_when_unchanged():
    state = _initial_state()
    state["last_shown"] = ("Queen", "Bohemian Rhapsody")
    state["displaying"] = True

    state = process_once(state)

    assert state["last_shown"] == ("Queen", "Bohemian Rhapsody")
    assert state["displaying"] is True


def test_silence_does_not_clear_before_the_debounce_period():
    state = _initial_state()
    state["displaying"] = True
    state["last_shown"] = ("Queen", "Bohemian Rhapsody")
    state["silence_since"] = time.time()  # streak just started

    state = _maybe_clear_for_silence(state)

    assert state["displaying"] is True
    assert state["last_shown"] == ("Queen", "Bohemian Rhapsody")


def test_silence_clears_display_after_the_debounce_period():
    state = _initial_state()
    state["displaying"] = True
    state["last_shown"] = ("Queen", "Bohemian Rhapsody")
    state["silence_since"] = time.time() - config.SILENCE_CLEAR_SECONDS - 1

    state = _maybe_clear_for_silence(state)

    assert state["displaying"] is False
    # Reset so the same song resuming later forces a fresh render instead
    # of being (wrongly) treated as unchanged.
    assert state["last_shown"] is None


def test_unrecognized_clears_stale_display_after_the_debounce_period():
    state = _initial_state()
    state["displaying"] = True
    state["last_shown"] = ("Queen", "Bohemian Rhapsody")
    state["unrecognized_since"] = time.time() - config.UNRECOGNIZED_CLEAR_SECONDS - 1

    state = _maybe_clear_for_unrecognized(state)

    assert state["displaying"] is False
    assert state["last_shown"] is None


def test_clearing_is_skipped_when_nothing_is_currently_displayed():
    # Guards against hammering the e-paper panel with repeat clear
    # commands every poll while genuinely idle -- once displaying is
    # already False, there's nothing to clear.
    from groove_tracker import display

    calls = []
    original = display.clear_display
    display.clear_display = lambda: calls.append(1)
    try:
        state = _initial_state()
        state["silence_since"] = time.time() - config.SILENCE_CLEAR_SECONDS - 1

        state = _maybe_clear_for_silence(state)

        assert state["displaying"] is False
        assert calls == []
    finally:
        display.clear_display = original
