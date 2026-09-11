"""
End-to-end test of the full pipeline in MOCK_MODE — no real hardware, no
network calls, no MongoDB connection required. Confirms the pieces are
wired together correctly.
"""
import os

os.environ["MOCK_MODE"] = "true"

from groove_tracker import config  # noqa: E402  (must set env var before import)
from groove_tracker.main import process_once  # noqa: E402


def test_process_once_renders_and_returns_key():
    assert config.MOCK_MODE is True

    key = process_once(last_shown=None)
    assert key == ("Queen", "Bohemian Rhapsody")

    out_path = os.path.join(config.MOCK_DISPLAY_OUTPUT_DIR, "now_playing.png")
    assert os.path.exists(out_path)


def test_process_once_skips_render_when_unchanged():
    # Calling again with the same key already "shown" should be a no-op
    # (returns the same key without re-rendering, though we don't assert
    # on the render call itself here — just that the key is stable).
    key = process_once(last_shown=("Queen", "Bohemian Rhapsody"))
    assert key == ("Queen", "Bohemian Rhapsody")
