"""Wraps the handful of systemctl/journalctl calls the web dashboard needs,
so app.py doesn't shell out directly.

The web UI runs as its own systemd service, under the same unprivileged
user as groove-tracker.service (never as root -- see docs/SETUP.md's Web
UI section for the sudoers drop-in install.sh installs, which grants only
these exact `systemctl start/stop/restart groove-tracker` commands via
`sudo -n`, nothing broader). `-n` (non-interactive) makes a missing/wrong
sudoers rule fail immediately with a clear error instead of hanging on a
password prompt that can never be answered from a web request.

Every function here is safe to call from a machine with no systemd at all
(e.g. this repo's own dev sandbox, or a Windows dev machine) -- a missing
systemctl/journalctl/sudo binary is caught and reported as a normal
"unavailable" result rather than raising, the same way the rest of this
project treats hardware that isn't present (see MOCK_MODE elsewhere).
"""
import subprocess

SERVICE_NAME = "groove-tracker.service"
_TIMEOUT = 15


class CommandUnavailable(Exception):
    """Raised when the underlying binary (systemctl/journalctl/sudo) isn't
    on PATH at all -- distinct from the command running and failing, which
    callers surface via the normal returncode/stderr on the result dict.
    """


def _run(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT)
    except FileNotFoundError as e:
        raise CommandUnavailable(str(e)) from e
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "output": f"Timed out after {_TIMEOUT}s: {e}"}
    return {
        "ok": result.returncode == 0,
        "output": (result.stdout or "") + (result.stderr or ""),
    }


def get_status():
    """Returns one of: active, inactive, failed, activating, deactivating,
    unknown (any other systemctl output), or "unavailable" (systemctl
    itself isn't present -- not running under systemd at all).
    `systemctl is-active` is read-only and needs no sudo.
    """
    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
    except FileNotFoundError:
        return "unavailable"
    except subprocess.TimeoutExpired:
        return "unknown"
    return result.stdout.strip() or "unknown"


def start():
    try:
        return _run(["sudo", "-n", "systemctl", "start", SERVICE_NAME])
    except CommandUnavailable as e:
        return {"ok": False, "output": f"systemctl/sudo not available: {e}"}


def stop():
    try:
        return _run(["sudo", "-n", "systemctl", "stop", SERVICE_NAME])
    except CommandUnavailable as e:
        return {"ok": False, "output": f"systemctl/sudo not available: {e}"}


def restart():
    try:
        return _run(["sudo", "-n", "systemctl", "restart", SERVICE_NAME])
    except CommandUnavailable as e:
        return {"ok": False, "output": f"systemctl/sudo not available: {e}"}


def restart_self_delayed(delay_seconds=2):
    """Restarts groove-tracker-web.service (this very process) a couple
    seconds from now, detached from the current request -- used after the
    dashboard's Update button pulls new code, so the web UI picks it up
    too. Doing this synchronously would kill the process handling this
    request before the browser ever got a response; the short delay, in a
    detached subprocess that outlives this one, gives Flask time to finish
    sending the redirect first.
    """
    try:
        subprocess.Popen(
            ["sh", "-c", f"sleep {delay_seconds} && sudo -n systemctl restart groove-tracker-web.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except FileNotFoundError:
        return False


def recent_logs(lines=200):
    """Returns the last `lines` journal entries for groove-tracker.service,
    newest last, or a single-element list explaining why not (no journalctl
    on this machine, or this user can't read the system journal -- the
    latter is fixed by adding the user to the `systemd-journal` group,
    which install.sh does).
    """
    try:
        result = subprocess.run(
            ["journalctl", "-u", SERVICE_NAME, "-n", str(lines), "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
    except FileNotFoundError:
        return ["journalctl is not available on this machine."]
    except subprocess.TimeoutExpired:
        return ["Timed out reading the journal."]

    if result.returncode != 0:
        return [(result.stderr or "Could not read logs.").strip()]

    return result.stdout.splitlines()
