"""Runs the dashboard's "Pull latest & restart" as a background job whose
progress the page can poll, instead of one long blocking request.

Steps: pull -> install dependencies -> restart the identifier service
(and wait until it's really running the new code) -> restart the
dashboard itself. Progress lives in .state/update.json rather than in
memory because the last step restarts this very process: the page keeps
polling, briefly can't connect, and the *new* process picks the file back
up and marks the job finished (see _reconcile).

"Restart" always means the systemd services, never the Pi itself.
"""
import json
import os
import threading
import time

from .. import config, status
from . import service_control, updater

STATE_PATH = os.path.join(config.STATE_DIR, "update.json")
TIMING_PATH = os.path.join(config.STATE_DIR, "update_timing.json")

# When this process started; a dashboard restart is confirmed by a process
# that started after the restart was requested.
PROCESS_STARTED = time.time()

# Rough expectations on a Pi Zero, used until real timings have been
# recorded from earlier updates (see _record_timing).
DEFAULT_ESTIMATES = {"main": 60, "web": 15}
MAIN_READY_TIMEOUT = 240
WEB_RESTART_TIMEOUT = 60
STALL_TIMEOUT = 900  # pip on a Pi Zero can legitimately take many minutes

STEP_DEFS = [
    ("pull", "Pulling latest code from GitHub"),
    ("deps", "Installing dependencies"),
    ("main", "Restarting the identifier service"),
    ("web", "Restarting the dashboard"),
]

_lock = threading.Lock()


def _read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f)
    os.replace(tmp_path, path)


def _save(state):
    state["updated_at"] = time.time()
    _write_json(STATE_PATH, state)


def _estimates():
    recorded = _read_json(TIMING_PATH, {})
    return {key: round(recorded.get(key, default)) for key, default in DEFAULT_ESTIMATES.items()}


def _record_timing(key, seconds):
    recorded = _read_json(TIMING_PATH, {})
    recorded[key] = seconds
    _write_json(TIMING_PATH, recorded)


def _new_state():
    return {
        "running": True,
        "ok": None,
        "started_at": time.time(),
        "updated_at": time.time(),
        "finished_at": None,
        "summary": "",
        "web_restart_requested_at": None,
        "estimates": _estimates(),
        "steps": [
            {"id": step_id, "label": label, "status": "pending", "detail": "", "started_at": None}
            for step_id, label in STEP_DEFS
        ],
    }


def _step(state, step_id):
    return next(step for step in state["steps"] if step["id"] == step_id)


def _begin(state, step_id, detail=""):
    step = _step(state, step_id)
    step.update(status="running", detail=detail, started_at=time.time())
    _save(state)


def _end(state, step_id, outcome, detail=""):
    _step(state, step_id).update(status=outcome, detail=detail)
    _save(state)


def _skip_pending(state, detail=""):
    for step in state["steps"]:
        if step["status"] == "pending":
            step.update(status="skipped", detail=detail)


def _finish(state, ok, summary):
    state.update(running=False, ok=ok, summary=summary, finished_at=time.time())
    _save(state)


def main_is_stale():
    """True if the main service is running older code than what's on disk
    -- i.e. a pull happened but it never restarted.

    Ignores a status report older than the service's current start: the
    new process hasn't reported in yet (importing everything and the first
    recording take a while on a Pi Zero), so the file still describes its
    predecessor and says nothing about the code now running.
    """
    if service_control.get_status() != "active":
        return False
    reported = status.read_status()
    started = service_control.get_start_time()
    if started and (reported.get("updated_at") or 0) < started:
        return False
    return status.code_is_stale(reported.get("code_version"), status.current_commit())


def _reconcile(state):
    """Settles a job that's marked running but whose thread may be gone --
    chiefly the dashboard-restart step, which kills the thread that was
    running the job. Called whenever the state is read.
    """
    now = time.time()
    web_step = _step(state, "web")
    requested = state.get("web_restart_requested_at")

    if web_step["status"] == "running" and requested:
        if PROCESS_STARTED > requested:
            _record_timing("web", PROCESS_STARTED - requested)
            web_step.update(status="done", detail="Dashboard is back up.")
            _finish(state, True, f"Updated to v{status.current_version()}. Both services restarted.")
        elif now - requested > WEB_RESTART_TIMEOUT:
            web_step.update(status="failed", detail="The dashboard didn't restart.")
            _finish(
                state, False,
                "The code was updated and the identifier service restarted, but the dashboard "
                "itself didn't restart. Run: sudo systemctl restart groove-tracker-web",
            )
    elif now - state.get("updated_at", now) > STALL_TIMEOUT:
        _finish(state, False, "The update was interrupted before it finished.")

    return state


