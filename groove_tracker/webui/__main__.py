"""Run with:  python3 -m groove_tracker.webui
(installed as its own systemd service by install.sh -- see
systemd/groove-tracker-web.service and docs/SETUP.md's "Web UI" section)
"""
from .. import config
from .app import create_app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=config.WEBUI_PORT, threaded=True)
