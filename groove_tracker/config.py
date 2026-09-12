"""
Configuration, loaded from environment variables (via a .env file in
development, or real environment variables when run as a systemd service).

Copy .env.example to .env and fill in your real values — .env is
gitignored so secrets never get committed.
"""
import os

from dotenv import load_dotenv

load_dotenv()


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

# --- Home Assistant ---
# Optional — leave HA_URL/HA_TOKEN blank to disable this feature entirely.
# HA_TOKEN is a Long-Lived Access Token: create one in Home Assistant under
# your Profile page (scroll to "Long-lived access tokens" -> Create Token).
HA_URL = os.getenv("HA_URL", "")
HA_TOKEN = os.getenv("HA_TOKEN", "")
HA_PLAYING_ENTITY_ID = os.getenv("HA_PLAYING_ENTITY_ID", "binary_sensor.groove_tracker_playing")
