"""Flask app for the Groove Tracker web dashboard -- lets you check status,
start/stop/restart the service, tail its logs, and edit .env from a
browser instead of SSH. See docs/SETUP.md's "Web UI" section for how it's
installed/hosted (its own systemd service, alongside groove-tracker.service,
reachable at http://<hostname>.local:8420/ on your LAN).

Runs as a separate process from groove-tracker.service itself (see
groove_tracker/status.py's docstring for why) -- this file only ever reads
status.json / the display preview PNG and shells out to systemctl/
journalctl; it never imports audio_capture/identify/collection_match/
display, so it has no hardware or network dependency of its own and stays
usable even if the main service is stopped or crashed.
"""
import functools
import os
import secrets

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for

from .. import config, status
from . import env_editor, service_control, update_job


def _password_configured():
    return bool(config.WEBUI_PASSWORD)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not _password_configured() or session.get("authed"):
            return view(*args, **kwargs)
        return redirect(url_for("login", next=request.path))

    return wrapped


def create_app():
    app = Flask(__name__)
    # Falls back to a random per-process key if WEBUI_SECRET_KEY isn't set
    # in .env yet -- sessions just won't survive a restart until it is
    # (install.sh sets a persistent one during setup).
    app.secret_key = config.WEBUI_SECRET_KEY or secrets.token_hex(32)

    @app.get("/login")
    def login():
        if not _password_configured():
            return redirect(url_for("dashboard"))
        return render_template("login.html", error=None)

    @app.post("/login")
    def login_submit():
        if request.form.get("password") == config.WEBUI_PASSWORD:
            session["authed"] = True
            next_path = request.args.get("next") or url_for("dashboard")
            return redirect(next_path)
        return render_template("login.html", error="Wrong password."), 401

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def dashboard():
        status_data = status.read_status()
        service_state = service_control.get_status()
        return render_template(
            "dashboard.html",
            status=status_data,
            stale=update_job.main_is_stale(),
            running_commit=status_data.get("code_version") or "an older version",
            disk_commit=status.current_commit(),
            version=status.current_version() or "unknown",
            history=status.read_history(),
            service_status=service_state,
            password_configured=_password_configured(),
            preview_exists=os.path.exists(config.DISPLAY_PREVIEW_PATH),
            flash=request.args.get("flash"),
            flash_msg=request.args.get("msg"),
        )

    @app.get("/api/status")
    @login_required
    def api_status():
        return jsonify({
            **status.read_status(),
            "service_status": service_control.get_status(),
            "history": status.read_history(),
        })

    @app.get("/preview.png")
    @login_required
    def preview():
        if not os.path.exists(config.DISPLAY_PREVIEW_PATH):
            return "", 404
        # Always re-read from disk (no client caching) -- this changes
        # every time a new song is recognized/cleared, and staleness here
        # would be exactly the kind of confusing "is it working?" bug this
        # dashboard exists to avoid.
        response = send_file(config.DISPLAY_PREVIEW_PATH, max_age=0)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/service/<action>")
    @login_required
    def service_action(action):
        actions = {
            "start": service_control.start,
            "stop": service_control.stop,
            "restart": service_control.restart,
        }
        if action not in actions:
            return "Unknown action", 400
        result = actions[action]()
        return redirect(url_for("dashboard", flash=("ok" if result["ok"] else "error"), msg=result["output"][:500]))

    @app.post("/update")
    @login_required
    def update():
        started, reason = update_job.start()
        return jsonify({"started": started, "reason": reason}), (200 if started else 409)

    @app.get("/api/update_status")
    @login_required
    def api_update_status():
        return jsonify(update_job.get_state())

    @app.get("/logs")
    @login_required
    def logs():
        return render_template("logs.html")

    @app.get("/api/logs")
    @login_required
    def api_logs():
        lines = request.args.get("lines", default=200, type=int)
        return jsonify({"lines": service_control.recent_logs(lines=min(lines, 2000))})

    @app.get("/config")
    @login_required
    def config_page():
        return render_template("config.html", groups=env_editor.build_form_groups(), saved=request.args.get("saved"))

    @app.post("/config")
    @login_required
    def config_save():
        updates = {}
        for _, fields in env_editor.FIELDS:
            for key, field_type, _label, secret, _help in fields:
                if field_type == "bool":
                    updates[key] = "true" if request.form.get(key) else "false"
                    continue
                value = request.form.get(key, "")
                if secret and not value:
                    continue  # blank secret field = keep the existing value
                updates[key] = value

        text = env_editor.apply_updates(env_editor.read_env_file(), updates)
        env_editor.write_env_file(text)

        restart_after = bool(request.form.get("restart_after_save"))
        if restart_after:
            service_control.restart()

        return redirect(url_for("config_page", saved="1"))

    return app
