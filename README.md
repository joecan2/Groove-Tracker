# Groove Tracker

Identifies whatever's playing on the turntable and shows it on a small
e-paper display — preferring the release you actually own in your
[DVinyl](https://github.com/Kyonew/DVinyl) collection (e.g. a *Greatest
Hits* comp) over whatever original studio album the recognition API
guesses.

Hardware: Raspberry Pi Zero WH + Waveshare 4.2" e-Paper Module + a line-out
tap on the turntable's signal to a powered speakers setup. Full wiring and
OS setup: [`docs/SETUP.md`](docs/SETUP.md).

## How it works

```
turntable line-out (tapped)
        │
        ▼
  audio_capture.py  ──►  identify.py (AudD)  ──►  collection_match.py (DVinyl / MongoDB)
                                                          │
                                                          ▼
                                                    display.py (e-paper)
```

`main.py` loops: record a short clip, ask AudD what it is, check whether
you own a release with that track, then render the result — preferring
your own release's title/format when there's a match. The display
auto-sizes text to fill the panel, shows album art when AudD's metadata
includes it, and clears itself (after a short debounce) once the
turntable stops or a track can't be identified, so it never shows stale
info indefinitely.

## Project layout

```
groove_tracker/
├── config.py            # settings, loaded from .env
├── audio_capture.py      # records from the line-in tap, applies CAPTURE_GAIN
├── identify.py            # AudD API wrapper, extracts album art URL
├── collection_match.py   # matches recognized tracks against your DVinyl collection
├── album_art.py           # fetches/crops album art for the display
├── display.py             # renders to the Waveshare e-paper panel (auto-sized text + art)
├── status.py               # writes/reads the JSON status snapshot the web UI reads
├── main.py                 # the loop tying it all together, incl. debounced display clearing
└── webui/                   # optional browser dashboard -- see "Web UI" below
waveshare_epd/               # vendored driver lib, project root (not in git — see docs/SETUP.md)
tests/                       # pytest suite, runs without real hardware
docs/SETUP.md               # complete wiring + install + troubleshooting guide
install.sh                   # one-command setup: packages, SPI, driver, venv, Samba, systemd, web UI
bootstrap.sh                 # clones this repo + runs install.sh, for a fresh Pi
systemd/groove-tracker.service      # template, filled in by install.sh
systemd/groove-tracker-web.service  # template for the web UI's service
```

## Web UI

A browser dashboard for managing the service without SSH — status, a live
copy of what's on the e-paper panel, Start/Stop/Restart, log tailing, and
a form-based `.env` editor. `install.sh` sets it up (its own systemd
service, plus a narrowly-scoped sudoers rule so it can control
`groove-tracker.service` without running as root). See
[`docs/SETUP.md`](docs/SETUP.md#web-ui) for what it looks like, how it's
hosted, and its security model (LAN-only, single shared password, no
HTTPS by default).

## Setup

See [`docs/SETUP.md`](docs/SETUP.md) for the complete guide (wiring,
`.env` reference, testing, troubleshooting). Quick version, on a freshly
flashed Pi with SSH enabled:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/groove-tracker/main/bootstrap.sh)
```

That clones this repo and runs `install.sh`, which handles system
packages, SPI, the Waveshare driver, the Python venv, a Samba file share,
and the systemd service (installed + enabled, not started yet). Then:

```bash
cd ~/groove-tracker
nano .env                # fill in AUDD_API_TOKEN, MONGO_URI, etc. -- see docs/SETUP.md
sudo systemctl start groove-tracker
```

## Mock mode

Most of this project needs real hardware (a turntable, the e-paper panel)
or paid API calls to actually run. Set `MOCK_MODE=true` in `.env` (or the
environment) and:

- `audio_capture.record_clip()` returns a bundled silent fixture clip instead of recording
- `identify.identify_song()` returns a fixed fake result (Queen — Bohemian Rhapsody) instead of calling AudD
- `collection_match` uses an in-memory fake collection instead of connecting to MongoDB
- `display.render_now_playing()` writes a PNG to `mock_output/` instead of talking to the e-paper panel

This lets the whole pipeline run end-to-end on any machine — useful for
development and for the test suite.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Hardware notes / gotchas

- This Pi (ARMv6, Zero WH) only supports **32-bit** Raspberry Pi OS.
- Debian trixie removed `libatlas-base-dev` — use `libopenblas-dev` instead (see docs/SETUP.md).
- The `waveshare_epd` driver library isn't on PyPI; it's vendored manually and gitignored.
- DVinyl's MongoDB field names may differ by instance/version — verify with `db.items.findOne({collectionType: "music"})` before trusting the defaults in `.env.example`.

## Home Assistant integration

Reports whether the turntable is actively playing to Home Assistant, so an automation can turn a nearby light on/off with the music. Based on actual audio signal level (not recognition success) — this also means AudD calls are skipped entirely during silence, saving API quota.

- `audio_capture.is_signal_present()` checks RMS level against `SILENCE_THRESHOLD`
- `home_assistant.set_playing_state()` POSTs to `binary_sensor.groove_tracker_playing` via the HA REST API every poll cycle
- A Home Assistant automation (`automation.groove_tracker_now_playing_light`) watches that entity and controls `light.now_playing_light`, with a 30-second debounce on the "stopped" transition to avoid flicker between tracks

Set `HA_URL` and `HA_TOKEN` in `.env` to enable — leave both blank to disable this feature entirely (the rest of the project works fine without it).
