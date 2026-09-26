# Groove Tracker — Complete Setup Guide

Everything needed to go from a blank SD card to a running device: wiring,
OS setup, the one-command installer, configuration, testing, and a
troubleshooting appendix covering every real issue hit while building
this (dependency gaps, a mic-level audio adapter mangling recognition, a
quiet line-level adapter with no gain control, DVinyl's actual schema,
and more).

## What you need

- Raspberry Pi Zero WH (or similar — **ARMv6, 32-bit only** on the Zero
  WH/Zero W; this guide assumes that constraint throughout)
- Waveshare 4.2" e-Paper Module (this guide assumes the V2 hardware
  revision — `epd4in2_V2`)
- A USB audio interface with a genuine **line-level** input — a Behringer
  UCA202 or similar. Avoid cheap "USB sound card" dongles built for
  headset mics; see the Wiring section and the troubleshooting appendix
  for why this matters more than it sounds like it should.
- 2x RCA Y-splitters (to tap the turntable/receiver's line-out in parallel
  with your existing powered speakers) + an RCA-to-3.5mm (or RCA-to-RCA,
  depending on your interface) cable
- A microSD card, Raspberry Pi Imager, and a way to SSH into the Pi
  headless (no monitor/keyboard needed)
- An [AudD](https://audd.io) API account (free tier is enough for
  personal use)
