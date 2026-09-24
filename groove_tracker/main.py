"""
Main loop: record audio -> check for silence -> identify song -> check your
DVinyl collection -> render to the e-paper display -> report playing state
to Home Assistant.

Run with:      python -m groove_tracker
Or for a single one-shot pass (handy for testing): main_loop(once=True)
"""
import os
import time

from . import config, display, home_assistant
from .audio_capture import cleanup_stale_clips, is_signal_present, record_clip
from .collection_match import find_owned_release, refresh_cache
from .identify import identify_song


def _initial_state():
    """Tracks what's currently on the display, and how long the turntable
    has been continuously silent or continuously unrecognized, so the
    display can be updated after a debounce period (see
    _maybe_clear_for_silence/_maybe_clear_for_unrecognized) instead of
    either never changing (stale info stays up forever) or changing on
    every brief pause between tracks.
    """
    return {
        "last_shown": None,  # (artist, title) currently on the display, or None
        "screen_state": "blank",  # "blank" | "song" | "unrecognized" -- what's currently shown
        "silence_since": None,  # time.time() when the current silence streak began, or None
        "unrecognized_since": None,  # time.time() when the current "playing but unrecognized" streak began, or None
    }


def process_once(state=None):
    """Runs a single capture -> identify -> match -> display pass.

    Returns the updated state dict (see _initial_state) -- pass it back in
    on the next call, the same way main_loop does.
    """
    if state is None:
        state = _initial_state()

    print("Recording clip...", flush=True)
    wav_path = record_clip()
    try:
        playing = is_signal_present(wav_path)
        print(f"Signal level check: {'playing' if playing else 'silent'}", flush=True)

        try:
            home_assistant.set_playing_state(playing)
        except Exception as e:
            # A Home Assistant hiccup shouldn't block recognition/display.
            print(f"Error reporting to Home Assistant: {e}", flush=True)

        if not playing:
            state["unrecognized_since"] = None
            return _maybe_clear_for_silence(state)

        # Something is playing -- any silence streak is over.
        state["silence_since"] = None

        print("Identifying song via AudD...", flush=True)
        song = identify_song(wav_path)

        if not song:
            print("No song recognized this pass.", flush=True)
            return _maybe_clear_for_unrecognized(state)

        # A song was recognized -- any unrecognized streak is over.
        state["unrecognized_since"] = None

        key = (song["artist"], song["title"])
        print(f"Recognized: {song['artist']} — {song['title']}", flush=True)
        if key == state["last_shown"] and state["screen_state"] == "song":
            print("Same as last shown, not re-rendering.", flush=True)
            return state

        print("Checking DVinyl collection...", flush=True)
        owned_release = find_owned_release(song["artist"], song["title"])
        art_url = song.get("art_url")
        if owned_release:
            album = owned_release.get(config.FIELD_TITLE, song["album"])
            print(f"Owned release found: {album} — rendering to display...", flush=True)
            display.render_now_playing(song["artist"], song["title"], album, owned=True, art_url=art_url)
        else:
            print(f"Not in collection, using AudD's album: {song['album']} — rendering to display...", flush=True)
            display.render_now_playing(song["artist"], song["title"], song["album"], owned=False, art_url=art_url)

        print("Display updated.", flush=True)
        state["last_shown"] = key
        state["screen_state"] = "song"
        return state
    finally:
        # Always clean up the recorded clip, even if something above raised
        # -- this was previously leaking a ~1MB file every poll cycle
        # (found after ~500 accumulated and filled a size-limited /tmp).
        if not config.MOCK_MODE:
            try:
                os.remove(wav_path)
            except OSError:
                pass


def _maybe_clear_for_silence(state):
    """Clears the display after SILENCE_CLEAR_SECONDS of *continuous*
    silence -- not immediately, so a normal pause between tracks or while
    flipping a record doesn't blank the screen. `silence_since` marks when
    the current streak began; process_once resets it to None the moment
    audio is present again.

    Guarded on screen_state != "blank" rather than a plain "was something
    showing" boolean so this also correctly blanks a "Song not
    recognized" message left up from _maybe_clear_for_unrecognized, once
    the turntable actually stops -- and, either way, avoids hammering the
    panel with a repeat Clear() every poll once it's already blank.
    """
    now = time.time()
    if state["silence_since"] is None:
        state["silence_since"] = now
        return state

    if state["screen_state"] != "blank" and (now - state["silence_since"]) >= config.SILENCE_CLEAR_SECONDS:
        print(f"Silent for {config.SILENCE_CLEAR_SECONDS}s+, clearing display.", flush=True)
        display.clear_display()
        state["screen_state"] = "blank"
        # Force a fresh render next time, even if the same song resumes --
        # otherwise it'd be (wrongly) treated as "unchanged" and skipped.
        state["last_shown"] = None

    return state


def _maybe_clear_for_unrecognized(state):
    """Same debounce idea as _maybe_clear_for_silence, but for "the
    turntable is playing something, AudD just isn't recognizing it" --
    without this, a previously-recognized song's info would stay on
    screen indefinitely once a different, unrecognized track starts,
    making it look like recognition is still working when it isn't.

    Once the debounce period elapses, this renders an explicit "Song not
    recognized" message rather than just blanking the screen -- so it's
    clear the turntable is playing and being listened to, just not
    identified, as opposed to looking identical to genuine silence/idle.
    Guarded on screen_state != "unrecognized" so this message is rendered
    once per streak, not re-rendered (and re-flickering the e-paper panel)
    on every subsequent poll while the streak continues.
    """
    now = time.time()
    if state["unrecognized_since"] is None:
        state["unrecognized_since"] = now
        return state

    if state["screen_state"] != "unrecognized" and (now - state["unrecognized_since"]) >= config.UNRECOGNIZED_CLEAR_SECONDS:
        print(f"Unrecognized for {config.UNRECOGNIZED_CLEAR_SECONDS}s+, showing 'not recognized' message.", flush=True)
        display.render_message("Song not recognized")
        state["screen_state"] = "unrecognized"
        state["last_shown"] = None

    return state


def main_loop(once=False):
    refresh_cache()
    last_maintenance = time.time()
    state = _initial_state()

    while True:
        try:
            state = process_once(state)

            # Hourly maintenance: refresh the DVinyl cache, and sweep any
            # recordings left behind in .tmp_audio/ by a crash (normal
            # cleanup happens per-cycle in process_once and handles
            # everything else -- see cleanup_stale_clips's docstring).
            if time.time() - last_maintenance > 3600:
                refresh_cache()
                removed = cleanup_stale_clips()
                if removed:
                    print(f"Cleaned up {removed} stale recording(s) from .tmp_audio.", flush=True)
                last_maintenance = time.time()

        except Exception as e:
            print(f"Error in main loop: {e}")

        if once:
            return

        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main_loop()
