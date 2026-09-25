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


_warned_missing_font_paths = set()


def _load_font(path, size):
    """Loads a scalable TrueType font at the requested size, falling back
    to Pillow's built-in bitmap font if the file isn't present.

    That fallback is a trap worth calling out loudly: ImageFont.load_default()
    ignores the `size` argument entirely and always returns the same tiny
    fixed-size font, and it also has a very limited glyph set (no "★", for
    instance -- it renders as a blank box instead). Silently falling back
    here previously meant every single render used the same tiny font no
    matter what max_size _fit_text picked, with no error anywhere -- it
    just looked like "the auto-sizing isn't working" rather than "the
    DejaVu font files (fonts-dejavu-core) aren't installed." Printing once
    per missing path means that's now visible in journalctl instead.
    """
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        if path not in _warned_missing_font_paths:
            print(
                f"WARNING: could not load font '{path}' -- falling back to "
                "Pillow's tiny built-in bitmap font, which ignores the "
                "requested size and is missing many glyphs (e.g. '★'). "
                "Install the DejaVu fonts: sudo apt install fonts-dejavu-core",
                flush=True,
            )
            _warned_missing_font_paths.add(path)
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

    # max_size here is a ceiling, not a target -- _fit_text always picks
    # the largest size that actually fits the box, so raising these lets
    # short text (e.g. "Baba O'Riley") grow to fill its box instead of
    # being capped well below what the box has room for. Longer text
    # still shrinks automatically same as before; only the upper bound
    # moved.
    # max_size is deliberately set well above anything that could actually
    # fit any of these boxes -- _fit_text always picks the largest size
    # that fits, so this just makes sure the box's own width/height are
    # the real limit, not an arbitrary cap. Longer text still shrinks
    # automatically same as before.
    y = MARGIN
    font, lines, line_h = _fit_text(draw, title, FONT_PATH_BOLD, text_width, title_box_h, max_size=140, min_size=18)
    _draw_block(draw, lines, font, line_h, text_x, y, title_box_h)
    y += title_box_h

    font, lines, line_h = _fit_text(draw, artist, FONT_PATH_REGULAR, text_width, artist_box_h, max_size=140, min_size=14)
    _draw_block(draw, lines, font, line_h, text_x, y, artist_box_h)
    y += artist_box_h

    album_label = album if not owned else f"{album}  ★ in your collection"
    font, lines, line_h = _fit_text(draw, album_label, FONT_PATH_REGULAR, text_width, album_box_h, max_size=140, min_size=12)
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


def _compose_message_image(text, width, height):
    """Centered, word-wrapped status message filling the whole panel -- no
    album art, no artist/album blocks, just the message. Used for
    render_message (e.g. "Song not recognized"), as distinct from the
    three-block song-info layout in _compose_image.
    """
    image = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(image)

    max_width = width - 2 * MARGIN
    max_height = height - 2 * MARGIN
    font, lines, line_h = _fit_text(draw, text, FONT_PATH_BOLD, max_width, max_height, max_size=36, min_size=16)

    total_height = line_h * len(lines)
    y = MARGIN + max(0, (max_height - total_height) // 2)
    for line in lines:
        line_width = draw.textlength(line, font=font)
        x = MARGIN + max(0, (max_width - line_width) // 2)
        draw.text((x, y), line, font=font, fill=0)
        y += line_h

    return image


def render_message(text):
    """Renders a short centered status message instead of song info --
    used when the turntable is playing something AudD can't identify, so
    the display says so explicitly (e.g. "Song not recognized") rather
    than either showing stale song info or going silently blank. See
    main.py's _maybe_clear_for_unrecognized for the debounce logic that
    decides when this gets called.
    """
    if config.MOCK_MODE:
        os.makedirs(config.MOCK_DISPLAY_OUTPUT_DIR, exist_ok=True)
        image = _compose_message_image(text, *MOCK_DISPLAY_SIZE)
        out_path = os.path.join(config.MOCK_DISPLAY_OUTPUT_DIR, "now_playing.png")
        image.save(out_path)
        print(f"[mock display] Message: {text} -> {out_path}", flush=True)
        return

    import importlib

    epd_module = importlib.import_module(f"waveshare_epd.{config.DISPLAY_MODEL}")
    epd = epd_module.EPD()
    epd.init()
    epd.Clear()

    image = _compose_message_image(text, epd.width, epd.height)
    epd.display(epd.getbuffer(image))
    epd.sleep()


def clear_display():
    """Blanks the display entirely (no icon, no text) -- a low-level
    primitive kept around for a genuinely empty panel. main.py's idle
    state uses render_idle() instead, for a nicer resting screen; this is
    no longer called from the debounce logic, but still useful (e.g. if
    something later wants a truly blank panel, or during development).
    """
    if config.MOCK_MODE:
        os.makedirs(config.MOCK_DISPLAY_OUTPUT_DIR, exist_ok=True)
        blank = Image.new("1", MOCK_DISPLAY_SIZE, 255)
        out_path = os.path.join(config.MOCK_DISPLAY_OUTPUT_DIR, "now_playing.png")
        blank.save(out_path)
        print("[mock display] Cleared (blank)", flush=True)
        return

    import importlib

    epd_module = importlib.import_module(f"waveshare_epd.{config.DISPLAY_MODEL}")
    epd = epd_module.EPD()
    epd.init()
    epd.Clear()
    epd.sleep()


VINYL_GROOVE_COUNT = 5
# Icon-only is the default idle screen. Set to a string (e.g. "No record
# playing") and pass it explicitly to render_idle()/​_compose_idle_image
# if a caption is ever wanted again -- kept as a named constant here
# rather than deleted so that option stays a one-line change.
IDLE_CAPTION = "No record playing"


def _draw_vinyl_record(draw, cx, cy, radius):
    """Draws a simple vinyl record icon centered at (cx, cy): a black
    disc, a handful of thin concentric groove rings, a punched-out label
    near the center, and a small spindle hole through the middle of that.

    Pure drawing helper -- takes any ImageDraw and plain numbers, no
    MOCK_MODE/hardware dependency, so it's safe to unit test by inspecting
    pixels on an in-memory image, same as the text-layout helpers above.
    All black/white fills (no grays or dithering) since this is a crisp
    vector icon, not a photo -- unlike album_art.py's cover art, which
    dithers because it's downsampling a real photo.
    """
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=0)

    label_radius = radius * 0.38
    groove_band = radius - label_radius
    for i in range(1, VINYL_GROOVE_COUNT + 1):
        r = label_radius + groove_band * i / (VINYL_GROOVE_COUNT + 1)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=255, width=1)

    draw.ellipse(
        [cx - label_radius, cy - label_radius, cx + label_radius, cy + label_radius],
        fill=255,
    )
    hole_radius = max(2, radius * 0.045)
    draw.ellipse(
        [cx - hole_radius, cy - hole_radius, cx + hole_radius, cy + hole_radius],
        fill=0,
    )


