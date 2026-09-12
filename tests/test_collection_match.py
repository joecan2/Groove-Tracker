from groove_tracker.collection_match import (
    MOCK_COLLECTION,
    _find_best_candidate,
    _normalize,
    _titles_match,
)


def test_normalize_strips_punctuation_and_case():
    assert _normalize("Bohemian Rhapsody!") == "bohemian rhapsody"
    assert _normalize("  A Night at the Opera  ") == "a night at the opera"


def test_titles_match_exact():
    assert _titles_match("Bohemian Rhapsody", "Bohemian Rhapsody")


def test_titles_match_minor_variation():
    # trailing remaster tags etc. should still match above threshold
    assert _titles_match("Bohemian Rhapsody", "Bohemian Rhapsody (Remastered)", threshold=0.7)


def test_titles_match_rejects_different_songs():
    assert not _titles_match("Bohemian Rhapsody", "Killer Queen")


def test_find_best_candidate_prefers_vinyl_over_other_formats():
    # Both mock releases contain "Bohemian Rhapsody" by Queen; the vinyl
    # "Greatest Hits" copy should win over the CD "A Night at the Opera".
    match = _find_best_candidate(MOCK_COLLECTION, "Queen", "Bohemian Rhapsody")
    assert match is not None
    assert match["title"] == "Greatest Hits"
    assert match["media_type"] == "Vinyl"


def test_find_best_candidate_no_match_returns_none():
    match = _find_best_candidate(MOCK_COLLECTION, "Some Other Artist", "Some Other Song")
    assert match is None


def test_find_best_candidate_requires_artist_match():
    # Track title matches, but artist doesn't — should not match.
    match = _find_best_candidate(MOCK_COLLECTION, "Not Queen", "Bohemian Rhapsody")
    assert match is None
