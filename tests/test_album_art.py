"""
Tests the pure image-transform function (_fit_square) directly, not the
public get_album_art wrapper -- that branches on config.MOCK_MODE (fixed
at first import, per CLAUDE.md's testing conventions) and does network I/O
in real mode.
"""
from PIL import Image

from groove_tracker.album_art import _fit_square


def test_fit_square_resizes_to_requested_size():
    image = Image.new("RGB", (600, 600), (10, 20, 30))
    result = _fit_square(image, 150)
    assert result.size == (150, 150)


def test_fit_square_converts_to_grayscale():
    image = Image.new("RGB", (300, 300), (200, 50, 50))
    result = _fit_square(image, 100)
    assert result.mode == "L"


def test_fit_square_center_crops_non_square_source():
    # A wide (non-square) source should be cropped to a centered square
    # before resizing, not squashed/stretched.
    image = Image.new("RGB", (400, 200), (0, 0, 0))
    # Paint a white square in the vertical center strip so we can check
    # the crop kept the middle, not an edge.
    for x in range(150, 250):
        for y in range(0, 200):
            image.putpixel((x, y), (255, 255, 255))

    result = _fit_square(image, 50)
    assert result.size == (50, 50)
    # Center pixel should have landed in the white strip.
    center_value = result.getpixel((25, 25))
    assert center_value > 200  # bright (white), not black background
