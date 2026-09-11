"""
Looks up a recognized track against your DVinyl collection so the display
can show the release YOU own (e.g. a Greatest Hits comp) instead of
whatever original studio album AudD guesses.

The matching functions (_normalize, _titles_match, _find_best_candidate)
are pure Python and unit-tested in tests/ without needing a real MongoDB
connection. Only _get_music_items() touches the network.
"""
import difflib

from . import config

_client = None
_music_items_cache = None

# A couple of fake owned releases, used in MOCK_MODE so the matching logic
# can be exercised without a real DVinyl/MongoDB connection.
MOCK_COLLECTION = [
    {
        "artist": "Queen",
        "title": "Greatest Hits",
        "format": "Vinyl",
        "tracklist": [{"title": "Bohemian Rhapsody"}, {"title": "Killer Queen"}],
    },
    {
        "artist": "Queen",
        "title": "A Night at the Opera",
        "format": "CD",
        "tracklist": [{"title": "Bohemian Rhapsody"}, {"title": "Love of My Life"}],
    },
]


def _get_music_items():
    """Connects to MongoDB once and caches your music collection in memory."""
    global _client, _music_items_cache
    if _music_items_cache is not None:
        return _music_items_cache

    if config.MOCK_MODE:
        _music_items_cache = MOCK_COLLECTION
        return _music_items_cache

    from pymongo import MongoClient

    _client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
    db = _client[config.MONGO_DB_NAME]
    coll = db[config.MONGO_COLLECTION_NAME]

    items = list(coll.find({"collectionType": config.MUSIC_COLLECTION_TYPE}))
    _music_items_cache = items
    return items


def refresh_cache():
    """Call periodically (e.g. once an hour) in case your collection changes."""
    global _music_items_cache
    _music_items_cache = None
    _get_music_items()


def _normalize(text):
    return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()


def _titles_match(a, b, threshold=0.85):
    a, b = _normalize(a), _normalize(b)
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def _find_best_candidate(items, artist, track_title):
    """Pure matching logic, separated out so it's testable without a DB."""
    candidates = []

    for item in items:
        item_artist = item.get(config.FIELD_ARTIST, "")
        if not _titles_match(item_artist, artist, threshold=0.8):
            continue

        tracklist = item.get(config.FIELD_TRACKLIST, [])
        for track in tracklist:
            track_name = track.get("title", "") if isinstance(track, dict) else str(track)
            if _titles_match(track_name, track_title):
                candidates.append(item)
                break

    if not candidates:
        return None

    # Prefer a vinyl copy, since that's presumably what's on the turntable.
    for item in candidates:
        if str(item.get(config.FIELD_FORMAT, "")).lower() == "vinyl":
            return item

    return candidates[0]


def find_owned_release(artist, track_title):
    """
    Returns the best-matching item dict from your DVinyl collection, or None
    if you don't own a release containing this track by this artist.
    """
    items = _get_music_items()
    return _find_best_candidate(items, artist, track_title)
