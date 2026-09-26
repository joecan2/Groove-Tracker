"""
Configuration, loaded from environment variables (via a .env file in
development, or real environment variables when run as a systemd service).

Copy .env.example to .env and fill in your real values — .env is
gitignored so secrets never get committed.
"""
import os

from dotenv import load_dotenv

try:
    load_dotenv()
except UnicodeDecodeError:
    # A .env file edited/saved on Windows (e.g. via Notepad's default
    # "ANSI" save option) can end up saved as Windows-1252 instead of
    # UTF-8. This shows up as a decode error on bytes like 0x97 -- an em
    # dash (-) in that encoding, easy to pick up by copy-pasting from
    # .env.example's comments. Retry once assuming that encoding rather
    # than crashing the whole service outright; every value dotenv reads
    # is treated as plain text either way, so this is safe even if the
    # file turns out to be UTF-8 with no non-ASCII characters at all.
    load_dotenv(encoding="cp1252")


def _bool_env(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# --- Mock mode ---
# When true, hardware-specific code paths (real audio recording, the
# Waveshare e-paper driver) are skipped in favor of stand-ins that work on
# any machine — useful for development off the actual Pi, and for Claude
# Code to be able to run and test this project. Set MOCK_MODE=true in your
# .env when NOT running on the actual Pi with the real hardware attached.
MOCK_MODE = _bool_env("MOCK_MODE", default=False)

# --- AudD (song recognition) ---
AUDD_API_TOKEN = os.getenv("AUDD_API_TOKEN", "")
AUDD_API_URL = "https://api.audd.io/"

# --- Audio capture ---
AUDIO_DEVICE = os.getenv("AUDIO_DEVICE") or None  # None = system default input
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "44100"))
CHANNELS = int(os.getenv("CHANNELS", "2"))
CLIP_SECONDS = int(os.getenv("CLIP_SECONDS", "12"))

# Fixed linear gain applied to every captured sample before it's written to
# disk. Some audio interfaces (e.g. the Behringer UCA202) have no hardware
# capture-level control at all, so a clean line-level signal can still come
# in quiet enough (low RMS) that fingerprinting services struggle with it —
# not because it's inaudible, but because the signal only occupies a small
# slice of the 16-bit range, so its useful detail is more exposed to
# quantization noise. A fixed multiplier fixes that without changing the
# balance between silence and signal (both get scaled by the same amount,
# so SILENCE_THRESHOLD doesn't need retuning) — unlike per-clip auto-
# normalization, which would also amplify pure noise/hum during silent
# gaps up to "loud", breaking silence detection entirely.
#
# To tune: record a clip, check its level with get_audio_level(), and pick
# a gain that brings it up to roughly 0.2-0.3. Peaks above ~80% of full
# scale are soft-limited (see _soft_limit in audio_capture.py) rather than
# hard-clipped, as a hedge against records mastered louder than whatever
# you tuned against -- but that's a safety net, not a tuning target, so
# aim below it rather than relying on it.
CAPTURE_GAIN = float(os.getenv("CAPTURE_GAIN", "1.0"))

# How old (seconds) a leftover recording in .tmp_audio/ must be before the
# periodic cleanup sweep deletes it. Recordings are normally deleted
# within seconds by the main loop right after use -- this only ever
# catches ones orphaned by a crash, so the default is deliberately
# generous (24 hours) rather than tuned tightly.
TMP_AUDIO_MAX_AGE_SECONDS = int(os.getenv("TMP_AUDIO_MAX_AGE_SECONDS", "86400"))

# In mock mode, audio_capture returns this fixture file instead of recording.
MOCK_AUDIO_FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "tests", "fixtures", "sample_clip.wav"
)