- Optional: a self-hosted [DVinyl](https://github.com/Kyonew/DVinyl)
  instance with MongoDB, if you want owned-release matching
- Optional: a Home Assistant instance, if you want a light to react to
  playback

## Wiring

### E-paper module (Waveshare 4.2", 8-pin cable to GPIO)

Board pin labels are silkscreened directly on the driver PCB next to the
8-pin socket — check those on your specific unit rather than trusting wire
color alone (VCC and RST in particular can look similar).

| Board label | Pi physical pin | Pi GPIO |
|---|---|---|
| VCC | 1 | 3.3V |
| GND | 6 (any GND pin works) | GND |
| DIN | 19 | GPIO10 (MOSI) |
| CLK | 23 | GPIO11 (SCLK) |
| CS | 24 | GPIO8 (CE0) |
| DC | 22 | GPIO25 |
| RST | 11 | GPIO17 |
| BUSY | 18 | GPIO24 |

Pin 1 on the Pi's header: flip the board over — pin 1 has a square solder
pad (every other pin is round), and it's the pin closest to the microSD
card slot corner.

### Audio tap

Turntable/receiver line-out → RCA Y-splitter (inline, one per channel) →
one leg continues to your powered speakers as before → the other leg runs
into your USB audio interface → that plugs into the Pi's micro-USB port
via an OTG cable (use the Pi Zero's **data** micro-USB port, not the power
one — they're unlabeled and easy to mix up).

**If your turntable/receiver has a LINE/PHONO output switch, set it to
LINE.** PHONO output is the raw, un-equalized cartridge signal (weak,
~5mV, with the RIAA curve not yet corrected — bass rolled off, treble
boosted) meant to feed a dedicated phono preamp. Neither your powered
speakers nor a plain line-level USB interface expect that; LINE gives you
a full-level, already-corrected signal both can use directly.

**Use a genuine line-level USB audio interface, not a cheap mic-level USB
dongle.** A mic-level input can apply voice-oriented processing (auto
gain, noise gating, sometimes bandwidth limiting) to the signal — this can
degrade fingerprint-relevant detail badly enough to break recognition
*even when the recorded level looks completely normal* (this cost a lot
of debugging time — see the troubleshooting appendix). A Behringer UCA202
or similar dedicated line-level interface avoids this entirely.

**A line-level interface may have no adjustable capture gain at all** —
some (the UCA202 included) are fixed-level by design; `alsamixer` will
show "This sound device does not have any capture controls." for these.
That's normal, not a wiring problem. If your recordings come back clean
but consistently quiet, that's what `CAPTURE_GAIN` in `.env` is for (see
the Testing section) — a software boost applied after capture, since
there's no hardware knob to turn.

## Flash the OS

Use Raspberry Pi Imager. The Zero WH only supports **32-bit** Raspberry Pi
OS (single-core ARMv6 chip) — Imager will correctly hide 64-bit options,
that's expected. Choose Raspberry Pi OS Lite (32-bit). In the gear icon /
advanced settings, set WiFi credentials, hostname, and **enable SSH**
before writing the card, so it boots headless.

First boot typically takes 3–5 minutes on this hardware (filesystem
resize + SSH host key generation + WiFi association).

If SSH gives "connection refused" after the Pi responds to ping: check
that the SSH-enable file actually got written to the boot partition (the
gear icon → Enable SSH step in Imager is easy to miss), or re-flash.

## First boot

```bash
ssh <your-username>@<hostname>.local
```

(`install.sh`, in the next step, enables SPI for you automatically — no
need to do it by hand via `raspi-config` first.)

## Get the code onto the Pi

If you've pushed this repo to your own GitHub (recommended — that's what
makes the one-command bootstrap below work):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/groove-tracker/main/bootstrap.sh)
```

That one command clones the repo to `~/groove-tracker` and immediately
runs `install.sh` (see below) — the full "fresh SD card to installed" path
in a single line. (Edit the `YOUR_GITHUB_USERNAME` placeholder in
`bootstrap.sh` once you've pushed the repo, and in the command above.)

Otherwise, clone or copy it manually:

```bash
git clone <your-repo-url> ~/groove-tracker
# or, from your computer:  scp -r ./groove-tracker <user>@<hostname>.local:~/
cd ~/groove-tracker
bash install.sh
```

## What `install.sh` automates

Running `bash install.sh` from the project root (which `bootstrap.sh` does
for you) handles, in order:

1. **System packages** — everything discovered to be necessary the hard
   way: `libopenjp2-7`, `libopenblas-dev` (the numpy BLAS dependency;
   Debian trixie removed the older `libatlas-base-dev`), `portaudio19-dev`,
   `libsndfile1` (needed by the `soundfile` package), `libfreetype6`
   (needed by Pillow's text rendering — without it, the display silently
   fails to render while everything else keeps working, which looks like
   a hang).
2. **Enables SPI** via `raspi-config nonint do_spi 0`.
3. **Vendors the Waveshare e-Paper driver** into the project root (not
   inside `groove_tracker/` — `display.py` imports it as a bare top-level
   module, which only resolves from the root) using a sparse/partial git
   clone. The full Waveshare repo has 33,000+ files for every product they
   sell; a normal full clone can exhaust inodes or fill a RAM-backed
   `/tmp` on a small SD card / low-RAM board like the Zero.
4. **Python virtual environment** + `pip install -r requirements.txt`.
5. **`.env`** — copies `.env.example` to `.env` if it doesn't exist yet
   (never overwrites an existing one).
6. **Samba file share** — installs `samba` and adds a `[groove-tracker]`
   share pointing at the project directory, so you can drag files over
   from your computer instead of `scp`-ing everything. Doesn't (can't)
   set a Samba password for you — see the checklist it prints at the end.
7. **systemd service** — installs `groove-tracker.service` (substituting
   your actual username and project path into the template in
   `systemd/`) and enables it to start on boot, but does **not** start it
   yet, since `.env` still needs real values first.

It's safe to re-run any time — each step skips itself if already done, and
it never touches an existing `.env`.

## Manual steps (the script prints this checklist too)

1. Wire the display and audio tap, if you haven't already (above).
2. Get an AudD API token at <https://audd.io> → `AUDD_API_TOKEN` in `.env`.
3. Create a read-only MongoDB user for DVinyl (below) → `MONGO_URI` in
   `.env`.
4. Optional: create a Home Assistant Long-Lived Access Token (below) →
   `HA_URL`/`HA_TOKEN` in `.env`.
5. Set a Samba password: `sudo smbpasswd -a <your-username>` (separate
   from your Pi login password — this is what you'll actually type when
   connecting from your computer's file browser).
6. Edit `.env` — `nano ~/groove-tracker/.env` — see the full reference
   below.

## `.env` reference

| Variable | Default | Notes |
|---|---|---|
| `MOCK_MODE` | `false` | `true` swaps in fake hardware/network for dev off the real device — leave `false` here. |
| `AUDD_API_TOKEN` | *(none)* | From <https://audd.io>. |
| `AUDIO_DEVICE` | *(blank = system default)* | Only set this if the wrong input device gets picked automatically. |
| `SAMPLE_RATE` | `44100` | |
| `CHANNELS` | `2` | Some cheap adapters only support mono — set to `1` if you get an `Invalid number of channels` error. |
| `CLIP_SECONDS` | `12` | Length of each recording; ~12s is close to AudD's useful max. |
| `CAPTURE_GAIN` | `1.0` | Fixed digital gain multiplier, applied before saving/recognizing. Leave at `1.0` unless your interface has no hardware gain control and recordings come back clean-but-quiet (see Testing below and the troubleshooting appendix). |
| `MONGO_URI` | *(none)* | `mongodb://user:pass@host:27017/dvinyl?authSource=dvinyl` — use the read-only user, not admin credentials. |
| `MONGO_DB_NAME` | `dvinyl` | |
| `MONGO_COLLECTION_NAME` | `albums` | Confirmed against a real DVinyl instance — not `items`. |
| `MONGO_FILTER_FIELD` / `MONGO_FILTER_VALUE` | `kind` / `Music` | Set `MONGO_FILTER_FIELD=` (empty) to skip filtering and query every document, if your instance differs. |
| `FIELD_ARTIST` / `FIELD_TITLE` / `FIELD_FORMAT` / `FIELD_TRACKLIST` | `artist` / `title` / `media_type` / `tracklist` | Verify against your own instance — see below. |
| `DISPLAY_MODEL` | `epd4in2_V2` | Waveshare driver submodule name; confirmed correct for the 4.2" V2 panel. |
| `POLL_INTERVAL_SECONDS` | `25` | How often the main loop records and checks. |
| `SILENCE_THRESHOLD` | `0.02` | RMS level above which a clip counts as "playing." |
| `SILENCE_CLEAR_SECONDS` | `30` | How long the turntable must be *continuously* silent before the display clears. Debounced so a normal pause between tracks doesn't blank the screen. |
| `UNRECOGNIZED_CLEAR_SECONDS` | `60` | Same idea, for "playing but AudD can't identify it" — clears a now-stale previous song instead of leaving it up forever. |
| `HA_URL` / `HA_TOKEN` | *(blank = disabled)* | Home Assistant base URL + Long-Lived Access Token. |
| `HA_PLAYING_ENTITY_ID` | `binary_sensor.groove_tracker_playing` | |
| `WEBUI_PORT` | `8420` | Port the web dashboard listens on. |
| `WEBUI_PASSWORD` | *(blank = no login)* | Password for the dashboard. Only leave blank on a fully trusted LAN. |
| `WEBUI_SECRET_KEY` | *(none)* | Signs the login session cookie. `install.sh` generates this for you — don't set it by hand, and don't edit it later (that logs everyone out). |

