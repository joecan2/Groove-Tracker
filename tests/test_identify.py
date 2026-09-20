"""
Tests _extract_art_url directly -- a pure function over a plain dict, no
MOCK_MODE or network dependency.
"""
from groove_tracker.identify import _extract_art_url


def test_prefers_apple_music_artwork_and_substitutes_size():
    result = {
        "apple_music": {"artwork": {"url": "https://example.com/art/{w}x{h}bb.jpg"}},
        "spotify": {"album": {"images": [{"url": "https://spotify.example/big.jpg", "width": 640}]}},
    }
    assert _extract_art_url(result) == "https://example.com/art/600x600bb.jpg"


def test_falls_back_to_largest_spotify_image_when_no_apple_music():
    result = {
        "spotify": {
            "album": {
                "images": [
                    {"url": "https://spotify.example/small.jpg", "width": 64},
                    {"url": "https://spotify.example/big.jpg", "width": 640},
                ]
            }
        }
    }
    assert _extract_art_url(result) == "https://spotify.example/big.jpg"


def test_returns_none_when_no_artwork_metadata_present():
    assert _extract_art_url({}) is None
    assert _extract_art_url({"apple_music": {}}) is None
    assert _extract_art_url({"spotify": {"album": {"images": []}}}) is None
