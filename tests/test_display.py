"""
Tests the pure layout helpers in display.py directly -- _wrap_by_pixel and
_fit_text take a plain ImageDraw and text, with no MOCK_MODE or hardware
dependency, so they're safe to unit test the same way as
_compute_rms_level and _fit_square.
"""
from PIL import Image, ImageDraw

from groove_tracker.display import FONT_PATH_REGULAR, _fit_text, _wrap_by_pixel

_draw = ImageDraw.Draw(Image.new("1", (10, 10)))


def test_wrap_by_pixel_keeps_short_text_on_one_line():
    from groove_tracker.display import _load_font

    font = _load_font(FONT_PATH_REGULAR, 20)
    lines = _wrap_by_pixel(_draw, "Baba O'Riley", font, max_width=1000)
    assert lines == ["Baba O'Riley"]


def test_wrap_by_pixel_splits_long_text_across_lines():
    from groove_tracker.display import _load_font

    font = _load_font(FONT_PATH_REGULAR, 20)
    long_title = "This Is A Very Long Song Title That Will Not Fit On One Line"
    lines = _wrap_by_pixel(_draw, long_title, font, max_width=150)
    assert len(lines) > 1
    # No line should exceed the requested width.
    for line in lines:
        assert _draw.textlength(line, font=font) <= 150


def test_fit_text_picks_a_large_font_for_short_text_in_a_big_box():
    font, lines, line_height = _fit_text(
        _draw, "Baba O'Riley", FONT_PATH_REGULAR, max_width=400, max_height=200, max_size=44, min_size=12
    )
    # Should use the largest available size since a short title easily
    # fits a generous box -- this is the "fill the screen" behavior.
    assert font.size == 44
    assert lines == ["Baba O'Riley"]


def test_fit_text_shrinks_for_long_text_in_a_small_box():
    long_title = "This Is A Very Long Song Title That Will Not Fit On One Line At A Large Size"
    font, lines, line_height = _fit_text(
        _draw, long_title, FONT_PATH_REGULAR, max_width=200, max_height=80, max_size=44, min_size=12
    )
    assert font.size < 44
    assert line_height * len(lines) <= 80 or font.size == 12
