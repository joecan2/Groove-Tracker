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
    assert state["screen_state"] == "song"

    out_path = os.path.join(config.MOCK_DISPLAY_OUTPUT_DIR, "now_playing.png")
    assert os.path.exists(out_path)


def test_process_once_skips_render_when_unchanged():
    state = _initial_state()
    state["last_shown"] = ("Queen", "Bohemian Rhapsody")
    state["screen_state"] = "song"

    state = process_once(state)

    assert state["last_shown"] == ("Queen", "Bohemian Rhapsody")
    assert state["screen_state"] == "song"


def test_silence_does_not_clear_before_the_debounce_period():
    state = _initial_state()
    state["screen_state"] = "song"
    state["last_shown"] = ("Queen", "Bohemian Rhapsody")
    state["silence_since"] = time.time()  # streak just started

    state = _maybe_clear_for_silence(state)

    assert state["screen_state"] == "song"
    assert state["last_shown"] == ("Queen", "Bohemian Rhapsody")


def test_silence_clears_display_after_the_debounce_period():
    state = _initial_state()
    state["screen_state"] = "song"
    state["last_shown"] = ("Queen", "Bohemian Rhapsody")
    state["silence_since"] = time.time() - config.SILENCE_CLEAR_SECONDS - 1

    state = _maybe_clear_for_silence(state)

    assert state["screen_state"] == "blank"
    # Reset so the same song resuming later forces a fresh render instead
    # of being (wrongly) treated as unchanged.
    assert state["last_shown"] is None


def test_silence_clears_a_stale_unrecognized_message_too():
    # A "Song not recognized" message left on screen should also get
    # blanked once the turntable genuinely stops -- not just stale song
    # info. This is what screen_state (vs. a plain "displaying" boolean)
    # exists to cover.
    state = _initial_state()
    state["screen_state"] = "unrecognized"
    state["silence_since"] = time.time() - config.SILENCE_CLEAR_SECONDS - 1

    state = _maybe_clear_for_silence(state)

    assert state["screen_state"] == "blank"


def test_unrecognized_shows_a_message_after_the_debounce_period():
    state = _initial_state()
    state["screen_state"] = "song"
    state["last_shown"] = ("Queen", "Bohemian Rhapsody")
    state["unrecognized_since"] = time.time() - config.UNRECOGNIZED_CLEAR_SECONDS - 1

    state = _maybe_clear_for_unrecognized(state)

    assert state["screen_state"] == "unrecognized"
    assert state["last_shown"] is None

    out_path = os.path.join(config.MOCK_DISPLAY_OUTPUT_DIR, "now_playing.png")
    assert os.path.exists(out_path)


def test_unrecognized_message_is_not_repeatedly_rerendered():
    # Guards against re-rendering (and re-flickering the e-paper panel
    # with) the same "Song not recognized" message on every poll while
    # the unrecognized streak continues -- once shown, it should stay put
    # until something actually changes.
    from groove_tracker import display

    calls = []
    original = display.render_message
    display.render_message = lambda text: calls.append(text)
    try:
        state = _initial_state()
        state["screen_state"] = "unrecognized"
        state["unrecognized_since"] = time.time() - config.UNRECOGNIZED_CLEAR_SECONDS - 1

        state = _maybe_clear_for_unrecognized(state)

        assert calls == []
    finally:
        display.render_message = original


def test_clearing_is_skipped_when_nothing_is_currently_displayed():
    # Guards against hammering the e-paper panel with repeat clear
    # commands every poll while genuinely idle -- once the screen is
    # already blank, there's nothing to clear.
    from groove_tracker import display

    calls = []
    original = display.clear_display
    display.clear_display = lambda: calls.append(1)
    try:
        state = _initial_state()
        state["silence_since"] = time.time() - config.SILENCE_CLEAR_SECONDS - 1

        state = _maybe_clear_for_silence(state)

        assert state["screen_state"] == "blank"
        assert calls == []
    finally:
        display.clear_display = original
