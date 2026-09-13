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
sudo apt update
sudo apt install -y python3-pip python3-venv git \
    libopenjp2-7 libopenblas-dev portaudio19-dev
```

Note: `libopenblas-dev` replaces the older `libatlas-base-dev`, which
Debian trixie (the current Raspberry Pi OS base) has removed. It provides
the same BLAS library numpy needs.

## 4. Get the Waveshare display library

The `waveshare_epd` library is not on PyPI — clone it directly and copy it
to the project root (sibling to the `groove_tracker/` package folder, NOT
inside it — `display.py` imports it as a bare top-level module, so it
needs to be directly on the Python path, which only the project root is
when running `python3 -m groove_tracker` from there):

```bash
cd ~
git clone https://github.com/waveshare/e-Paper.git
cp -r e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd ~/groove-tracker/
```

## 5. Set up the project

Clone/copy this repo to `~/groove-tracker` on the Pi, then:

```bash
cd ~/groove-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in your real `AUDD_API_TOKEN` and `MONGO_URI` (see
below). Leave `MOCK_MODE=false` on the real device.

## 6. Get an AudD API token

Sign up at https://audd.io — the free tier is enough for personal use.
Paste the token into `.env` as `AUDD_API_TOKEN`.

## 7. Create a read-only MongoDB user for DVinyl

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
Pi's subnet, and update `MONGO_URI` in `.env` with your Unraid IP and the
new credentials.

## 8. Verify your DVinyl schema

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

## 9. Test before running the full loop

With `MOCK_MODE=true` in `.env`, you can exercise the whole pipeline
without any hardware or network dependencies — see the "Mock mode" section
in the main README. Once that passes, switch to real hardware:

```bash
# Test audio capture (records 12s — play it back to confirm you hear the record)
python3 -c "from groove_tracker.audio_capture import record_clip; print(record_clip())"

# Test AudD recognition on that file
python3 -c "from groove_tracker.identify import identify_song; print(identify_song('/path/to/clip.wav'))"

# Test DVinyl matching
python3 -c "from groove_tracker.collection_match import find_owned_release; print(find_owned_release('Queen', 'Bohemian Rhapsody'))"

# Test the display directly
python3 -c "from groove_tracker import display; display.render_now_playing('Test Artist', 'Test Title', 'Test Album')"
```

## 10. Optional: Home Assistant "Now Playing" light

If you want a nearby light to turn on/off with the music:

1. In Home Assistant, go to your Profile page and scroll to "Long-lived access tokens" → Create Token. Copy it.
2. In `.env`, set `HA_URL` (e.g. `http://192.168.1.50:8123`) and `HA_TOKEN` to that token.
3. Test it reports correctly: `python3 -c "from groove_tracker.home_assistant import set_playing_state; set_playing_state(True)"` — you should see `binary_sensor.groove_tracker_playing` appear as "on" in Home Assistant (Developer Tools → States).
4. The automation that watches this entity and controls the light was set up separately in Home Assistant (`automation.groove_tracker_now_playing_light`) — it's not part of this repo. If you need to recreate it, it triggers on that binary_sensor's state changing to "on"/"off" (with a 30s debounce on "off" to avoid flicker between tracks) and calls `light.turn_on`/`light.turn_off` on your target light/switch.

This step is entirely optional — leave `HA_URL`/`HA_TOKEN` blank in `.env` and the rest of the project works normally without it.

## 11. Run it for real

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
