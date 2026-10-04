"""Groove Tracker — identifies what's playing on the turntable and shows it
on a small e-paper display, preferring the release you actually own in
your DVinyl collection over whatever original album the recognition API
suggests.
"""

import os as _os

try:
    with open(_os.path.join(_os.path.dirname(__file__), "..", "VERSION")) as _f:
        __version__ = _f.read().strip() or "unknown"
except OSError:
    __version__ = "unknown"
