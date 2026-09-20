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
from .audio_capture import is_signal_present, record_clip
from .collection_match import find_owned_release, refresh_cache
from .identify import identify_song


def process_once(last_shown=None):
    """Runs a single capture -> identify -> match -> display pass.

    Returns the (artist, title) tuple that was shown, or last_shown
    unchanged if nothing new was recognized.
    """
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
            return last_shown

        print("Identifying song via AudD...", flush=True)
        song = identify_song(wav_path)

        if not song:
            print("No song recognized this pass.", flush=True)
            return last_shown

        key = (song["artist"], song["title"])
        print(f"Recognized: {song['artist']} — {song['title']}", flush=True)
        if key == last_shown:
            print("Same as last shown, not re-rendering.", flush=True)
            return last_shown

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
        return key
    finally:
        # Always clean up the recorded clip, even if something above raised
        # -- this was previously leaking a ~1MB file every poll cycle
        # (found after ~500 accumulated and filled a size-limited /tmp).
        if not config.MOCK_MODE:
            try:
                os.remove(wav_path)
            except OSError:
                pass


def main_loop(once=False):
    refresh_cache()
    last_cache_refresh = time.time()
    last_shown = None

    while True:
        try:
            last_shown = process_once(last_shown)

            if time.time() - last_cache_refresh > 3600:
                refresh_cache()
                last_cache_refresh = time.time()

        except Exception as e:
            print(f"Error in main loop: {e}")

        if once:
            return

        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main_loop()
