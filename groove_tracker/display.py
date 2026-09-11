"""Renders now-playing info to the Waveshare e-paper display.

In MOCK_MODE, writes a PNG to mock_output/ instead of talking to real
hardware, so this can run and be tested on any machine.
"""
import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

from . import config

FONT_PATH_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Fallback used when the DejaVu fonts above aren't installed (e.g. in a
# dev/CI environment). Real Raspberry Pi OS installs have DejaVu by default.
MOCK_DISPLAY_SIZE = (400, 300)  # matches the Waveshare 4.2" panel resolution


def _load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _compose_image(artist, title, album, owned, width, height):
    image = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(image)

    font_title = _load_font(FONT_PATH_BOLD, 22)
    font_artist = _load_font(FONT_PATH_REGULAR, 18)
    font_album = _load_font(FONT_PATH_REGULAR, 16)

    y = 10
    for line in textwrap.wrap(title, width=22):
        draw.text((10, y), line, font=font_title, fill=0)
        y += 26

    y += 6
    for line in textwrap.wrap(artist, width=26):
        draw.text((10, y), line, font=font_artist, fill=0)
        y += 22

    y += 6
    album_label = album if not owned else f"{album}  (in your collection)"
    for line in textwrap.wrap(album_label, width=30):
        draw.text((10, y), line, font=font_album, fill=0)
        y += 20

    return image


def render_now_playing(artist, title, album, owned=False):
    if config.MOCK_MODE:
        os.makedirs(config.MOCK_DISPLAY_OUTPUT_DIR, exist_ok=True)
        image = _compose_image(artist, title, album, owned, *MOCK_DISPLAY_SIZE)
        out_path = os.path.join(config.MOCK_DISPLAY_OUTPUT_DIR, "now_playing.png")
        image.save(out_path)
        print(f"[mock display] {artist} — {title} ({album}) -> {out_path}")
        return

    import importlib

    epd_module = importlib.import_module(f"waveshare_epd.{config.DISPLAY_MODEL}")
    epd = epd_module.EPD()
    epd.init()
    epd.Clear()

    image = _compose_image(artist, title, album, owned, epd.width, epd.height)
    epd.display(epd.getbuffer(image))
    epd.sleep()
