"""Shares a snapshot of main_loop's pipeline state with the web UI.

main.py and groove_tracker.webui run as separate OS processes (the web UI
needs to stay up even if the main service is stopped/crashed, and vice
versa), so there's no shared memory to read main_loop's state dict from
directly. Instead main.py calls write_status() after each pass, and the
web UI calls read_status() to render it -- a small JSON file is the
simplest thing that works for a single-writer/single-reader pair like
this, without needing a socket, database, or extra service.

Pure I/O, no MOCK_MODE branch: writing a small local JSON file has no
hardware/network dependency to mock out in the first place.
"""
import json
import os
import time

from . import config


def write_status(playing, song=None, owned=None, error=None):
    """Overwrites the status file with the current pipeline snapshot.

    `song` is the {artist, title, album} dict from identify_song(), or
    None if nothing's currently recognized/displayed. `error` is a short
    string describing the most recent main-loop exception, or None --
    kept separate from `song` so a transient error doesn't have to erase
    whatever was last successfully shown.
    """
    os.makedirs(config.STATE_DIR, exist_ok=True)
    status = {
        "updated_at": time.time(),
        "playing": playing,
        "artist": song.get("artist") if song else None,
        "title": song.get("title") if song else None,
        "album": song.get("album") if song else None,
        "owned": owned,
        "error": error,
    }
    tmp_path = config.STATUS_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(status, f)
    # Atomic on POSIX (and on Windows dev machines, os.replace handles the
    # same-filesystem overwrite too) -- avoids the web UI ever reading a
    # half-written file.
    os.replace(tmp_path, config.STATUS_PATH)


def read_status():
    """Returns the last-written status dict, or a default "unknown" one if
    the file doesn't exist yet (e.g. the service has never run) or is
    unreadable (e.g. being written concurrently -- see write_status's use
    of os.replace, which makes this rare but not impossible to catch here
    defensively).
    """
    try:
        with open(config.STATUS_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {
            "updated_at": None,
            "playing": None,
            "artist": None,
            "title": None,
            "album": None,
            "owned": None,
            "error": None,
        }


def append_history(song, owned):
    """Adds a newly-recognized song to the rolling history log (newest
    first, capped at config.HISTORY_MAX_ENTRIES), for the web UI's
    "Recently identified" list.

    Call this only when a *new* song actually starts showing on the
    display (main.py's "Display updated" branch in process_once) -- not
    on every poll, and not when process_once's own "same as last shown"
    check skips re-rendering, or every repeat recognition of a song
    that's still playing would bloat the log with duplicates of itself
    instead of showing 5 distinct tracks.

    Also skips appending if this is an exact repeat of the most recent
    entry, which covers the one gap process_once's own check doesn't:
    a service restart (main_loop always starts from a fresh in-memory
    state, so last_shown/screen_state don't carry over) while the same
    song is still playing would otherwise re-log it as if it were a new
    track.
    """
    history = read_history()
    if history and history[0]["artist"] == song["artist"] and history[0]["title"] == song["title"]:
        return
    print(f"Added to recent history: {song['artist']} — {song['title']}", flush=True)

    entry = {
        "artist": song["artist"],
        "title": song["title"],
        "album": song.get("album"),
        "owned": owned,
        "recognized_at": time.time(),
    }
    history.insert(0, entry)
    history = history[: config.HISTORY_MAX_ENTRIES]

    os.makedirs(config.STATE_DIR, exist_ok=True)
    tmp_path = config.HISTORY_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(history, f)
    os.replace(tmp_path, config.HISTORY_PATH)


def read_history():
    """Returns the rolling history list (newest first), or [] if it
    doesn't exist yet or is unreadable (see read_status's docstring for
    why that's expected, not an error).
    """
    try:
        with open(config.HISTORY_PATH) as f:
            history = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(history, list):
        return []
    # Drop anything malformed rather than let one bad entry break both the
    # dashboard render and the next append.
    return [
        entry for entry in history
        if isinstance(entry, dict) and "artist" in entry and "title" in entry
    ]