## Create a read-only MongoDB user for DVinyl

On your DVinyl host, open a shell into the MongoDB container and run:

```javascript
use dvinyl
db.createUser({
  user: "vinyl_display_reader",
  pwd: "choose-a-strong-password",
  roles: [{ role: "read", db: "dvinyl" }]
})
```

Make sure the MongoDB container's port (usually `27017`) is actually
reachable from the Pi's subnet, not just from inside the host (e.g. an
Unraid Docker container needs that port published in its network settings
— check with `docker ps` for a host-side mapping like
`0.0.0.0:27017->27017/tcp`), then set `MONGO_URI` in `.env`.

**Verify your schema** — field names can vary by version or how entries
were imported. Confirmed against one real instance: collection `albums`
(not `items`), entry-type field `kind` (e.g. `"Music"`, not
`collectionType`), format field `media_type` (e.g. `"Vinyl"`,
`"cassette"`). Check yours:

```javascript
db.albums.findOne()
```

and adjust the `MONGO_*`/`FIELD_*` variables in `.env` to match if it
differs.

## Home Assistant integration (optional)

1. In Home Assistant: Profile page → scroll to "Long-lived access tokens"
   → Create Token. Copy it.
2. In `.env`, set `HA_URL` (e.g. `http://192.168.1.50:8123`) and
   `HA_TOKEN`.
