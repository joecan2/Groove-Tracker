# CLAUDE.md

Context for Claude Code working in this repo.

## What this project is

A small Python service running on a Raspberry Pi Zero WH: it listens to a
turntable (tapped off the line-out feeding a pair of powered speakers),
identifies the playing track via the AudD recognition API, checks whether
the user owns a matching release in their self-hosted DVinyl vinyl-collection
app (MongoDB-backed, running on their Unraid server), and renders the
result to a small Waveshare 4.2" e-paper display.

The interesting design point: AudD will usually return the *original*
studio album for a track, but the user might own a *different* release
containing that same track (e.g. a Greatest Hits comp). `collection_match.py`
exists specifically to prefer what the user actually owns over AudD's guess.

## Architecture

```
audio_capture.record_clip()          -> WAV file path
identify.identify_song(wav_path)     -> {artist, title, album} | None
collection_match.find_owned_release(artist, title) -> DVinyl item dict | None
display.render_now_playing(artist, title, album, owned: bool)
main.process_once() / main.main_loop()  -> ties the above together, dedupes by (artist, title)
```

Each module's hardware/network dependency is isolated behind a `MOCK_MODE`
check (see config.py) so the pipeline is testable without the real Pi,
turntable, or DVinyl connection. **When modifying these modules, preserve
the mock branch** — it's what makes this project runnable and testable in
a normal dev sandbox (including this one).

## Environment

- Target hardware is a Raspberry Pi Zero WH: single-core **ARMv6, 32-bit
  only**. Don't suggest anything requiring 64-bit or multi-core assumptions
  for code that runs on the real device.
- Dependencies come from piwheels (prebuilt ARM wheels) on the real Pi —
  don't assume a fast source-compile environment there.
- `libatlas-base-dev` doesn't exist anymore on the Pi's OS (Debian
  trixie-based) — the numpy BLAS dependency is `libopenblas-dev` now. See
  docs/SETUP.md.
- The `waveshare_epd` driver library is vendored manually (not pip-
  installable) into `groove_tracker/waveshare_epd/` and is gitignored — it
  won't be present in this repo or in this sandbox. `display.py` only
  imports it inside the non-mock code path, so this is fine as long as
  that stays true.
- Real secrets (AudD token, Mongo URI) live in `.env`, gitignored. Use
  `.env.example` as the source of truth for what variables exist —keep it
  updated if you add new config.

## Running things in this sandbox

This sandbox has no turntable, no e-paper panel, and no MongoDB
connection, so:

```bash
export MOCK_MODE=true
python3 -m groove_tracker          # runs one loop iteration worth of mocked pipeline, repeats
pytest                              # unit + mock-mode integration tests, no hardware needed
```

Non-mock code paths (real `sounddevice` recording, the `waveshare_epd`
import, a real MongoDB connection) cannot be exercised here — don't try to
"fix" failures caused by missing hardware/libraries in those paths; that's
expected outside the real Pi.

## DVinyl integration specifics

DVinyl doesn't expose a documented public read API, so `collection_match.py`
connects directly to its MongoDB database with a read-only user. Field
names (`FIELD_ARTIST`, `FIELD_TITLE`, `FIELD_FORMAT`, `FIELD_TRACKLIST` in
config.py / .env) are configurable because they may not match the defaults
for every DVinyl instance — the user needs to confirm theirs with
`db.items.findOne({collectionType: "music"})` on their actual database.
Don't hardcode assumptions about this schema elsewhere in the code; go
through the configured field names.

## Testing conventions

- `tests/test_collection_match.py` — pure-Python matching logic (no I/O)
- `tests/test_main_mock_pipeline.py` — full pipeline in MOCK_MODE, no real hardware/network
- When adding features, prefer keeping new logic in pure functions that can
  be unit tested the same way, rather than deep inside hardware-touching
  code paths.

## Known open items

- `AUDD_API_TOKEN` and `MONGO_URI` in the user's real `.env` are
  placeholders until they sign up / set up the read-only Mongo user (see
  docs/SETUP.md steps 6–7).
- DVinyl schema field names haven't been verified against the user's real
  instance yet — the defaults in `.env.example` are best guesses.
