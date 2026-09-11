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
MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "dvinyl")
MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "items")
MUSIC_COLLECTION_TYPE = os.getenv("MUSIC_COLLECTION_TYPE", "music")

# Field names inside a DVinyl music item document.
# VERIFY these against your own instance:
#   db.items.findOne({collectionType: "music"})
# and adjust your .env if your field names differ.
FIELD_ARTIST = os.getenv("FIELD_ARTIST", "artist")
FIELD_TITLE = os.getenv("FIELD_TITLE", "title")
FIELD_FORMAT = os.getenv("FIELD_FORMAT", "format")
FIELD_TRACKLIST = os.getenv("FIELD_TRACKLIST", "tracklist")

# --- Display ---
DISPLAY_MODEL = os.getenv("DISPLAY_MODEL", "epd4in2")  # waveshare_epd submodule name
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "25"))

# In mock mode, rendered images are written here instead of to real hardware.
MOCK_DISPLAY_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "mock_output")
