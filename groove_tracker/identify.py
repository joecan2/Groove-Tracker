"""Sends an audio clip to AudD for song recognition."""
import requests

from . import config

# Used in MOCK_MODE so the pipeline can be tested end-to-end without
# burning real AudD API calls. art_url points at the bundled mock fixture
# handling in album_art.py -- in MOCK_MODE the actual URL value is ignored,
# only its truthiness matters, so any non-empty placeholder works here.
MOCK_RESULT = {
    "artist": "Queen",
    "title": "Bohemian Rhapsody",
    "album": "A Night at the Opera",
    "art_url": "https://mock.local/art.jpg",
}


def _extract_art_url(result):
    """Pulls an artwork URL out of AudD's optional Apple Music/Spotify
    enrichment (only present because identify_song requests
    return=apple_music,spotify). Pure function -- no MOCK_MODE/network
    dependency, so it's safe to unit test against a plain dict.

    Prefers Apple Music's artwork, since its URL is a template that can be
    asked for a specific resolution; falls back to Spotify's largest image;
    returns None if neither is present (common for older/obscure releases
    that AudD's own match doesn't map to enriched metadata).
    """
    apple_music = result.get("apple_music") or {}
    artwork = apple_music.get("artwork") or {}
    url_template = artwork.get("url")
    if url_template:
        # Apple's template URL has literal "{w}x{h}" placeholders for the
        # pixel dimensions, e.g. ".../100x100bb.jpg" -> substitute a size
        # that's comfortably larger than anything we'll display.
        return url_template.replace("{w}", "600").replace("{h}", "600")

    spotify = result.get("spotify") or {}
    images = (spotify.get("album") or {}).get("images") or []
    if images:
        best = max(images, key=lambda img: img.get("width", 0))
        return best.get("url")

    return None


def identify_song(wav_path):
    """Returns a dict {artist, title, album} or None if nothing was recognized."""
    if config.MOCK_MODE:
        return dict(MOCK_RESULT)

    with open(wav_path, "rb") as f:
        response = requests.post(
            config.AUDD_API_URL,
            data={
                "api_token": config.AUDD_API_TOKEN,
                "return": "apple_music,spotify",
            },
            files={"file": f},
            timeout=20,
        )
    response.raise_for_status()
    data = response.json()

    if data.get("status") != "success" or not data.get("result"):
        return None

    result = data["result"]
    return {
        "artist": result.get("artist", "Unknown Artist"),
        "title": result.get("title", "Unknown Title"),
        "album": result.get("album", ""),
        "art_url": _extract_art_url(result),
    }
