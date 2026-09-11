"""Sends an audio clip to AudD for song recognition."""
import requests

from . import config

# Used in MOCK_MODE so the pipeline can be tested end-to-end without
# burning real AudD API calls.
MOCK_RESULT = {
    "artist": "Queen",
    "title": "Bohemian Rhapsody",
    "album": "A Night at the Opera",
}


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
    }
