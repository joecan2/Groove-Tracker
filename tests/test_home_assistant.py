"""
Tests the pure payload-construction helper directly (_build_now_playing_payload),
not the public set_now_playing/set_playing_state wrappers -- those branch on
config.MOCK_MODE and make a real network call otherwise, same reasoning as
_compute_rms_level in test_audio_capture.py. See CLAUDE.md's testing
conventions.
"""
from groove_tracker.home_assistant import _build_now_playing_payload


def test_no_artist_means_not_playing():
    state, attributes = _build_now_playing_payload(
        artist=None, title=None, album=None, owned=False, art_url=None
    )
    assert state == "Not playing"
    # No song-specific attributes should leak through when nothing's
    # recognized -- a dashboard card reading these shouldn't see stale
    # artist/title/album data sitting on a "Not playing" state.
    assert "artist" not in attributes
    assert "title" not in attributes
    assert "album" not in attributes
    assert "entity_picture" not in attributes


def test_recognized_song_sets_state_and_attributes():
    state, attributes = _build_now_playing_payload(
        artist="The Who", title="Baba O'Riley", album="Who's Next", owned=True, art_url=None
    )
    assert state == "Baba O'Riley — The Who"
    assert attributes["artist"] == "The Who"
    assert attributes["title"] == "Baba O'Riley"
    assert attributes["album"] == "Who's Next"
    assert attributes["owned"] is True


def test_art_url_is_also_set_as_entity_picture():
    # entity_picture is what Home Assistant's frontend actually reads to
    # show a thumbnail on a card -- without also setting it (not just a
    # plain "art_url" attribute), the album art wouldn't show up
    # automatically on a Picture Entity/Glance card.
    _, attributes = _build_now_playing_payload(
        artist="Queen", title="Bohemian Rhapsody", album="A Night at the Opera",
        owned=False, art_url="https://example.com/art.jpg",
    )
    assert attributes["art_url"] == "https://example.com/art.jpg"
    assert attributes["entity_picture"] == "https://example.com/art.jpg"


def test_no_art_url_omits_entity_picture():
    _, attributes = _build_now_playing_payload(
        artist="Queen", title="Bohemian Rhapsody", album="A Night at the Opera",
        owned=False, art_url=None,
    )
    assert "art_url" not in attributes
    assert "entity_picture" not in attributes


def test_state_is_truncated_to_ha_state_limit():
    # Home Assistant rejects state values over 255 characters -- defensive
    # truncation so a pathological AudD result can't turn into a hard
    # failure reporting to Home Assistant.
    long_title = "A" * 300
    state, _ = _build_now_playing_payload(
        artist="Artist", title=long_title, album="Album", owned=False, art_url=None
    )
    assert len(state) <= 255