3. Test it: `python3 -c "from groove_tracker.home_assistant import set_playing_state; set_playing_state(True)"`
   — `binary_sensor.groove_tracker_playing` should appear as "on" in
   Home Assistant under Developer Tools → States.
4. The automation that watches this entity and controls a light
   (`automation.groove_tracker_now_playing_light`) lives in Home
   Assistant itself, not in this repo. It triggers on the binary
   sensor's state changing, with a 30s debounce on the "off" transition
   to avoid flicker between tracks, and calls `light.turn_on`/
   `light.turn_off` on your target light.

Leave `HA_URL`/`HA_TOKEN` blank to disable this feature entirely — the
rest of the project works fine without it.

## Samba (file sharing)

`install.sh` already installed Samba and added the `[groove-tracker]`
share. After running `sudo smbpasswd -a <your-username>` (step 5 above),
connect from your computer:

- **Windows**: File Explorer → address bar → `\\<hostname>\groove-tracker`
- **Mac**: Finder → Cmd+K → `smb://<hostname>.local/groove-tracker`

Use the Samba password you just set, not your Pi login password.

## Testing before running the full loop

With `MOCK_MODE=true` in `.env` (or as an env var), the whole pipeline
runs end-to-end without any hardware or network dependencies — see the
"Mock mode" section in the main README. Once that passes, test against
real hardware, one piece at a time, keeping everything in the **same**
terminal session (shell variables like `$CLIP` don't persist across
separate SSH connections):

```bash
source venv/bin/activate

# 1. Record a clip (12s — play a record while this runs)
CLIP=$(python3 -c "from groove_tracker.audio_capture import record_clip; print(record_clip())")
echo $CLIP

# 2. Check its level
python3 -c "from groove_tracker.audio_capture import get_audio_level; print(get_audio_level('$CLIP'))"
```

**If the level is well under ~0.15-0.2 even during a loud passage**, and
`alsamixer` shows no capture controls for your device, raise
`CAPTURE_GAIN` in `.env` (try `4`-`6` as a starting point), re-run steps 1
and 2, and confirm the new level lands around `0.2`-`0.3` without
clipping (a level pinned near `1.0` means the gain is too high). This is
expected for fixed line-level interfaces like the UCA202 — no hardware
gain to adjust, so this software boost is the intended fix.

```bash
# 3. Test AudD recognition on that same clip
python3 -c "from groove_tracker.identify import identify_song; print(identify_song('$CLIP'))"

# 4. Test DVinyl matching (independent of audio -- use something you own)
python3 -c "from groove_tracker.collection_match import find_owned_release; print(find_owned_release('Queen', 'Bohemian Rhapsody'))"

# 5. Test the display directly, including album art
python3 -c "from groove_tracker import display; display.render_now_playing('Queen', 'Bohemian Rhapsody', 'Greatest Hits', owned=True, art_url='https://any-image-url.example/art.jpg')"

# 6. Test clearing the display
python3 -c "from groove_tracker import display; display.clear_display()"

# 7. Run one full pass of the actual loop
python3 -c "from groove_tracker.main import process_once; print(process_once())"
```

## Enable and start the service

`install.sh` already installed and enabled `groove-tracker.service`.
Once `.env` is filled in and the hardware is wired:

```bash
sudo systemctl start groove-tracker
sudo journalctl -u groove-tracker -f   # watch it live
```

You should see a cycle like:

```
Recording clip...
Signal level check: playing
Identifying song via AudD...
Recognized: Artist — Title
Checking DVinyl collection...
Owned release found: Album — rendering to display...
Display updated.
```

