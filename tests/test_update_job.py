"""Tests the update job's state handling -- chiefly how a job that was
interrupted by the dashboard restarting itself gets settled by the new
process. Uses temp files and monkeypatched clocks; never runs git or
touches systemd.
"""
import time

import pytest

from groove_tracker.webui import update_job


@pytest.fixture(autouse=True)
def temp_state_files(tmp_path, monkeypatch):
    monkeypatch.setattr(update_job, "STATE_PATH", str(tmp_path / "update.json"))
    monkeypatch.setattr(update_job, "TIMING_PATH", str(tmp_path / "timing.json"))


def _state_awaiting_web_restart(requested_at):
    state = update_job._new_state()
    for step in state["steps"]:
        step["status"] = "done"
    update_job._step(state, "web")["status"] = "running"
    state["web_restart_requested_at"] = requested_at
    return state


def test_new_process_completes_a_pending_dashboard_restart(monkeypatch):
    monkeypatch.setattr(update_job, "PROCESS_STARTED", time.time())
    state = _state_awaiting_web_restart(requested_at=time.time() - 5)

    result = update_job._reconcile(state)

    assert result["running"] is False
    assert result["ok"] is True
    assert update_job._step(result, "web")["status"] == "done"


def test_old_process_does_not_claim_the_restart_happened(monkeypatch):
    # The process that requested the restart started *before* it, so it
    # must not mistake itself for the new one.
    monkeypatch.setattr(update_job, "PROCESS_STARTED", time.time() - 100)
    state = _state_awaiting_web_restart(requested_at=time.time() - 5)

    result = update_job._reconcile(state)

    assert result["running"] is True


def test_dashboard_restart_that_never_happens_is_reported_as_failed(monkeypatch):
    monkeypatch.setattr(update_job, "PROCESS_STARTED", time.time() - 1000)
    state = _state_awaiting_web_restart(requested_at=time.time() - update_job.WEB_RESTART_TIMEOUT - 5)

    result = update_job._reconcile(state)

    assert result["running"] is False
    assert result["ok"] is False
    assert "systemctl restart groove-tracker-web" in result["summary"]


def test_stalled_job_is_marked_interrupted():
    state = update_job._new_state()
    update_job._step(state, "pull")["status"] = "running"
    state["updated_at"] = time.time() - update_job.STALL_TIMEOUT - 1

    result = update_job._reconcile(state)

    assert result["running"] is False
    assert result["ok"] is False


def test_cannot_start_a_second_update_while_one_is_running():
    update_job._save(update_job._new_state())

    started, reason = update_job.start()

    assert started is False
    assert "already" in reason.lower()


def test_get_state_is_idle_when_no_update_has_ever_run():
    state = update_job.get_state()

    assert state["idle"] is True
    assert state["running"] is False
