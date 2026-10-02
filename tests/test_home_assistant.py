"""
Tests the pure payload-construction helper directly (_build_now_playing_payload),
not the public set_now_playing/set_playing_state wrappers -- those branch on
config.MOCK_MODE and make a real network call otherwise, same reasoning as
_compute_rms_level in test_audio_capture.py. See CLAUDE.md's testing
conventions.
"""
from groove_tracker.home_assistant import _build_now_playing_payload


def test_no_artist_means_idle_with_no_media_attributes():
    state, attributes = _build_now_playing_payload(artist=None, title=None, album=None, owned=False)
    assert state == "idle"
    # No song-specific attributes should leak through when nothing's
    # recognized -- the states API replaces attributes wholesale, so
    # omitting them is what clears stale song info off the card.
    assert not any(key.startswith("media_") for key in attributes)


def test_recognized_song_sets_playing_state_and_media_attributes():
    state, attributes = _build_now_playing_payload(
        artist="The Who", title="Baba O'Riley", album="Who's Next", owned=True
    )
    assert state == "playing"
    assert attributes["media_title"] == "Baba O'Riley"
    assert attributes["media_artist"] == "The Who"
    assert attributes["media_album_name"] == "Who's Next"
    assert attributes["media_content_type"] == "music"
    assert attributes["owned"] is True


def test_no_artwork_is_ever_sent():
    _, attributes = _build_now_playing_payload(
        artist="Queen", title="Bohemian Rhapsody", album="A Night at the Opera", owned=False
    )
    assert "entity_picture" not in attributes
    assert "art_url" not in attributes


def test_missing_album_becomes_empty_string():
    _, attributes = _build_now_playing_payload(artist="Queen", title="X", album=None, owned=False)
    assert attributes["media_album_name"] == ""
