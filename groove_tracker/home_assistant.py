"""
Reports playback status to Home Assistant via the REST API, across two
separate entities:

- binary_sensor.groove_tracker_playing (set_playing_state): plain on/off,
  watched by a Home Assistant automation (created separately, see
  docs/SETUP.md) that turns a nearby light on/off accordingly.
- sensor.groove_tracker_now_playing (set_now_playing): the actual song
  info (artist/title/album/art), for a dashboard card to display -- a
  separate entity because a dashboard wants to show/hide the card and its
  content very differently from how an automation wants to gate a light,
  and because the binary_sensor's "unavailable until first report" boot
  behavior is fine for a light gate but would be a confusing dashboard
  card state ("unavailable" vs. a clean "Not playing").

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


def _build_now_playing_payload(artist, title, album, owned, art_url):
    """Pure construction of the now-playing sensor's state/attributes --
    no MOCK_MODE or network dependency, safe to unit test directly, same
    pattern as the other pure helpers in this project (_compute_rms_level,
    _find_best_candidate, etc).

    artist=None means "nothing recognized right now" (idle or playing-but-
    unrecognized) -- mapped to a distinct "Not playing" state with no
    song attributes, rather than leaving stale song info sitting on an
    entity a dashboard card is reading from.

    art_url (when present) is set as both a plain "art_url" attribute and
    as "entity_picture" -- the latter is what Home Assistant's frontend
    recognizes to show an entity's thumbnail automatically (e.g. in a
    Picture Entity or Glance card), so the same URL doubles as both a
    plain data field and the thing that makes the picture actually show
    up without extra dashboard configuration.
    """
    if artist is None:
        return "Not playing", {"friendly_name": "Groove Tracker Now Playing"}

    # HA state values are capped at 255 characters -- title/artist should
    # never come remotely close, but truncate defensively rather than let
    # a pathological AudD result turn into a 400 from the states API.
    state = f"{title} — {artist}"[:255]
    attributes = {
        "friendly_name": "Groove Tracker Now Playing",
        "artist": artist,
        "title": title,
        "album": album,
        "owned": owned,
    }
    if art_url:
        attributes["art_url"] = art_url
        attributes["entity_picture"] = art_url

    return state, attributes


def set_now_playing(artist=None, title=None, album=None, owned=False, art_url=None):
    """Sets config.HA_NOW_PLAYING_ENTITY_ID in Home Assistant to reflect
    the currently recognized song, for a dashboard card -- separate from
    the plain on/off binary_sensor above.

    Call with no arguments to reset to a "Not playing" state -- main.py
    does this whenever it shows the idle screen (see
    _maybe_clear_for_silence/_maybe_clear_for_unrecognized), so the
    dashboard card doesn't keep showing stale song info once the e-paper
    display itself has already moved on.
    """
    state, attributes = _build_now_playing_payload(artist, title, album, owned, art_url)

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
