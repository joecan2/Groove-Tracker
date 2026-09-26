"""Tests the pure .env text-rewriting logic behind the web UI's config
page -- parse_env_text/apply_updates take and return plain strings, no
filesystem access, so they're testable the same way as the rest of this
project's non-hardware-touching logic.
"""
from groove_tracker.webui.env_editor import apply_updates, parse_env_text


def test_parse_env_text_ignores_comments_and_blank_lines():
    text = "# a comment\n\nMOCK_MODE=true\nAUDD_API_TOKEN=abc123\n"
    assert parse_env_text(text) == {"MOCK_MODE": "true", "AUDD_API_TOKEN": "abc123"}


def test_apply_updates_replaces_an_existing_key_in_place():
    text = "MOCK_MODE=false\nCAPTURE_GAIN=1.0\n"
    result = apply_updates(text, {"CAPTURE_GAIN": "4.5"})
    assert "CAPTURE_GAIN=4.5" in result
    assert "MOCK_MODE=false" in result
    # Line order/count is otherwise untouched.
    assert result.count("\n") == 2


def test_apply_updates_preserves_comments_and_other_lines():
    text = "# --- Audio capture ---\nCAPTURE_GAIN=1.0\n"
    result = apply_updates(text, {"CAPTURE_GAIN": "5"})
    assert "# --- Audio capture ---" in result
    assert "CAPTURE_GAIN=5" in result


def test_apply_updates_appends_a_missing_key():
    text = "MOCK_MODE=false\n"
    result = apply_updates(text, {"WEBUI_PORT": "8420"})
    assert "MOCK_MODE=false" in result
    assert "WEBUI_PORT=8420" in result


def test_apply_updates_leaves_untouched_keys_alone():
    text = "AUDD_API_TOKEN=secret\nMOCK_MODE=false\n"
    result = apply_updates(text, {"MOCK_MODE": "true"})
    # A blank/omitted secret update must never blank out the real value --
    # this is what lets the config page's "leave blank to keep" behavior
    # for secret fields actually work.
    assert "AUDD_API_TOKEN=secret" in result
    assert "MOCK_MODE=true" in result
