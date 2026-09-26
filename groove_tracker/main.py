"""
Main loop: record audio -> check for silence -> identify song -> check your
DVinyl collection -> render to the e-paper display -> report playing state
to Home Assistant.

Run with:      python -m groove_tracker
Or for a single one-shot pass (handy for testing): main_loop(once=True)
"""
import os
import time

from . import config, display, home_assistant, status
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
        "screen_state": "idle",  # "idle" | "song" -- what's currently shown. Both
        # silence and "playing but unrecognized" render the same idle vinyl icon
        # (see _maybe_clear_for_silence/_maybe_clear_for_unrecognized), so there's
        # no separate visual state for "unrecognized" -- just a separate timer.
        "silence_since": None,  # time.time() when the current silence streak began, or None
        "unrecognized_since": None,  # time.time() when the current "playing but unrecognized" streak began, or None
        "last_album": None,  # album shown alongside last_shown, kept only for status.write_status
        "last_owned": None,  # owned bool shown alongside last_shown, kept only for status.write_status
    }


def _status_song(state):
    """Builds the {artist, title, album} dict status.write_status() wants,
    from whatever's currently on the display per `state` -- kept separate
    from the screen-state machine itself (last_shown/screen_state) since
    only the web UI's status snapshot needs album/owned detail.
    """
    if state["screen_state"] != "song" or not state["last_shown"]:
        return None
    artist, title = state["last_shown"]
    return {"artist": artist, "title": title, "album": state["last_album"]}


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
            state = _maybe_clear_for_silence(state)
            status.write_status(playing=False, song=_status_song(state), owned=state["last_owned"])
            return state

        # Something is playing -- any silence streak is over.
        state["silence_since"] = None

        print("Identifying song via AudD...", flush=True)
        song = identify_song(wav_path)

        if not song:
            print("No song recognized this pass.", flush=True)
            state = _maybe_clear_for_unrecognized(state)
            status.write_status(playing=True, song=_status_song(state), owned=state["last_owned"])
            return state

        # A song was recognized -- any unrecognized streak is over.
        state["unrecognized_since"] = None

        key = (song["artist"], song["title"])
        print(f"Recognized: {song['artist']} — {song['title']}", flush=True)
        if key == state["last_shown"] and state["screen_state"] == "song":
            print("Same as last shown, not re-rendering.", flush=True)
            status.write_status(playing=True, song=_status_song(state), owned=state["last_owned"])
            return state

        print("Checking DVinyl collection...", flush=True)
        owned_release = find_owned_release(song["artist"], song["title"])
        art_url = song.get("art_url")
        if owned_release:
            album = owned_release.get(config.FIELD_TITLE, song["album"])
            print(f"Owned release found: {album} — rendering to display...", flush=True)
            display.render_now_playing(song["artist"], song["title"], album, owned=True, art_url=art_url)
        else:
            album = song["album"]
            print(f"Not in collection, using AudD's album: {album} — rendering to display...", flush=True)
            display.render_now_playing(song["artist"], song["title"], album, owned=False, art_url=art_url)

        print("Display updated.", flush=True)
        state["last_shown"] = key
        state["screen_state"] = "song"
        state["last_album"] = album
        state["last_owned"] = bool(owned_release)
        status.write_status(playing=True, song=_status_song(state), owned=state["last_owned"])
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
    """Shows the idle vinyl-icon screen after SILENCE_CLEAR_SECONDS of
    *continuous* silence -- not immediately, so a normal pause between
    tracks or while flipping a record doesn't switch the screen on every
    gap. `silence_since` marks when the current streak began; process_once
    resets it to None the moment audio is present again.

    Guarded on screen_state != "idle" rather than a plain "was something
    showing" boolean so this also correctly replaces stale song info --
    and, either way, avoids hammering the panel with a repeat render every
    poll once it's already idle (which also covers the case where
    _maybe_clear_for_unrecognized got there first: same "idle" state,
    same icon, so this is a no-op).
    """
    now = time.time()
    if state["silence_since"] is None:
        state["silence_since"] = now
        return state

    if state["screen_state"] != "idle" and (now - state["silence_since"]) >= config.SILENCE_CLEAR_SECONDS:
        print(f"Silent for {config.SILENCE_CLEAR_SECONDS}s+, showing idle screen.", flush=True)
        display.render_idle()
        state["screen_state"] = "idle"
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

    Shows the same idle vinyl-icon screen as _maybe_clear_for_silence --
    the panel doesn't try to visually distinguish "nothing's playing" from
    "something's playing but AudD can't identify it," it just clears stale
    song info back to the resting icon either way (an earlier version
    showed a distinct "Song not recognized" text message here instead).
    Guarded on screen_state != "idle" so this doesn't re-render an
    identical image (and re-flicker the panel) on every subsequent poll
    while the streak continues.
    """
    now = time.time()
    if state["unrecognized_since"] is None:
        state["unrecognized_since"] = now
        return state

    if state["screen_state"] != "idle" and (now - state["unrecognized_since"]) >= config.UNRECOGNIZED_CLEAR_SECONDS:
        print(f"Unrecognized for {config.UNRECOGNIZED_CLEAR_SECONDS}s+, showing idle screen.", flush=True)
        display.render_idle()
        state["screen_state"] = "idle"
        state["last_shown"] = None

    return state


def main_loop(once=False):
    refresh_cache()
    last_maintenance = time.time()
    state = _initial_state()

    # E-paper panels hold whatever was last drawn even across a reboot/power
    # loss, so without this the display could show a stale render from
    # before the service (re)started, indefinitely, until the next song is
    # recognized. Showing the idle screen up front means it always starts
    # from a known, on-theme state.
    display.render_idle()

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
            try:
                status.write_status(
                    playing=state.get("screen_state") == "song",
                    song=_status_song(state),
                    owned=state.get("last_owned"),
                    error=str(e),
                )
            except Exception:
                pass  # status.json is diagnostic only -- never let it mask the real error above

        if once:
            return

        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main_loop()
