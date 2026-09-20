"""Renders now-playing info -- with album art, when available -- to the
Waveshare e-paper display.

In MOCK_MODE, writes a PNG to mock_output/ instead of talking to real
hardware, so this can run and be tested on any machine.

Text is sized automatically to fill the available space (see _fit_text):
rather than fixed font sizes tuned for one particular title length, each
of the title/artist/album blocks picks the largest font that still wraps
to fit its box, so a short title like "Baba O'Riley" fills the screen and
a long one still fits without overflowing.
"""
import os

from PIL import Image, ImageDraw, ImageFont

from . import album_art, config

FONT_PATH_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

MOCK_DISPLAY_SIZE = (400, 300)  # matches the Waveshare 4.2" panel resolution
ART_SIZE = 150  # square album art footprint, in pixels
MARGIN = 12


def _load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _split_long_word(draw, word, font, max_width):
    """Hard-breaks a single word wider than max_width into chunks that each
    fit, character by character. Fallback for a word too long to ever fit
    the column at a given font size (e.g. a short album-art column at a
    large font) -- rare on its own, but _fit_text relies on it as the
    safety valve while it searches for a font size that avoids needing it.
    """
    chunks = []
    current = ""
    for ch in word:
        candidate = current + ch
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            chunks.append(current)
            current = ch
    if current:
        chunks.append(current)
    return chunks


def _wrap_by_pixel(draw, text, font, max_width):
    """Greedy word-wrap using actual rendered pixel width (via
    draw.textlength), so lines never overflow their box regardless of
    character count -- unlike wrapping by a fixed character count, this
    stays correct as the font size changes. Also guarantees no returned
    line exceeds max_width, even for a single word that's too wide on its
    own (see _split_long_word) -- without this, a font size could look
    like it "fits" (few lines, so the height check in _fit_text passes)
    while actually overflowing the box horizontally.
    """
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = ""
    for word in words:
        if draw.textlength(word, font=font) > max_width:
            if current:
                lines.append(current)
                current = ""
            chunks = _split_long_word(draw, word, font, max_width)
            lines.extend(chunks[:-1])
            current = chunks[-1] if chunks else ""
            continue

        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)
    return lines or [""]


def _fit_text(draw, text, font_path, max_width, max_height, max_size, min_size=12, line_spacing=1.15):
    """Finds the largest font size (stepping down from max_size to
    min_size) whose wrapped lines all fit inside max_width x max_height.

    Falls back to min_size if even that overflows the height -- rare, only
    for unusually long text -- so the caller always gets something to draw
    rather than an exception.

    Pure function: takes any ImageDraw and plain text, no MOCK_MODE or
    hardware dependency, so it's safe to unit test against an in-memory
    image.
    """
    font = lines = line_height = None
    for size in range(max_size, min_size - 1, -2):
        font = _load_font(font_path, size)
        lines = _wrap_by_pixel(draw, text, font, max_width)
        line_height = int(size * line_spacing)
        if line_height * len(lines) <= max_height:
            return font, lines, line_height

    # Nothing fit within max_height even at min_size -- return the
    # smallest size anyway; _draw_block clips at the box edge rather than
    # overflowing into the next block.
    return font, lines, line_height


def _draw_block(draw, lines, font, line_height, x, y, max_height):
    """Draws wrapped lines top-down starting at (x, y), stopping before it
    would run past max_height -- defensive clipping for the rare case
    _fit_text couldn't make everything fit even at its smallest size.
    """
    drawn = 0
    for line in lines:
        if drawn + line_height > max_height:
            break
        draw.text((x, y + drawn), line, font=font, fill=0)
        drawn += line_height
    return drawn


def _compose_image(artist, title, album, owned, width, height, art_image=None):
    image = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(image)

    if art_image is not None:
        art_x = MARGIN
        art_y = max(MARGIN, (height - art_image.height) // 2)
        image.paste(art_image.convert("1"), (art_x, art_y))
        text_x = art_x + art_image.width + MARGIN
    else:
        text_x = MARGIN

    text_width = width - text_x - MARGIN
    usable_height = height - 2 * MARGIN

    # Title gets the most room and the largest font; artist and album
    # split the rest. _fit_text shrinks automatically for longer text, so
    # these proportions just set the starting budget, not a hard size.
    title_box_h = int(usable_height * 0.42)
    artist_box_h = int(usable_height * 0.32)
    album_box_h = usable_height - title_box_h - artist_box_h

    y = MARGIN
    font, lines, line_h = _fit_text(draw, title, FONT_PATH_BOLD, text_width, title_box_h, max_size=44, min_size=18)
    _draw_block(draw, lines, font, line_h, text_x, y, title_box_h)
    y += title_box_h

    font, lines, line_h = _fit_text(draw, artist, FONT_PATH_REGULAR, text_width, artist_box_h, max_size=32, min_size=14)
    _draw_block(draw, lines, font, line_h, text_x, y, artist_box_h)
    y += artist_box_h

    album_label = album if not owned else f"{album}  ★ in your collection"
    font, lines, line_h = _fit_text(draw, album_label, FONT_PATH_REGULAR, text_width, album_box_h, max_size=24, min_size=12)
    _draw_block(draw, lines, font, line_h, text_x, y, album_box_h)

    return image


def render_now_playing(artist, title, album, owned=False, art_url=None):
    art_image = album_art.get_album_art(art_url, ART_SIZE)

    if config.MOCK_MODE:
        os.makedirs(config.MOCK_DISPLAY_OUTPUT_DIR, exist_ok=True)
        image = _compose_image(artist, title, album, owned, *MOCK_DISPLAY_SIZE, art_image=art_image)
        out_path = os.path.join(config.MOCK_DISPLAY_OUTPUT_DIR, "now_playing.png")
        image.save(out_path)
        print(f"[mock display] {artist} — {title} ({album}) -> {out_path}", flush=True)
        return

    import importlib

    epd_module = importlib.import_module(f"waveshare_epd.{config.DISPLAY_MODEL}")
    epd = epd_module.EPD()
    epd.init()
    epd.Clear()

    image = _compose_image(artist, title, album, owned, epd.width, epd.height, art_image=art_image)
    epd.display(epd.getbuffer(image))
    epd.sleep()
