"""Fetches and prepares album artwork for the e-paper display.

Artwork is best-effort: AudD only returns an art URL when the enriched
Apple Music/Spotify metadata includes one (`identify.py`'s
`_extract_art_url`), and a fetch can always fail (network hiccup, dead
link, unexpected response). None of that should ever break the display --
a track with no art, or a failed download, just renders text-only, so
every failure path here returns None rather than raising.
"""
import io
import os

import requests
from PIL import Image

from . import config

# In MOCK_MODE, this fixture stands in for a downloaded image, so the mock
# pipeline can exercise the "art is present" layout without a network call.
MOCK_ALBUM_ART_FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "tests", "fixtures", "mock_album_art.png"
)


def get_album_art(art_url, size):
    """Returns a square, grayscale PIL Image of `size` x `size`, or None if
    there's no art URL or it couldn't be fetched/decoded.
    """
    if not art_url:
        return None

    if config.MOCK_MODE:
        try:
            image = Image.open(MOCK_ALBUM_ART_FIXTURE)
            image.load()
        except (FileNotFoundError, OSError):
            return None
        return _fit_square(image, size)

    try:
        response = requests.get(art_url, timeout=10)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        image.load()
    except (requests.RequestException, OSError):
        print(f"[album_art] Could not fetch artwork from {art_url}", flush=True)
        return None

    return _fit_square(image, size)


def _fit_square(image, size):
    """Center-crops to a square and resizes to `size` x `size`, in
    grayscale. Pure function -- no network or MOCK_MODE dependency, so it's
    safe to unit test directly against any in-memory image.
    """
    image = image.convert("L")
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    return image.resize((size, size), Image.LANCZOS)
