"""Pulls the latest code from GitHub and reinstalls dependencies, for the
dashboard's Update button -- see docs/SETUP.md "Web UI" > "Updating".
"""
import os
import subprocess

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
VENV_PIP = os.path.join(PROJECT_ROOT, "venv", "bin", "pip")


def _run(cmd, cwd=None, timeout=30, env=None):
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except FileNotFoundError as e:
        return {"ok": False, "output": f"{cmd[0]} not found: {e}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"Timed out after {timeout}s running: {' '.join(cmd)}"}
    return {"ok": result.returncode == 0, "output": ((result.stdout or "") + (result.stderr or "")).strip()}


def pull_latest():
    """Runs `git pull --ff-only` in the project root.

    --ff-only refuses to create a merge commit or silently reconcile
    diverged history -- if the local branch has commits that aren't on
    the remote (e.g. someone edited a tracked file directly on the Pi),
    this fails loudly with a clear message instead of doing something
    surprising unattended. Only ever pulls; never resets/force-anything,
    so a bad pull can't lose local work.

    GIT_TERMINAL_PROMPT=0 makes a git that unexpectedly needs credentials
    (e.g. the remote went private) fail immediately instead of hanging
    until the subprocess timeout -- there's no terminal here to prompt.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return _run(["git", "pull", "--ff-only"], cwd=PROJECT_ROOT, timeout=30, env=env)


def pulled_new_commits(pull_result):
    """True if pull_latest() actually brought in new commits -- as
    opposed to succeeding with nothing to do, in which case there's no
    reason to reinstall dependencies or restart anything.
    """
    return pull_result["ok"] and "Already up to date" not in pull_result["output"]


def install_requirements():
    """Re-installs requirements.txt into the project's venv -- picks up
    any new/changed dependency after a pull. pip is a fast no-op when
    nothing changed, but a real dependency bump (numpy, Pillow, etc.) can
    take a while on a Pi Zero's single core, hence the generous timeout.
    """
    if not os.path.exists(VENV_PIP):
        return {"ok": False, "output": f"{VENV_PIP} not found -- is the venv set up?"}
    requirements_path = os.path.join(PROJECT_ROOT, "requirements.txt")
    return _run([VENV_PIP, "install", "-r", requirements_path], timeout=600)
