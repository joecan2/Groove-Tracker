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
audio_capture.is_signal_present()    -> bool (RMS level vs SILENCE_THRESHOLD)
home_assistant.set_playing_state()   -> reports bool to binary_sensor.groove_tracker_playing via HA REST API
identify.identify_song(wav_path)     -> {artist, title, album} | None   (skipped entirely if not playing)
collection_match.find_owned_release(artist, title) -> DVinyl item dict | None
display.render_now_playing(artist, title, album, owned: bool)
main.process_once() / main.main_loop()  -> ties the above together, dedupes by (artist, title)
```

"Is playing" is derived from actual audio signal level, not from AudD recognition success — recognition can fail for reasons unrelated to whether music is playing (network hiccup, API quota, background noise), and silence detection also lets us skip the AudD call entirely when idle.

Each module's hardware/network dependency is isolated behind a `MOCK_MODE`
check (see config.py) so the pipeline is testable without the real Pi,
turntable, or DVinyl connection. **When modifying these modules, preserve
the mock branch** — it's what makes this project runnable and testable in
a normal dev sandbox (including this one).

**Testability pattern:** hardware-touching public functions (`get_audio_level`, `find_owned_release`, etc.) branch on `config.MOCK_MODE`, which is fixed at first import of the config module — this makes them unsuitable for testing with per-test environment variable overrides, since Python caches the module. Where the underlying logic is worth testing directly, it's split into a `_`-prefixed pure function with no MOCK_MODE dependency (`_compute_rms_level`, `_find_best_candidate`) that tests call directly. Follow this pattern for new hardware-touching features.

## Environment

- Target hardware is a Raspberry Pi Zero WH: single-core **ARMv6, 32-bit
  only**. Don't suggest anything requiring 64-bit or multi-core assumptions
  for code that runs on the real device.
- Dependencies come from piwheels (prebuilt ARM wheels) on the real Pi —
  don't assume a fast source-compile environment there.
- `libatlas-base-dev` doesn't exist anymore on the Pi's OS (Debian
  trixie-based) — the numpy BLAS dependency is `libopenblas-dev` now. See
  docs/SETUP.md.
- Pillow's text rendering (used in `display.py` to draw the artist/title/
  album text) needs the system `libfreetype6` library — without it,
  `render_now_playing()` raises `libfreetype.so.6: cannot open shared
  object file` on every call, which the broad `except Exception` in
  `main.main_loop()` swallows and logs, so the visible symptom is a
  service that runs and recognizes songs fine but never actually updates
  the display. Installed by `install.sh`.
- The `waveshare_epd` driver library is vendored manually (not pip-
  installable) at the project root — `waveshare_epd/`, a sibling of
  `groove_tracker/`, NOT nested inside it — and is gitignored. It must be
  at the root because `display.py` imports it as a bare top-level module
  (`import waveshare_epd.X`), which only resolves if the project root
  (not the package directory) is on the Python path.
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

## Display layout and album art

`display.py` auto-sizes text rather than using fixed font sizes: `_fit_text`
tries font sizes from large down to small and picks the largest one whose
wrapped lines (`_wrap_by_pixel`, measured with actual rendered pixel
widths via `draw.textlength`, not a fixed character count) fit the
allotted box. This is what makes a short title like "Baba O'Riley" fill
the screen while a long one still shrinks to fit instead of overflowing.
`_wrap_by_pixel` also hard-splits (`_split_long_word`) any single word
that's wider than the column on its own -- this matters more than it
might seem, since adding album art narrows the text column to ~215px, and
an ordinary word at a large bold font size can exceed that on its own.

Album art comes from `album_art.py`, fed by an `art_url` that
`identify.py`'s `_extract_art_url` pulls out of AudD's optional Apple
Music/Spotify enrichment (`return=apple_music,spotify` in the API
request) -- AudD itself doesn't return artwork directly. Apple Music's
artwork URL is a template with literal `{w}x{h}` placeholders that must
be substituted with a real size before it's a fetchable URL; Spotify's
`album.images` list is the fallback, largest first. Art is always
optional: no URL, a failed fetch, or a decode error all return `None`
rather than raising, and `display.py` falls back to a full-width
text-only layout in that case -- never assume `art_url`/the fetched image
will be present.

## Display staleness (debounced clearing)

The display only gets a fresh render when a *new* song is recognized, so
without explicit handling, whatever was last shown would stay up
indefinitely after the turntable stops, or after a different,
unrecognized track starts playing (looking like recognition is still
working when it's actually just stale). `main.py` handles both, via a
small state dict threaded through `process_once`/`main_loop` (see
`_initial_state`) instead of the old bare `last_shown` tuple. The dict's
`screen_state` field is a tri-state (`"blank"` / `"song"` / `"unrecognized"`)
-- not a plain boolean -- because there are three distinct things the
panel can be showing, not two:

- `_maybe_clear_for_silence` blanks the display (`display.clear_display()`)
  after `SILENCE_CLEAR_SECONDS` of *continuous* silence. This fires
  regardless of whether `screen_state` was `"song"` or `"unrecognized"` --
  a stale "Song not recognized" message needs clearing too, once the
  turntable actually stops, not just stale song info.
- `_maybe_clear_for_unrecognized` renders an explicit **"Song not
  recognized"** message (`display.render_message()`) after
  `UNRECOGNIZED_CLEAR_SECONDS` of the turntable playing something AudD
  keeps failing to recognize -- so the person looking at the panel can
  tell "it's listening but can't identify this" apart from "nothing is
  playing" or "the whole thing crashed," which look identical on a panel
  that goes to blank either way.

Both are **debounced**, not instant -- the timer starts on the first
silent/unrecognized poll and only actually acts once it's held past the
threshold on a later poll, and each is also guarded on `screen_state`
already matching its target (`"blank"` / `"unrecognized"`) so it doesn't
re-render the same thing (and re-flicker the panel) on every subsequent
poll while a streak continues. This matters because a normal pause
between tracks or while flipping a record would otherwise blank-flash the
panel on every gap, which is both annoying and an unnecessary e-paper
refresh (these panels visibly flicker on a full refresh, and refreshes
aren't meant to happen constantly). Same reasoning as the existing 30s
debounce on the Home Assistant light's off-transition.

When either debounce fires, `state["last_shown"]` is reset to `None` --
without that, the same song resuming after a pause would be (wrongly)
treated as "unchanged" and skipped, leaving the display showing the old
message/blank even though something is playing again.

`render_message()` in `display.py` shares `_fit_text` with the normal
song-info layout, but composes a simple full-panel centered message
(`_compose_message_image`) instead of the three-block title/artist/album
layout -- there's no art or metadata to lay out for a status message.

## .tmp_audio cleanup

`main.py`'s `process_once()` deletes each recording right after use
(`try`/`finally`, see the temp-file-leak fix history), so `.tmp_audio/`
normally never accumulates anything -- but a hard crash or `SIGKILL`
between `record_clip()` writing the file and that `finally` block running
would leave one behind, and nothing used to sweep those up. `main_loop()`
now calls `audio_capture.cleanup_stale_clips()` on the same hourly
cadence as the DVinyl cache refresh, deleting any `.wav` in
`TEMP_AUDIO_DIR` older than `TMP_AUDIO_MAX_AGE_SECONDS` (default 24 hours
-- deliberately generous, since a normal recording is used and deleted
within seconds, so anything that old was never going to be used anyway).
The sweep itself is checked hourly; the age threshold just controls how
old a file must be before that hourly check removes it.
Pure function (age/directory/`now` are all injectable), no `MOCK_MODE`
branch needed since `MOCK_MODE` never writes to `TEMP_AUDIO_DIR` in the
first place.

## Audio gain

Some USB audio interfaces used for the line-out tap have no hardware
capture-gain control at all (confirmed on a Behringer UCA202 via
`alsamixer`: "This sound device does not have any capture controls."). A
clean but quiet signal (low RMS, e.g. ~0.05) is harder for AudD to
fingerprint reliably even though it isn't clipping or silent — likely
because it only uses a small slice of the 16-bit range, so quantization
noise is proportionally more significant.

Fixed via `config.CAPTURE_GAIN` (default `1.0`, a no-op): `audio_capture.
_apply_gain()` multiplies every captured sample by this fixed linear
factor before the WAV is written. It's a **fixed** multiplier, not
per-clip auto-normalization, specifically because normalizing every clip
to a target RMS would also amplify pure background noise/hum during
silent gaps up to "loud," breaking `SILENCE_THRESHOLD`-based silence
detection. A fixed gain scales silence and signal by the same factor, so
their ratio — and thus the existing threshold — stays meaningful.
`_apply_gain` and its helper `_soft_limit` are pure functions (no
MOCK_MODE branch) for the same testability reasons as `_compute_rms_level`.

**Soft-knee limiting, not a hard clip.** A single fixed `CAPTURE_GAIN` has
to work across records mastered at very different loudness levels — a
value tuned against one (quieter) reference track can push a
hotter-mastered record's peaks well past full scale. The original
implementation used `np.clip()` to the exact int16 ceiling, which produces
flat-topped, sharp-cornered waveforms at every one of those peaks —
broadband harmonic distortion. This was root-caused as a real recognition
failure: a healthy-RMS (0.32), correctly-pitched recording of "Complicated"
by Avril Lavigne consistently failed AudD recognition, and direct WAV
analysis of the failing clip found 0.385% of samples sitting at the
*exact* digital ceiling (32767/-32768) — the signature of hard clipping,
not natural analog saturation (which a much more heavily-clipped clip
survived fine earlier in the project, before the gain fix existed at all).

`_soft_limit()` replaces the hard clip: everything below `KNEE_RATIO`
(80%) of full scale passes through completely linearly — so normal-level
content, and the silence/signal ratio the threshold depends on, are
unaffected — and only the portion above that knee is smoothly saturated
via `tanh`, asymptoting toward the ceiling instead of slamming into it.
Two different peaks that would both hard-clip to the identical ceiling
value now map to two different (still near-ceiling) output values, which
is what avoids the flat plateau. Re-running the actual failing clip's
samples through `_soft_limit()` eliminates exact-ceiling hits entirely
(4078 → 0).

This is a hedge against mastering-loudness variance, not a substitute for
reasonable tuning — if a lot of records are pushing well past the knee,
`CAPTURE_GAIN` is probably still set higher than it needs to be; see
`.env.example` for how to check.

## DVinyl integration specifics

DVinyl doesn't expose a documented public read API, so `collection_match.py`
connects directly to its MongoDB database with a read-only user.

Schema confirmed against a real instance (via `db.albums.findOne()`):
collection name is `albums` (not `items`), there's no `collectionType`
field — entry type is `kind` (e.g. `"Music"`) — and the format field is
`media_type` (e.g. `"cassette"`, `"Vinyl"`), not `format`. These are now
the defaults in config.py / .env.example. Field names are still
configurable (`FIELD_ARTIST`, `FIELD_TITLE`, `FIELD_FORMAT`,
`FIELD_TRACKLIST`, `MONGO_COLLECTION_NAME`, `MONGO_FILTER_FIELD`,
`MONGO_FILTER_VALUE`) since other DVinyl instances may still differ —
don't hardcode schema assumptions elsewhere in the code; go through the
configured field names.

## Testing conventions

- `tests/test_audio_capture.py` — pure RMS-level computation (no I/O beyond reading a local WAV fixture, no MOCK_MODE dependency)
- `tests/test_collection_match.py` — pure-Python matching logic (no I/O)
- `tests/test_main_mock_pipeline.py` — full pipeline in MOCK_MODE, no real hardware/network
- When adding features, prefer keeping new logic in pure functions that can
  be unit tested the same way, rather than deep inside hardware-touching
  code paths.

## Home Assistant integration

`home_assistant.py` reports play/pause state to a Home Assistant instance via a directly-set `binary_sensor.groove_tracker_playing` entity (not backed by a real integration — this is the standard lightweight pattern for external devices, see the module's docstring). The actual light control lives in a Home Assistant automation (`automation.groove_tracker_now_playing_light`, created via the HA MCP tools, not in this repo) watching that entity and controlling `light.now_playing_light` with a 30s debounce on the off-transition. If asked to modify the light-control behavior, that means editing the HA automation, not this codebase — this repo only owns reporting the playing state.

## Known open items

- `AUDD_API_TOKEN` and `MONGO_URI` in the user's real `.env` are
  placeholders until they sign up / set up the read-only Mongo user (see
  docs/SETUP.md steps 6–7).
- DVinyl schema field names haven't been verified against the user's real
  instance yet — the defaults in `.env.example` are best guesses.
