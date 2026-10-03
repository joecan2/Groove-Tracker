"""
End-to-end test of the full pipeline in MOCK_MODE -- no real hardware, no
network calls, no MongoDB connection required. Confirms the pieces are
wired together correctly, including the debounced silence/unrecognized
logic that replaces a stale song with the idle vinyl-icon screen instead
of leaving it up forever.
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


def test_silence_shows_idle_screen_after_the_debounce_period():
    state = _initial_state()
    state["screen_state"] = "song"
    state["last_shown"] = ("Queen", "Bohemian Rhapsody")
    state["silence_since"] = time.time() - config.SILENCE_CLEAR_SECONDS - 1

    state = _maybe_clear_for_silence(state)

    assert state["screen_state"] == "idle"
    # Reset so the same song resuming later forces a fresh render instead
    # of being (wrongly) treated as unchanged.
    assert state["last_shown"] is None


def test_unrecognized_shows_idle_screen_after_the_debounce_period():
    state = _initial_state()
    state["screen_state"] = "song"
    state["last_shown"] = ("Queen", "Bohemian Rhapsody")
    state["unrecognized_since"] = time.time() - config.UNRECOGNIZED_CLEAR_SECONDS - 1

    state = _maybe_clear_for_unrecognized(state)

    # Shows the same idle vinyl-icon screen as the silence case -- there's
    # no separate visual state for "playing but unrecognized" vs. "genuine
    # silence," just a separate timer that got there.
    assert state["screen_state"] == "idle"
    assert state["last_shown"] is None

    out_path = os.path.join(config.MOCK_DISPLAY_OUTPUT_DIR, "now_playing.png")
    assert os.path.exists(out_path)


def test_unrecognized_idle_screen_is_not_repeatedly_rerendered():
    # Guards against re-rendering (and re-flickering the e-paper panel
    # with) an identical idle icon on every poll while the unrecognized
    # streak continues -- once shown, it should stay put until something
    # actually changes.
    from groove_tracker import display

    calls = []
    original = display.render_idle
    display.render_idle = lambda: calls.append(1)
    try:
        state = _initial_state()  # screen_state defaults to "idle" already
        state["unrecognized_since"] = time.time() - config.UNRECOGNIZED_CLEAR_SECONDS - 1

        state = _maybe_clear_for_unrecognized(state)

        assert calls == []
    finally:
        display.render_idle = original


def test_idle_screen_is_not_repeatedly_rerendered():
    # Guards against hammering the e-paper panel with a repeat render
    # every poll while genuinely idle -- once the idle screen is already
    # showing, there's nothing to change.
    from groove_tracker import display

    calls = []
    original = display.render_idle
    display.render_idle = lambda: calls.append(1)
    try:
        state = _initial_state()
        state["silence_since"] = time.time() - config.SILENCE_CLEAR_SECONDS - 1

        state = _maybe_clear_for_silence(state)

        assert state["screen_state"] == "idle"
        assert calls == []
    finally:
        display.render_idle = original


def _clear_history():
    if os.path.exists(config.HISTORY_PATH):
        os.remove(config.HISTORY_PATH)


def test_identified_song_is_added_to_recent_history_with_displayed_album():
    from groove_tracker import status

    _clear_history()
    process_once(_initial_state())

    history = status.read_history()
    assert len(history) == 1
    assert history[0]["artist"] == "Queen"
    assert history[0]["title"] == "Bohemian Rhapsody"
    # The mock collection owns this track on "Greatest Hits", which is what
    # the display shows -- history should match the display, not AudD's
    # guess ("A Night at the Opera").
    assert history[0]["album"] == "Greatest Hits"
    assert history[0]["owned"] is True


def test_still_playing_song_is_not_logged_again():
    from groove_tracker import status

    _clear_history()
    state = process_once(_initial_state())
    process_once(state)

    assert len(status.read_history()) == 1


def test_history_survives_a_restart_without_duplicating_the_playing_song():
    from groove_tracker import status

    _clear_history()
    process_once(_initial_state())
    # A restart means a brand new in-memory state; the history file is
    # the only thing that carries over.
    process_once(_initial_state())

    assert len(status.read_history()) == 1


def test_unidentified_playback_adds_nothing_to_history():
    from groove_tracker import status

    _clear_history()
    state = _initial_state()
    state["unrecognized_since"] = time.time() - config.UNRECOGNIZED_CLEAR_SECONDS - 1
    _maybe_clear_for_unrecognized(state)
    state["silence_since"] = time.time() - config.SILENCE_CLEAR_SECONDS - 1
    _maybe_clear_for_silence(state)

    assert status.read_history() == []