and, after the turntable stops for `SILENCE_CLEAR_SECONDS`:

```
Silent for 30s+, clearing display.
```

## Web UI

A local dashboard for managing the service from a browser instead of SSH
— check what's playing, start/stop/restart the service, tail its logs,
and edit `.env`, all from your phone or laptop on the same LAN.

`install.sh` sets this up as step 9/9 (skip it there and re-run
`install.sh` any time to add it later). It installs:

- **`groove-tracker-web.service`** — a second systemd service, running
  `python3 -m groove_tracker.webui` as the same unprivileged user as
  `groove-tracker.service` itself (never as root).
- **`/etc/sudoers.d/groove-tracker-web`** — grants that user exactly
  `sudo systemctl start/stop/restart groove-tracker.service` and nothing
  broader, so the dashboard's Start/Stop/Restart buttons work without the
  web process needing root. Written via a validated (`visudo -c`)
  temp file, never edited in place.
- Adds the user to the `systemd-journal` group, so the Logs page can read
  `journalctl -u groove-tracker` without sudo.

Once installed:

```
http://<hostname>.local:8420/
```

**Pages:**

- **Dashboard** — turntable playing/silent, last recognized song (with
  album/owned-in-your-collection status), a live copy of whatever's
  currently on the e-paper panel, and Start/Stop/Restart buttons.
- **Logs** — the same thing as `journalctl -u groove-tracker -f`, in a
  browser, auto-refreshing every few seconds.