def get_state():
    """Current job state for the page, or {"idle": True} if no update has
    ever run. Always includes "now" (server time) so the page can show
    elapsed time without trusting its own clock.
    """
    with _lock:
        state = _read_json(STATE_PATH, None)
        if state is None:
            return {"idle": True, "running": False, "now": time.time()}
        if state.get("running"):
            state = _reconcile(state)
        state["now"] = time.time()
        return state


def start():
    """Starts an update in the background. Returns (started, reason)."""
    with _lock:
        existing = _read_json(STATE_PATH, None)
        if existing and existing.get("running"):
            existing = _reconcile(existing)
            if existing.get("running"):
                return False, "An update is already in progress."
        state = _new_state()
        _save(state)
    threading.Thread(target=_run, args=(state,), daemon=True).start()
    return True, ""


def _fail(state, step_id, detail, summary):
    _end(state, step_id, "failed", detail)
    _skip_pending(state, "Not run")
    _finish(state, False, summary)


def _wait_for_main(state, started, target_commit):
    """Waits until the restarted identifier service is active and has
    reported in from the target commit. Returns (ok, detail)."""
    estimate = state["estimates"]["main"]
    deadline = started + MAIN_READY_TIMEOUT
    while time.time() < deadline:
        service_state = service_control.get_status()
        reported = status.read_status()
        if service_state == "failed":
            return False, "The service failed to start.\n" + "\n".join(service_control.recent_logs(8))
        fresh = (reported.get("updated_at") or 0) > started
        right_code = target_commit is None or reported.get("code_version") == target_commit
        if service_state == "active" and fresh and right_code:
            return True, ""
        elapsed = int(time.time() - started)
        _step(state, "main")["detail"] = (
            f"Waiting for it to start up... {elapsed}s so far (usually about {estimate}s)"
        )
        _save(state)
        time.sleep(2)
    return False, (
        f"It didn't report in within {MAIN_READY_TIMEOUT}s.\n" + "\n".join(service_control.recent_logs(8))
    )


def _run(state):
    try:
        _begin(state, "pull")
        pulled_result = updater.pull_latest()
        if not pulled_result["ok"]:
            _fail(state, "pull", pulled_result["output"][-400:], "git pull failed -- nothing was changed.")
            return
        output_lines = pulled_result["output"].strip().splitlines()
        _end(state, "pull", "done", output_lines[-1] if output_lines else "")

        pulled = updater.pulled_new_commits(pulled_result)
        # Also restart if the code was already pulled by other means (e.g.
        # by hand over SSH) but the identifier service never picked it up --
        # otherwise "Already up to date" would leave it on old code forever.
        stale = main_is_stale()

        if not pulled and not stale:
            _skip_pending(state, "Nothing to do")
            _finish(state, True, f"Already up to date (v{status.current_version()}).")
            return

        if not pulled:
            # Decided up front so the page's time estimate only counts
            # steps that will actually run.
            _end(state, "deps", "skipped", "No new code")
            _end(state, "web", "skipped", "No new code")

        if pulled:
            _begin(state, "deps")
            deps = updater.install_requirements()
            if not deps["ok"]:
                _fail(
                    state, "deps", deps["output"][-400:],
                    "Installing dependencies failed, so the services were NOT restarted "
                    "(they're still running the previous code).",
                )
                return
            _end(state, "deps", "done")

        target = status.current_commit()
        _begin(state, "main", "Restarting...")
        restart_started = time.time()
        restarted = service_control.restart()
        if not restarted["ok"]:
            _fail(state, "main", restarted["output"].strip()[-400:], "Couldn't restart the identifier service.")
            return
        ready, detail = _wait_for_main(state, restart_started, target)
        if not ready:
            _fail(state, "main", detail, "The identifier service restarted but didn't come back up properly.")
            return
        seconds = time.time() - restart_started
        _record_timing("main", seconds)
        _end(state, "main", "done", f"Running {target or 'the new code'} after {int(seconds)}s")

        if not pulled:
            _finish(state, True, f"Identifier service restarted (v{status.current_version()}).")
            return

        state["web_restart_requested_at"] = time.time()
        _begin(state, "web", "Restarting -- this page will reconnect on its own.")
        if not service_control.restart_self_delayed():
            _fail(state, "web", "Couldn't start the restart command.", "Couldn't restart the dashboard.")
        # Otherwise this process is about to be replaced; the new one
        # confirms the restart and finishes the job (see _reconcile).
    except Exception as e:
        _finish(state, False, f"Update failed unexpectedly: {e}")
