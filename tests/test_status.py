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