def _compose_idle_image(width, height, caption=None):
    """Vinyl record icon centered in the panel, with an optional short
    caption underneath -- the resting screen shown once the turntable's
    been silent (or playing something unrecognized) past the debounce
    (see main.py's _maybe_clear_for_silence/_maybe_clear_for_unrecognized),
    replacing the old plain-blank/text-message behavior with something
    that still reads as "this is a record player" at a glance. Icon-only
    (caption=None) is the default; pass a string (e.g. IDLE_CAPTION) for a
    caption underneath instead.
    """
    image = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(image)

    caption_area_h = 0
    if caption:
        caption_area_h = int(height * 0.22)

    icon_area_h = height - caption_area_h
    radius = int(min(width, icon_area_h) * 0.5) - MARGIN
    cx = width // 2
    cy = icon_area_h // 2
    _draw_vinyl_record(draw, cx, cy, radius)

    if caption:
        max_width = width - 2 * MARGIN
        font, lines, line_h = _fit_text(
            draw, caption, FONT_PATH_REGULAR, max_width, caption_area_h, max_size=32, min_size=14
        )
        total_height = line_h * len(lines)
        y = icon_area_h + max(0, (caption_area_h - total_height) // 2)
        for line in lines:
            line_width = draw.textlength(line, font=font)
            x = MARGIN + max(0, (max_width - line_width) // 2)
            draw.text((x, y), line, font=font, fill=0)
            y += line_h

    return image


def render_idle(caption=None):
    """Renders the vinyl-record resting screen -- shown once the turntable
    has been silent, or playing something unrecognized, long enough that
    whatever was on screen counts as stale (see main.py's
    _maybe_clear_for_silence/_maybe_clear_for_unrecognized for the
    debounce logic that decides when). Icon-only by default; pass a
    caption string (e.g. IDLE_CAPTION) for a caption underneath instead.
    """
    if config.MOCK_MODE:
        os.makedirs(config.MOCK_DISPLAY_OUTPUT_DIR, exist_ok=True)
        image = _compose_idle_image(*MOCK_DISPLAY_SIZE, caption=caption)
        out_path = os.path.join(config.MOCK_DISPLAY_OUTPUT_DIR, "now_playing.png")
        image.save(out_path)
        print("[mock display] Idle (vinyl icon)", flush=True)
        return

    import importlib

    epd_module = importlib.import_module(f"waveshare_epd.{config.DISPLAY_MODEL}")
    epd = epd_module.EPD()
    epd.init()
    epd.Clear()

    image = _compose_idle_image(epd.width, epd.height, caption=caption)
    epd.display(epd.getbuffer(image))
    epd.sleep()
