from datetime import datetime, timedelta, timezone

import pytest

from src.shl.poller import PollerError, run_poller_tick, run_poller_worker
from src.shl.store import (
    list_due_poll_targets,
    list_unprocessed_domain_events,
    mark_domain_event_processed,
    upsert_poll_target,
)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def test_upsert_poll_target_and_list_due(tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    due_id = upsert_poll_target(
        tmp_path,
        target_type="schedule",
        target_key="18263",
        enabled=True,
        next_poll_at=_iso(now - timedelta(minutes=1)),
    )
    upsert_poll_target(
        tmp_path,
        target_type="standings",
        target_key="18263",
        enabled=True,
        next_poll_at=_iso(now + timedelta(minutes=10)),
    )

    due = list_due_poll_targets(tmp_path, now_iso=_iso(now))
    assert [item["id"] for item in due] == [due_id]
    assert due[0]["target_type"] == "schedule"
    assert due[0]["target_key"] == "18263"


def test_run_poller_tick_success_updates_state_and_writes_event(monkeypatch, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    upsert_poll_target(
        tmp_path,
        target_type="schedule",
        target_key="18263",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
    )

    calls = {"fetch_schedule": 0}

    def fake_fetch_schedule(season_id, db_dir):
        calls["fetch_schedule"] += 1
        assert season_id == 18263
        assert db_dir == tmp_path

    monkeypatch.setattr("src.shl.poller.fetch_schedule", fake_fetch_schedule)

    results = run_poller_tick(tmp_path, now=now)

    assert len(results) == 1
    assert results[0]["status"] == "ok"
    assert calls["fetch_schedule"] == 1

    # The same target should no longer be due immediately after success.
    due_after = list_due_poll_targets(tmp_path, now_iso=_iso(now))
    assert due_after == []

    events = list_unprocessed_domain_events(tmp_path)
    assert len(events) == 1
    assert events[0]["event_type"] == "poll_completed"
    assert events[0]["aggregate_key"] == "schedule:18263"


def test_run_poller_tick_failure_updates_state_and_writes_event(monkeypatch, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    upsert_poll_target(
        tmp_path,
        target_type="standings",
        target_key="18263",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
    )

    def fake_fetch_table(season_id, db_dir):
        raise RuntimeError("network down")

    monkeypatch.setattr("src.shl.poller.fetch_table", fake_fetch_table)

    results = run_poller_tick(tmp_path, now=now)

    assert len(results) == 1
    assert results[0]["status"] == "error"
    assert results[0]["error_count"] == 1
    assert "network down" in results[0]["error"]

    events = list_unprocessed_domain_events(tmp_path)
    assert len(events) == 1
    assert events[0]["event_type"] == "poll_failed"
    assert events[0]["aggregate_key"] == "standings:18263"


def test_domain_event_mark_processed(monkeypatch, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    upsert_poll_target(
        tmp_path,
        target_type="game",
        target_key="1004840",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
    )

    # Run a successful tick for game target.
    monkeypatch.setattr("src.shl.poller.fetch_game", lambda game_id, db_dir: None)
    run_poller_tick(tmp_path, now=now)

    events = list_unprocessed_domain_events(tmp_path)
    assert len(events) == 1

    mark_domain_event_processed(tmp_path, events[0]["id"], processed_at=_iso(now))
    remaining = list_unprocessed_domain_events(tmp_path)
    assert remaining == []


def test_run_poller_worker_runs_max_ticks(monkeypatch, tmp_path):
    calls = {"ticks": 0, "sleeps": 0}

    def fake_tick(cache_dir):
        calls["ticks"] += 1
        return [
            {"status": "ok"},
            {"status": "error"},
        ]

    def fake_sleep(seconds):
        calls["sleeps"] += 1

    monkeypatch.setattr("src.shl.poller.run_poller_tick", fake_tick)
    monkeypatch.setattr("src.shl.poller._sleep", fake_sleep)

    summary = run_poller_worker(tmp_path, tick_interval_seconds=0.01, max_ticks=3)

    assert summary == {"ticks": 3, "ok_results": 3, "error_results": 3}
    assert calls == {"ticks": 3, "sleeps": 2}


def test_run_poller_worker_validates_parameters(tmp_path):
    with pytest.raises(PollerError, match="tick_interval_seconds"):
        run_poller_worker(tmp_path, tick_interval_seconds=-1)

    with pytest.raises(PollerError, match="max_ticks"):
        run_poller_worker(tmp_path, max_ticks=0)
