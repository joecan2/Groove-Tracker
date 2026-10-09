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


def test_form_shows_the_real_default_for_a_setting_missing_from_env():
    from groove_tracker import config
    from groove_tracker.webui.env_editor import form_value

    assert form_value("HA_PLAYING_ENTITY_ID", {}) == config.HA_PLAYING_ENTITY_ID
    assert form_value("HA_PLAYING_ENTITY_ID", {}) != ""
    # An explicit value in .env always wins.
    assert form_value("HA_PLAYING_ENTITY_ID", {"HA_PLAYING_ENTITY_ID": "binary_sensor.custom"}) == "binary_sensor.custom"
    # None defaults (e.g. AUDIO_DEVICE = system default) show as blank.
    assert form_value("AUDIO_DEVICE", {}) == ""


def test_saving_the_form_never_creates_blank_overrides_for_unset_keys():
    from groove_tracker.webui.env_editor import updates_from_form

    form = {"HA_PLAYING_ENTITY_ID": "", "SAMPLE_RATE": "48000", "AUDD_API_TOKEN": ""}
    updates = updates_from_form(form, existing_env={"SAMPLE_RATE": "44100", "AUDD_API_TOKEN": "secret"})

    assert "HA_PLAYING_ENTITY_ID" not in updates  # not in .env, blank -> left alone
    assert "AUDD_API_TOKEN" not in updates  # blank secret -> keep current
    assert updates["SAMPLE_RATE"] == "48000"


def test_a_key_already_in_env_can_still_be_deliberately_blanked():
    from groove_tracker.webui.env_editor import updates_from_form

    # e.g. HA_URL blank = disable Home Assistant; that must stay possible.
    updates = updates_from_form({"HA_URL": ""}, existing_env={"HA_URL": "http://10.0.0.2:8123"})

    assert updates["HA_URL"] == ""
