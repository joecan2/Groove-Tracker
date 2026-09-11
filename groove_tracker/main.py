"""
Main loop: record audio -> identify song -> check your DVinyl collection ->
render to the e-paper display.

Run with:      python -m groove_tracker
Or for a single one-shot pass (handy for testing): main_loop(once=True)
"""
import time

from . import config, display
from .audio_capture import record_clip
from .collection_match import find_owned_release, refresh_cache
from .identify import identify_song


def process_once(last_shown=None):
    """Runs a single capture -> identify -> match -> display pass.

    Returns the (artist, title) tuple that was shown, or last_shown
    unchanged if nothing new was recognized.
    """
    wav_path = record_clip()
    song = identify_song(wav_path)

    if not song:
        return last_shown

    key = (song["artist"], song["title"])
    if key == last_shown:
        return last_shown

    owned_release = find_owned_release(song["artist"], song["title"])
    if owned_release:
        album = owned_release.get(config.FIELD_TITLE, song["album"])
        display.render_now_playing(song["artist"], song["title"], album, owned=True)
    else:
        display.render_now_playing(song["artist"], song["title"], song["album"], owned=False)

    return key


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