- **Config** — every `.env` variable, grouped and labeled, editable as a
  form instead of `nano .env`. Secrets (AudD token, Mongo URI, HA token,
  the dashboard's own password) are never echoed back into the page —
  leave a secret field blank to keep its current value, or type a new one
  to replace it. Changes only take effect once `groove-tracker.service`
  restarts (there's a checkbox to do that automatically on save).

**Security model:** this is built for a trusted home LAN, not the public
internet — there's a single shared password (no per-user accounts), and
no HTTPS (add a reverse proxy in front of it, e.g. Caddy or nginx, if you
want TLS). Don't port-forward `8420` to the internet. Leaving
`WEBUI_PASSWORD` blank disables login entirely; the dashboard will nag you
about this on every page load until you set one.

### Updating

The Dashboard's **Pull latest & restart** button (`groove_tracker/webui/updater.py`)
is the no-SSH equivalent of:

```bash
cd ~/groove-tracker
git pull --ff-only
source venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart groove-tracker
sudo systemctl restart groove-tracker-web
```

It only ever pulls (`--ff-only` — fails loudly rather than merging or
resetting if the Pi's local branch has diverged, e.g. from a file edited
directly over Samba/SSH) and only reinstalls dependencies/restarts
anything if the pull actually brought in new commits. Since restarting
`groove-tracker-web.service` kills the very process handling that button's
request, it's done via a 2-second-delayed detached command
(`restart_self_delayed()`), not synchronously — the response ("reload in
a few seconds") reaches your browser first, then the dashboard restarts.

Needs the extra `systemctl restart groove-tracker-web.service` grant in
`/etc/sudoers.d/groove-tracker-web` — already included if you installed
the web UI via `install.sh`'s step 9; re-run `install.sh` if you set the
web UI up before this button existed, to pick up the new sudoers rule.

---

## Troubleshooting appendix

Real issues hit while building this, in case you hit them again on a
fresh install:

| Symptom | Cause | Fix |
|---|---|---|
| `Package libatlas-base-dev is not available` | Debian trixie removed it | Use `libopenblas-dev` instead — `install.sh` already does this. |
| `git clone` of the Waveshare repo fails with mass "unable to write file" errors | Full clone (33,000+ files) exhausts inodes or fills a RAM-backed `/tmp` | `install.sh` uses a sparse/partial clone into the project directory instead — no action needed. |
| `ModuleNotFoundError: No module named 'waveshare_epd'` | The driver folder ended up nested inside `groove_tracker/` instead of the project root | Move it to the project root (sibling of `groove_tracker/`); `install.sh` places it correctly automatically. |
| `ModuleNotFoundError: No module named 'gpiozero'` | Newer Waveshare driver versions need `gpiozero`/`lgpio`, not just `RPi.GPIO` | Already in `requirements.txt`. |
| `cannot load library 'libsndfile.so'` | The `soundfile` package needs the system `libsndfile1` library | `install.sh` installs it. |
| `libfreetype.so.6: cannot open shared object file` | Pillow's text rendering needs `libfreetype6` | `install.sh` installs it. Symptom otherwise: the service runs and recognizes songs fine, but the display never actually updates (the render call throws, main loop's broad exception handler swallows and logs it). |
| Sound recognized inconsistently, or not at all, even on mainstream tracks, despite a clean-looking (non-silent, non-clipped) recording | A mic-level USB audio adapter applying voice-oriented DSP (auto gain, noise gating) to the signal | Use a genuine line-level interface (e.g. Behringer UCA202) instead. |
| Clean recording, but consistently quiet (e.g. RMS ~0.05) with no hardware gain control (`alsamixer` shows "This sound device does not have any capture controls") | Some line-level interfaces (UCA202 included) are fixed-level by design | Raise `CAPTURE_GAIN` in `.env` (software boost) — see Testing above. |
| Turntable output sounds thin/hollow and too quiet, or too loud/distorted, through the tap specifically (speakers still sound fine) | Turntable/receiver's LINE/PHONO output switch set to PHONO | Set it to LINE. |
| `pymongo.errors.ServerSelectionTimeoutError: Connection refused` | MongoDB's port isn't published to the LAN, or the read-only user doesn't exist yet | Publish the port in your Docker host's network settings; create the user (see above). |
| MongoDB `AuthenticationFailed` | Wrong password, or user created in the wrong database's user table | Recreate the user with `use dvinyl` first, so it's scoped correctly; double check `authSource=dvinyl` in `MONGO_URI`. |
| Samba: "No path in service groove-tracker" in logs, or Windows says "you need permission" | Malformed share block in `smb.conf` (a stray typo is enough) | `install.sh`'s heredoc-based share block avoids hand-typing this; if it still happens, run `testparm` to validate `smb.conf` before restarting `smbd`. |
| `/tmp` fills up after the service runs for hours (`Error opening '/tmp/tmpXXXXXXXX.wav'`) | An early version leaked a temp WAV file every poll cycle | Already fixed in this codebase — clips are written to a project-local, cleaned-up `.tmp_audio/` directory and deleted after each use. No action needed on a fresh install. |
| Display stays blank with no errors in the logs | Was an observability gap in an earlier version — a silent failure (e.g. a miswired BUSY pin) looked identical to silent success | Already fixed — `main.py` logs every pipeline stage; `journalctl -u groove-tracker -f` will show exactly where it stops now. |
| Display keeps showing an old song after the turntable stops, or after a different unrecognized track starts | Nothing used to ever clear the display | Already fixed via the debounced `SILENCE_CLEAR_SECONDS`/`UNRECOGNIZED_CLEAR_SECONDS` logic. If it's happening within those windows, that's expected — it hasn't debounced yet. |
| Web UI's Start/Stop/Restart buttons fail with a sudo-related error | The `/etc/sudoers.d/groove-tracker-web` drop-in is missing, or failed `visudo -c` validation during install | Re-run `install.sh` (step 9/9), or check its output for a validation warning. |
| Web UI's Logs page says it can't read the journal | The web UI's user isn't in the `systemd-journal` group yet (needs a fresh login/reboot to take effect after being added) | `sudo usermod -aG systemd-journal <user>`, then log out/in or reboot; `install.sh` does this for you already. |
| Web UI dashboard has no login | `WEBUI_PASSWORD` is blank in `.env` | Set it — via the Config page itself (works even with no login, so do this immediately if the dashboard is reachable off your LAN), or `nano .env`, then restart `groove-tracker-web.service`. |
