"""Reads/writes the project's .env file for the web UI's config page.

Pure functions apart from the two that touch the filesystem (read_env_file/
write_env_file) -- parse_env_text/render_env_text/apply_updates take and
return plain strings/dicts, so the update logic itself is unit-testable
without a real .env file (see tests/test_webui_env_editor.py), same
pattern as the rest of this project's hardware-touching modules.
"""
import os
import secrets

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

# One entry per .env variable the config page edits, grouped for display.
# `secret=True` means: never render the current value into the page (not
# even in an input's `value` attribute) -- show a placeholder instead, and
# only touch the variable if the submitted field was non-blank.
FIELDS = [
    ("Mock mode", [
        ("MOCK_MODE", "bool", "Mock mode", False,
         "Swap in fake hardware/network for dev/testing off the real Pi. Leave off on the real device."),
    ]),
    ("AudD (song recognition)", [
        ("AUDD_API_TOKEN", "secret", "AudD API token", True, "From https://audd.io"),
    ]),
    ("Audio capture", [
        ("AUDIO_DEVICE", "text", "Audio device", False, "Blank = system default input."),
        ("SAMPLE_RATE", "number", "Sample rate", False, ""),
        ("CHANNELS", "number", "Channels", False, "Set to 1 if your adapter is mono-only."),
        ("CLIP_SECONDS", "number", "Clip length (seconds)", False, ""),
        ("CAPTURE_GAIN", "number", "Capture gain", False,
         "Software boost for adapters with no hardware gain control. See docs/SETUP.md."),
        ("TMP_AUDIO_MAX_AGE_SECONDS", "number", "Stale recording max age (seconds)", False, ""),
    ]),
    ("DVinyl / MongoDB", [
        ("MONGO_URI", "secret", "MongoDB URI", True, "mongodb://user:pass@host:27017/dvinyl?authSource=dvinyl"),
        ("MONGO_DB_NAME", "text", "Database name", False, ""),
        ("MONGO_COLLECTION_NAME", "text", "Collection name", False, ""),
        ("MONGO_FILTER_FIELD", "text", "Filter field", False, "Empty = query every document."),
        ("MONGO_FILTER_VALUE", "text", "Filter value", False, ""),
        ("FIELD_ARTIST", "text", "Artist field name", False, ""),
        ("FIELD_TITLE", "text", "Title field name", False, ""),
        ("FIELD_FORMAT", "text", "Format field name", False, ""),
        ("FIELD_TRACKLIST", "text", "Tracklist field name", False, ""),
    ]),
    ("Display", [
        ("DISPLAY_MODEL", "text", "Waveshare driver module", False, "e.g. epd4in2_V2"),
        ("POLL_INTERVAL_SECONDS", "number", "Poll interval (seconds)", False, ""),
        ("SILENCE_THRESHOLD", "number", "Silence threshold (RMS)", False, ""),
        ("SILENCE_CLEAR_SECONDS", "number", "Clear after silence (seconds)", False, ""),
        ("UNRECOGNIZED_CLEAR_SECONDS", "number", "Clear after unrecognized (seconds)", False, ""),
    ]),
    ("Home Assistant", [
        ("HA_URL", "text", "Home Assistant URL", False, "e.g. http://192.168.1.50:8123 -- blank disables this feature."),
        ("HA_TOKEN", "secret", "Long-lived access token", True, ""),
        ("HA_PLAYING_ENTITY_ID", "text", "Playing entity ID", False, ""),
    ]),
    ("Web UI", [
        ("WEBUI_PORT", "number", "Port", False, ""),
        ("WEBUI_PASSWORD", "secret", "Login password", True, "Blank disables login -- only do that on a fully trusted LAN."),
    ]),
]

_ALL_KEYS = {key for _, fields in FIELDS for key, *_ in fields}


def read_env_file():
    """Returns the raw text of .env, or "" if it doesn't exist yet."""
    try:
        with open(ENV_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except UnicodeDecodeError:
        with open(ENV_PATH, encoding="cp1252") as f:
            return f.read()


def parse_env_text(text):
    """Parses KEY=value lines into a dict, ignoring blank lines and
    comments -- just enough to populate the form, not a full .env parser
    (no quoting/escaping support, matching the plain values install.sh's
    set_env_var and config.py's os.getenv already assume throughout).
    """
    values = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def apply_updates(text, updates):
    """Returns `text` with each key in `updates` set to its new value --
    replacing an existing `KEY=...` line in place (preserving every other
    line, including comments) if present, appending a new `KEY=value` line
    otherwise. Keys not in `updates` are left completely untouched, which
    is what lets the config page only send the fields the user actually
    changed.
    """
    lines = text.splitlines()
    remaining = dict(updates)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.partition("=")[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"

    for key, value in remaining.items():
        lines.append(f"{key}={value}")

    return "\n".join(lines) + "\n"


def write_env_file(text):
    tmp_path = ENV_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp_path, ENV_PATH)


def generate_secret_key():
    """A random value for WEBUI_SECRET_KEY (Flask session signing) --
    generated once by install.sh (or the first config save, if missing)
    and then left alone, since changing it invalidates every existing
    login session.
    """
    return secrets.token_hex(32)


def current_values():
    """Dict of every known field's current value, straight from .env (no
    masking) -- for internal use (e.g. deciding whether WEBUI_PASSWORD is
    set at all). The config page template must NOT be handed this
    directly for secret fields; see build_form_groups().
    """
    return parse_env_text(read_env_file())


def build_form_groups():
    """Returns FIELDS with each field's current value attached, for
    rendering the config form -- secret fields get value="" always (never
    echoing a real secret back into HTML), plain fields get their real
    current value.
    """
    values = current_values()
    groups = []
    for group_name, fields in FIELDS:
        rendered = []
        for key, field_type, label, secret, help_text in fields:
            value = "" if secret else values.get(key, "")
            rendered.append({
                "key": key,
                "type": field_type,
                "label": label,
                "secret": secret,
                "help": help_text,
                "value": value,
                "is_set": bool(values.get(key)) if secret else None,
            })
        groups.append((group_name, rendered))
    return groups
