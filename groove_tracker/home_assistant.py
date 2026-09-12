"""
Reports whether music is currently playing to Home Assistant, by setting
binary_sensor.groove_tracker_playing via the REST API. A Home Assistant
automation (created separately, see docs/SETUP.md) watches that entity
and turns a nearby light on/off accordingly.

This entity isn't backed by a real HA integration — it's set directly via
the states API, which is the standard lightweight pattern for reporting
state from an external device that doesn't warrant a full custom
integration. It'll show as "unavailable" until the first successful
report after each Home Assistant restart, which is expected.
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
