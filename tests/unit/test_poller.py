from datetime import datetime, timedelta, timezone

import pytest

from src.shl.poller import PollerError, _compute_error_next_poll, run_poller_tick, run_poller_worker
from src.shl.store import (
    list_due_poll_targets,
    list_poll_targets,
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
    assert [item.id for item in due] == [due_id]
    assert due[0].target_type == "schedule"
    assert due[0].target_key == "18263"


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

    def fake_fetch_schedule(season_id, db_dir, force_reparse=False):
        calls["fetch_schedule"] += 1
        assert season_id == 18263
        assert db_dir == tmp_path

    monkeypatch.setattr("src.shl.poller.fetch_schedule", fake_fetch_schedule)
    monkeypatch.setattr("src.shl.poller.get_standings", lambda season_id, cache_dir: [])

    results = run_poller_tick(tmp_path, now=now)

    assert len(results) == 1
    assert results[0]["status"] == "ok"
    assert calls["fetch_schedule"] == 1

    # The same target should no longer be due immediately after success.
    due_after = list_due_poll_targets(tmp_path, now_iso=_iso(now))
    assert due_after == []

    events = list_unprocessed_domain_events(tmp_path)
    assert len(events) == 1
    assert events[0].event_type == "poll_completed"
    assert events[0].aggregate_key == "schedule:18263"


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
    assert results[0]["recovery_mode"] == "backoff"
    assert results[0]["retry_in_seconds"] > 0
    assert "network down" in results[0]["error"]

    events = list_unprocessed_domain_events(tmp_path)
    assert len(events) == 1
    assert events[0].event_type == "poll_failed"
    assert events[0].aggregate_key == "standings:18263"


def test_domain_event_mark_processed(monkeypatch, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    upsert_poll_target(
        tmp_path,
        target_type="schedule",
        target_key="18263",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
    )

    # Run a successful tick for schedule target.
    monkeypatch.setattr("src.shl.poller.fetch_schedule", lambda season_id, db_dir, force_reparse=False: None)
    monkeypatch.setattr("src.shl.poller.get_standings", lambda season_id, cache_dir: [])
    monkeypatch.setattr("src.shl.poller.load_schedule", lambda cache_dir, season_id: [])
    run_poller_tick(tmp_path, now=now)

    events = list_unprocessed_domain_events(tmp_path)
    assert len(events) == 1

    mark_domain_event_processed(tmp_path, events[0].id, processed_at=_iso(now))
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

    assert summary["ticks"] == 3
    assert summary["ok_results"] == 3
    assert summary["error_results"] == 3
    assert summary["total_results"] == 6
    assert "worker_started_at" in summary
    assert "worker_completed_at" in summary
    assert calls == {"ticks": 3, "sleeps": 2}


def test_run_poller_worker_validates_parameters(tmp_path):
    with pytest.raises(PollerError, match="tick_interval_seconds"):
        run_poller_worker(tmp_path, tick_interval_seconds=-1)

    with pytest.raises(PollerError, match="max_ticks"):
        run_poller_worker(tmp_path, max_ticks=0)


def test_seed_season_targets_creates_schedule_and_standings(monkeypatch, tmp_path):
    from src.shl.poller import seed_season_targets

    result = seed_season_targets(tmp_path, season_id=18263)

    assert result["schedule_target"] == 1
    assert result["standings_target"] == 1
    assert result["player_stats_target"] == 1
    assert result["goalie_stats_target"] == 1
    assert result["rosters_target"] == 1
    assert result["team_info_target"] == 1
    assert result["live_games_target"] == 1
    assert result["total_targets"] == 7

    targets = list_poll_targets(tmp_path)
    assert len(targets) == 7
    assert {(t.target_type, t.target_key) for t in targets} == {
        ("schedule", "18263"),
        ("standings", "18263"),
        ("player_stats", "18263"),
        ("goalie_stats", "18263"),
        ("rosters", "18263"),
        ("team_info", "18263"),
        ("live_games", "18263"),
    }


def test_compute_error_next_poll_uses_circuit_breaker_cooldown(monkeypatch):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr("src.shl.poller.random.randint", lambda low, high: high)

    # Error count at threshold should switch to the larger cooldown window.
    next_poll_at = _compute_error_next_poll("schedule", now, current_error_count=5)
    retry_seconds = int((datetime.fromisoformat(next_poll_at) - now).total_seconds())
    assert retry_seconds >= 20 * 60