# --- DVinyl / MongoDB ---
# Use a dedicated read-only user, not your admin credentials — see
# docs/SETUP.md for how to create one.
#
# Confirmed against a real DVinyl instance via:
#   db.albums.findOne()
# DVinyl has no separate "items" collection or "collectionType" field —
# everything lives in "albums", and the entry type is the "kind" field
# (e.g. "Music"). MONGO_FILTER_FIELD/VALUE control that filter; set
# MONGO_FILTER_FIELD to an empty string to skip filtering entirely (query
# every document) if your instance doesn't use "kind" the same way.
MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "dvinyl")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "albums")
MONGO_FILTER_FIELD = os.getenv("MONGO_FILTER_FIELD", "kind")
MONGO_FILTER_VALUE = os.getenv("MONGO_FILTER_VALUE", "Music")

# Field names inside a DVinyl album document. Confirmed defaults below
# match a real instance, but field names can still vary — verify yours
# with `db.albums.findOne()` and adjust .env if needed.
FIELD_ARTIST = os.getenv("FIELD_ARTIST", "artist")
FIELD_TITLE = os.getenv("FIELD_TITLE", "title")
FIELD_FORMAT = os.getenv("FIELD_FORMAT", "media_type")
FIELD_TRACKLIST = os.getenv("FIELD_TRACKLIST", "tracklist")

# --- Display ---
DISPLAY_MODEL = os.getenv("DISPLAY_MODEL", "epd4in2")  # waveshare_epd submodule name
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "25"))

# In mock mode, rendered images are written here instead of to real hardware.
MOCK_DISPLAY_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "mock_output")

# --- Silence detection ---
# RMS amplitude (roughly 0-1) above which a clip counts as "something is
# playing" rather than silence between records. Tune if you get false
# on/off flips — lower it if quiet passages get marked as silent, raise it
# if turntable motor hum alone triggers "playing".
SILENCE_THRESHOLD = float(os.getenv("SILENCE_THRESHOLD", "0.02"))

# --- Display staleness ---
# The display only ever gets a fresh render when a *new* song is
# recognized -- without these, whatever was last shown would stay on
# screen indefinitely after the turntable stops, or after a different,
# unrecognized track starts playing. Both are debounced (not instant) so
# a normal pause between tracks or while flipping a record doesn't blank
# the screen.
#
# Seconds of continuous silence before the display is cleared.
SILENCE_CLEAR_SECONDS = int(os.getenv("SILENCE_CLEAR_SECONDS", "30"))
# Seconds of continuous "something is playing, but AudD isn't recognizing
# it" before the (now-stale) previously-shown song info is cleared.
UNRECOGNIZED_CLEAR_SECONDS = int(os.getenv("UNRECOGNIZED_CLEAR_SECONDS", "60"))

# --- Home Assistant ---
# Optional — leave HA_URL/HA_TOKEN blank to disable this feature entirely.
# HA_TOKEN is a Long-Lived Access Token: create one in Home Assistant under
# your Profile page (scroll to "Long-lived access tokens" -> Create Token).
HA_URL = os.getenv("HA_URL", "")
HA_TOKEN = os.getenv("HA_TOKEN", "")
HA_PLAYING_ENTITY_ID = os.getenv("HA_PLAYING_ENTITY_ID", "binary_sensor.groove_tracker_playing")

# --- Web UI ---
# Optional local dashboard (see groove_tracker/webui/) for controlling the
# service, viewing logs/status, and editing .env from a browser instead of
# SSH. install.sh sets WEBUI_PASSWORD and WEBUI_SECRET_KEY for you; leaving
# WEBUI_PASSWORD blank disables login entirely, so only set this up on a
# trusted LAN.
WEBUI_PORT = int(os.getenv("WEBUI_PORT", "8420"))
WEBUI_PASSWORD = os.getenv("WEBUI_PASSWORD", "")
WEBUI_SECRET_KEY = os.getenv("WEBUI_SECRET_KEY", "")

# Where main.py writes a small JSON snapshot of pipeline state
# (playing/last recognized song/errors), and where display.py always saves
# a PNG copy of whatever's currently on the display (real hardware or
# mock) -- both read by the web UI, which runs as a separate process and
# so can't just read these out of main_loop's in-memory state directly.
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", ".state")
STATUS_PATH = os.path.join(STATE_DIR, "status.json")
DISPLAY_PREVIEW_PATH = os.path.join(STATE_DIR, "now_playing.png")
