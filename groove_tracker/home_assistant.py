"""
Reports playback status to Home Assistant via the REST API, across two
separate entities:

- binary_sensor.groove_tracker_playing (set_playing_state): plain on/off,
  watched by a Home Assistant automation (created separately, see
  docs/SETUP.md) that turns a nearby light on/off accordingly.
- media_player.groove_tracker (set_now_playing): the actual song info
  (title/artist/album), shown by Home Assistant's media-control and tile
  cards -- a separate entity because a dashboard wants to show/hide the
  card and its content very differently from how an automation wants to
  gate a light. State is "playing" with media_* attributes while a song
  is recognized, and "idle" with none otherwise. No artwork is sent.

Neither entity is backed by a real HA integration -- both are set
directly via the states API, the standard lightweight pattern for
reporting state from an external device that doesn't warrant a full
custom integration. Each will show as "unavailable" until its first
successful report after a Home Assistant restart, which is expected.
"""
import requests

from . import config


def set_playing_state(is_playing):
    """Sets the groove_tracker_playing binary_sensor in Home Assistant.

    Called every poll cycle (not just on change) so the entity heals
    itself after a Home Assistant restart, rather than staying stale.
    """
    if config.MOCK_MODE:
        print(f"[mock home assistant] {config.HA_PLAYING_ENTITY_ID} -> {'on' if is_playing else 'off'}")
        return

    if not config.HA_URL or not config.HA_TOKEN:
        # Not configured — treat as an optional feature rather than an error.
        return

    url = f"{config.HA_URL.rstrip('/')}/api/states/{config.HA_PLAYING_ENTITY_ID}"
    headers = {
        "Authorization": f"Bearer {config.HA_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "state": "on" if is_playing else "off",
        "attributes": {
            "friendly_name": "Groove Tracker Playing",
            "device_class": "sound",
        },
    }
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()


def _build_now_playing_payload(artist, title, album, owned):
    """Pure construction of the media_player entity's state/attributes --
    no MOCK_MODE or network dependency, safe to unit test directly, same
    pattern as the other pure helpers in this project (_compute_rms_level,
    _find_best_candidate, etc).

    artist=None means "nothing recognized right now" (idle or playing-but-
    unrecognized) -- mapped to the "idle" state with no media_* attributes
    (the states API replaces attributes wholesale, so stale song info
    can't linger on the card).

    Deliberately sends no entity_picture/artwork -- the media player card
    just shows title/artist/album text.
    """
    if artist is None:
        return "idle", {"friendly_name": "Groove Tracker", "device_class": "speaker"}

    attributes = {
        "friendly_name": "Groove Tracker",
        "device_class": "speaker",
        "media_content_type": "music",
        "media_title": title,
        "media_artist": artist,
        "media_album_name": album or "",
        "owned": owned,
    }
    return "playing", attributes


def set_now_playing(artist=None, title=None, album=None, owned=False):
    """Sets config.HA_NOW_PLAYING_ENTITY_ID (a media_player) in Home
    Assistant to reflect the currently recognized song -- separate from
    the plain on/off binary_sensor above.

    Call with no arguments to reset to "idle" -- main.py does this
    whenever it shows the idle screen (see _maybe_clear_for_silence/
    _maybe_clear_for_unrecognized), so the card doesn't keep showing
    stale song info once the e-paper display itself has already moved on.
    """
    state, attributes = _build_now_playing_payload(artist, title, album, owned)

    if config.MOCK_MODE:
        print(f"[mock home assistant] {config.HA_NOW_PLAYING_ENTITY_ID} -> {state}")
        return

    if not config.HA_URL or not config.HA_TOKEN:
        return

    url = f"{config.HA_URL.rstrip('/')}/api/states/{config.HA_NOW_PLAYING_ENTITY_ID}"
    headers = {
        "Authorization": f"Bearer {config.HA_TOKEN}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        url, json={"state": state, "attributes": attributes}, headers=headers, timeout=10
    )
    response.raise_for_status()
