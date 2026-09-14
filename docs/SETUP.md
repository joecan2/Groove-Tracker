# Groove Tracker — Hardware Setup Guide

Hardware: Raspberry Pi Zero WH (ARMv6, 32-bit only), Waveshare 4.2" e-Paper
Module, USB audio adapter, RCA Y-splitters tapped off the turntable's
line-out.

## 1. Wiring

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
through the RCA-to-3.5mm cable into the USB audio adapter → USB audio
adapter plugs into the Pi's micro-USB port via the OTG cable.

If your USB audio adapter's line-in is tuned for microphone-level signals
rather than line-level, a real turntable signal can overload/clip it —
if levels come back near the max (close to 1.0) during testing in step 9,
lower the capture gain with `alsamixer` before assuming something's wired
wrong.

## 2. Flash the OS

Use Raspberry Pi Imager. This board only supports **32-bit** Raspberry Pi
OS (single-core ARMv6 chip) — Imager will correctly hide 64-bit options,
that's expected. Choose Raspberry Pi OS Lite (32-bit). In the gear icon /
advanced settings, set WiFi credentials, hostname, and **enable SSH**
before writing the card, so it boots headless.

First boot typically takes 3–5 minutes on this hardware (filesystem
resize + SSH host key generation + WiFi association).

If SSH gives "connection refused" after the Pi responds to ping: check
that the `ssh` enable file actually got written to the boot partition
(gear icon → Enable SSH in Imager is easy to miss), or re-flash.

## 3. First boot

```bash
ssh joe@<hostname>.local
sudo raspi-config
# Interface Options -> SPI -> Enable
```

(The install script in the next step also does this automatically — the
manual command above is here in case you want to confirm it separately.)

## 4. Copy the project to the Pi

From your computer:

```bash
scp -r ./groove-tracker joe@<hostname>.local:~/
```

Or, once Samba is set up (see the main README/your own notes on that), you
can just drag files over directly.

## 5. Run the install script

```bash
cd ~/groove-tracker
bash install.sh
```

This handles: system packages, enabling SPI, cloning the Waveshare e-Paper
driver into the right place (the project root, not inside `groove_tracker/`
— see the comment in `.gitignore` if you're curious why that distinction
matters), creating the virtual environment, and installing Python
dependencies. It's safe to re-run — it skips anything already done and
won't overwrite an existing `.env`.

<details>
<summary>What it does, if you'd rather run each piece by hand</summary>

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git \
    libopenjp2-7 libopenblas-dev portaudio19-dev

sudo raspi-config nonint do_spi 0

cd ~/groove-tracker
git clone --filter=blob:none --sparse --depth 1 https://github.com/waveshare/e-Paper.git .waveshare-sparse-clone
(cd .waveshare-sparse-clone && git sparse-checkout set RaspberryPi_JetsonNano/python/lib/waveshare_epd)
cp -r .waveshare-sparse-clone/RaspberryPi_JetsonNano/python/lib/waveshare_epd .
rm -rf .waveshare-sparse-clone

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Note: `libopenblas-dev` replaces the older `libatlas-base-dev`, which
Debian trixie (the current Raspberry Pi OS base) has removed — it provides
the same BLAS library numpy needs. The `waveshare_epd` folder must land at
the project root (sibling to `groove_tracker/`), not nested inside the
package — `display.py` imports it as a bare top-level module, which only
resolves from the project root. The sparse/partial clone above fetches
only that one folder rather than the full repo — Waveshare's e-Paper repo
has 33,000+ files covering every product they sell, and a full checkout
can exhaust inodes or fill a RAM-backed `/tmp` on a small SD card / low-RAM
board like the Zero. If you hit "unable to write file" errors from a full
`git clone` here, that's what happened — clean up with
`rm -rf /tmp/tmp.* ~/e-Paper` and use the sparse approach above instead.

</details>

After the script finishes, activate the venv for the rest of this guide:

```bash
source venv/bin/activate
```

## 6. Fill in .env

`cp .env.example .env` already happened via the script if `.env` didn't
exist yet. Edit it now:

```bash
nano .env
```

Confirm `DISPLAY_MODEL` matches your panel — `epd4in2_V2` is confirmed
correct for this hardware (check yours by running
`grep "^from waveshare_epd import" ~/e-Paper/.../examples/epd_4in2_V2_test.py`
against whichever demo script you used to test the display, if it
differs). Leave `MOCK_MODE=false` on the real device. The remaining
sections below walk through the values you still need to fill in.

