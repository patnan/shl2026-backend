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
        target_type="game",
        target_key="1004840",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
    )

    # Run a successful tick for game target.
    monkeypatch.setattr("src.shl.poller.fetch_game", lambda game_id, db_dir, force_reparse=False: None)
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


def test_seed_season_targets_creates_schedule_standings_and_game_targets(monkeypatch, tmp_path):
    from src.shl.models import ScheduleEntry
    from src.shl.poller import seed_season_targets

    monkeypatch.setattr(
        "src.shl.poller.fetch_schedule",
        lambda season_id, cache_dir, force_reparse=False: [
            ScheduleEntry(
                date="2025-09-16",
                time="19:00",
                game_result="",
                spectators="",
                venue="",
                game_url="https://stats.swehockey.se/Game/Events/1004308",
                round="1",
            ),
            ScheduleEntry(
                date="2025-09-16",
                time="19:00",
                game_result="",
                spectators="",
                venue="",
                game_url="https://stats.swehockey.se/Game/Events/1004308",
                round="1",
            ),
            ScheduleEntry(
                date="2025-09-16",
                time="19:00",
                game_result="",
                spectators="",
                venue="",
                game_url="https://stats.swehockey.se/Game/Events/1004309",
                round="1",
            ),
        ],
    )

    result = seed_season_targets(tmp_path, season_id=18263, include_games=True)

    assert result["schedule_target"] == 1
    assert result["standings_target"] == 1
    assert result["game_targets"] == 2
    assert result["total_targets"] == 4

    targets = list_poll_targets(tmp_path)
    assert len(targets) == 4
    assert {(t.target_type, t.target_key) for t in targets} == {
        ("schedule", "18263"),
        ("standings", "18263"),
        ("game", "1004308"),
        ("game", "1004309"),
    }


def test_seed_season_targets_can_skip_game_targets(monkeypatch, tmp_path):
    from src.shl.poller import seed_season_targets

    monkeypatch.setattr("src.shl.poller.fetch_schedule", lambda *args, **kwargs: pytest.fail("fetch_schedule should not be called"))

    result = seed_season_targets(tmp_path, season_id=18263, include_games=False)
    assert result["game_targets"] == 0
    assert result["total_targets"] == 2

    targets = list_poll_targets(tmp_path)
    assert {(t.target_type, t.target_key) for t in targets} == {
        ("schedule", "18263"),
        ("standings", "18263"),
    }


def test_compute_error_next_poll_uses_circuit_breaker_cooldown(monkeypatch):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr("src.shl.poller.random.randint", lambda low, high: high)

    # Error count at threshold should switch to the larger cooldown window.
    next_poll_at = _compute_error_next_poll("schedule", now, current_error_count=5)
    retry_seconds = int((datetime.fromisoformat(next_poll_at) - now).total_seconds())
    assert retry_seconds >= 20 * 60


def test_game_target_skipped_when_not_active(monkeypatch, tmp_path):
    """Game targets are skipped (deferred) when the game is not currently active."""
    from src.shl.store import save_schedule
    from src.shl.models import ScheduleEntry

    now = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)

    # Save a schedule with a game that was yesterday (already finished).
    save_schedule(tmp_path, 18263, [
        ScheduleEntry(
            date="2026-09-15",
            time="19:00",
            game_result="3 - 2",
            spectators="8000",
            venue="Arena",
            game_url="https://stats.swehockey.se/Game/Events/1004308",
            round="1",
        ),
    ])

    # Seed the game target.
    upsert_poll_target(
        tmp_path,
        target_type="game",
        target_key="1004308",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
    )

    # fetch_game should NOT be called.
    monkeypatch.setattr("src.shl.poller.fetch_game", lambda *a, **kw: pytest.fail("fetch_game should not be called"))

    results = run_poller_tick(tmp_path, now=now)
    assert len(results) == 1
    assert results[0]["status"] == "skipped"
    assert results[0]["target_key"] == "1004308"


def test_game_target_polled_when_active(monkeypatch, tmp_path):
    """Game targets are polled when the game is currently in progress."""
    from src.shl.store import save_schedule
    from src.shl.models import ScheduleEntry

    # Game starts at 19:00 today, now is 20:00 (within active window).
    now = datetime(2026, 9, 16, 20, 0, 0, tzinfo=timezone.utc)

    save_schedule(tmp_path, 18263, [
        ScheduleEntry(
            date="2026-09-16",
            time="19:00",
            game_result="",
            spectators="",
            venue="Arena",
            game_url="https://stats.swehockey.se/Game/Events/1004308",
            round="1",
        ),
    ])

    upsert_poll_target(
        tmp_path,
        target_type="game",
        target_key="1004308",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
    )

    calls = {"fetch_game": 0}

    def fake_fetch_game(game_id, db_dir, force_reparse=False):
        calls["fetch_game"] += 1

    monkeypatch.setattr("src.shl.poller.fetch_game", fake_fetch_game)

    results = run_poller_tick(tmp_path, now=now)
    assert len(results) == 1
    assert results[0]["status"] == "ok"
    assert calls["fetch_game"] == 1


def test_game_target_deferred_when_future(monkeypatch, tmp_path):
    """Game targets scheduled for tomorrow are deferred until near game start."""
    from src.shl.store import save_schedule
    from src.shl.models import ScheduleEntry

    now = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)

    save_schedule(tmp_path, 18263, [
        ScheduleEntry(
            date="2026-09-16",
            time="19:00",
            game_result="",
            spectators="",
            venue="Arena",
            game_url="https://stats.swehockey.se/Game/Events/1004308",
            round="1",
        ),
    ])

    upsert_poll_target(
        tmp_path,
        target_type="game",
        target_key="1004308",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
    )

    monkeypatch.setattr("src.shl.poller.fetch_game", lambda *a, **kw: pytest.fail("fetch_game should not be called"))

    results = run_poller_tick(tmp_path, now=now)
    assert len(results) == 1
    assert results[0]["status"] == "skipped"
    # Should be deferred to near the game start time (2026-09-16T18:55).
    deferred = datetime.fromisoformat(results[0]["next_poll_at"])
    assert deferred.date() == datetime(2026, 9, 16).date()
