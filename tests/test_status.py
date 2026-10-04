"""Tests status.py's read/write round-trip -- pure local file I/O, no
MOCK_MODE branch needed (see its docstring), so this runs the same
anywhere, same as the .tmp_audio cleanup tests.
"""
import os

from groove_tracker import config, status


def test_read_status_defaults_when_file_missing():
    if os.path.exists(config.STATUS_PATH):
        os.remove(config.STATUS_PATH)

    result = status.read_status()

    assert result["playing"] is None
    assert result["artist"] is None
    assert result["error"] is None


def test_write_then_read_status_round_trips():
    song = {"artist": "Queen", "title": "Bohemian Rhapsody", "album": "A Night at the Opera"}

    status.write_status(playing=True, song=song, owned=True)
    result = status.read_status()

    assert result["playing"] is True
    assert result["artist"] == "Queen"
    assert result["title"] == "Bohemian Rhapsody"
    assert result["album"] == "A Night at the Opera"
    assert result["owned"] is True
    assert result["error"] is None
    assert isinstance(result["updated_at"], float)


def test_write_status_with_no_song_clears_previous_fields():
    status.write_status(playing=True, song={"artist": "Queen", "title": "X", "album": "Y"}, owned=False)
    status.write_status(playing=False, song=None, error="boom")

    result = status.read_status()

    assert result["playing"] is False
    assert result["artist"] is None
    assert result["error"] == "boom"


def test_read_history_defaults_to_empty_list_when_file_missing():
    if os.path.exists(config.HISTORY_PATH):
        os.remove(config.HISTORY_PATH)

    assert status.read_history() == []


def test_append_history_adds_newest_entry_first():
    if os.path.exists(config.HISTORY_PATH):
        os.remove(config.HISTORY_PATH)

    status.append_history({"artist": "Queen", "title": "Bohemian Rhapsody", "album": "A Night at the Opera"}, owned=True)
    status.append_history({"artist": "The Who", "title": "Baba O'Riley", "album": "Who's Next"}, owned=False)

    history = status.read_history()

    assert history[0]["artist"] == "The Who"
    assert history[1]["artist"] == "Queen"
    assert history[0]["owned"] is False
    assert isinstance(history[0]["recognized_at"], float)


def test_append_history_caps_at_configured_max_entries():
    if os.path.exists(config.HISTORY_PATH):
        os.remove(config.HISTORY_PATH)

    for i in range(config.HISTORY_MAX_ENTRIES + 3):
        status.append_history({"artist": f"Artist {i}", "title": f"Title {i}", "album": "Album"}, owned=False)

    history = status.read_history()

    assert len(history) == config.HISTORY_MAX_ENTRIES
    # Newest first -- the most recently appended entries survive the cap.
    assert history[0]["title"] == f"Title {config.HISTORY_MAX_ENTRIES + 2}"


def test_append_history_skips_exact_repeat_of_most_recent_entry():
    # Guards against a service restart re-logging the same still-playing
    # song as if it were a new track -- main_loop always starts from fresh
    # in-memory state, so process_once's own "same as last shown" check
    # can't catch this the way it does during a single continuous run.
    if os.path.exists(config.HISTORY_PATH):
        os.remove(config.HISTORY_PATH)

    song = {"artist": "Queen", "title": "Bohemian Rhapsody", "album": "A Night at the Opera"}
    status.append_history(song, owned=True)
    status.append_history(song, owned=True)

    assert len(status.read_history()) == 1


def test_read_history_ignores_malformed_entries_and_non_lists():
    import json

    os.makedirs(config.STATE_DIR, exist_ok=True)
    with open(config.HISTORY_PATH, "w") as f:
        json.dump([{"artist": "Queen", "title": "X"}, "junk", {"artist": "no title"}], f)
    assert [e["artist"] for e in status.read_history()] == ["Queen"]

    with open(config.HISTORY_PATH, "w") as f:
        json.dump({"not": "a list"}, f)
    assert status.read_history() == []


def test_code_is_stale_compares_running_commit_to_disk():
    assert status.code_is_stale("abc1234", "def5678") is True
    assert status.code_is_stale("abc1234", "abc1234") is False
    # Started by code too old to report a commit at all.
    assert status.code_is_stale(None, "abc1234") is True
    # Can't tell what's on disk (no git) -- don't claim it's stale.
    assert status.code_is_stale("abc1234", None) is False