## 7. Get an AudD API token

Sign up at https://audd.io — the free tier is enough for personal use.
Paste the token into `.env` as `AUDD_API_TOKEN`.

## 8. Create a read-only MongoDB user for DVinyl

On your Unraid server, open a shell into the MongoDB container and run:

```javascript
use dvinyl
db.createUser({
  user: "vinyl_display_reader",
  pwd: "choose-a-strong-password",
  roles: [{ role: "read", db: "dvinyl" }]
})
```

Make sure the Mongo container's port (usually 27017) is reachable from the
Pi's subnet — this may mean publishing the port in Unraid's Docker UI if
it isn't already (check with `docker ps`, look for a host-side mapping
like `0.0.0.0:27017->27017/tcp`) — and update `MONGO_URI` in `.env` with
your Unraid IP and the new credentials.

## 9. Verify your DVinyl schema

Confirmed against a real instance: the collection is `albums` (not
`items`), and there's no `collectionType` field — entry type is `kind`
(e.g. `"Music"`), and the format field is `media_type` (e.g. `"cassette"`,
`"Vinyl"`). These are already the defaults in `.env.example`. Still worth
double-checking against your own database, since field names can vary by
version or how entries were imported:

```javascript
db.albums.findOne()
```

If your instance differs, adjust `MONGO_COLLECTION_NAME`,
`MONGO_FILTER_FIELD`/`MONGO_FILTER_VALUE`, and the `FIELD_*` variables in
`.env` to match. Set `MONGO_FILTER_FIELD=` (empty) to skip filtering
entirely and query every document if your instance doesn't use `kind`.

## 10. Test before running the full loop

With `MOCK_MODE=true` in `.env`, you can exercise the whole pipeline
without any hardware or network dependencies — see the "Mock mode" section
in the main README. Once that passes, switch to real hardware, testing one
piece at a time:

```bash
# Test audio capture (records 12s — play a record while this runs)
CLIP=$(python3 -c "from groove_tracker.audio_capture import record_clip; print(record_clip())")
echo $CLIP

# Test silence detection on that same clip
python3 -c "from groove_tracker.audio_capture import get_audio_level, is_signal_present; print('Level:', get_audio_level('$CLIP')); print('Playing:', is_signal_present('$CLIP'))"

# Test AudD recognition on that same clip
python3 -c "from groove_tracker.identify import identify_song; print(identify_song('$CLIP'))"

# Test DVinyl matching (independent of audio — use something you know is in your collection)
python3 -c "from groove_tracker.collection_match import find_owned_release; print(find_owned_release('Queen', 'Bohemian Rhapsody'))"

# Test the display directly
python3 -c "from groove_tracker import display; display.render_now_playing('Test Artist', 'Test Title', 'Test Album')"
```

Keep `$CLIP` and all of the above in the *same* terminal session — shell
variables don't persist across separate SSH connections.

## 11. Optional: Home Assistant "Now Playing" light

If you want a nearby light to turn on/off with the music:

1. In Home Assistant, go to your Profile page and scroll to "Long-lived access tokens" → Create Token. Copy it.
2. In `.env`, set `HA_URL` (e.g. `http://192.168.1.50:8123`) and `HA_TOKEN` to that token.
3. Test it reports correctly: `python3 -c "from groove_tracker.home_assistant import set_playing_state; set_playing_state(True)"` — you should see `binary_sensor.groove_tracker_playing` appear as "on" in Home Assistant (Developer Tools → States).
4. The automation that watches this entity and controls the light was set up separately in Home Assistant (`automation.groove_tracker_now_playing_light`) — it's not part of this repo. If you need to recreate it, it triggers on that binary_sensor's state changing to "on"/"off" (with a 30s debounce on "off" to avoid flicker between tracks) and calls `light.turn_on`/`light.turn_off` on your target light/switch.

This step is entirely optional — leave `HA_URL`/`HA_TOKEN` blank in `.env` and the rest of the project works normally without it.

## 12. Run it for real

```bash
python3 -m groove_tracker
```

Once that works end-to-end, install it as a service so it starts on boot:

```bash
sudo cp systemd/groove-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now groove-tracker.service
sudo journalctl -u groove-tracker -f   # watch the logs
```
