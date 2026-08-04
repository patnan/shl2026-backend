from datetime import datetime, timedelta, timezone

from src.shl.poller import run_poller_tick, seed_season_targets
from src.shl.store import (
    list_due_poll_targets,
    list_poll_targets,
    list_unprocessed_domain_events,
    upsert_poll_target,
)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def test_seed_then_tick_updates_poll_state_and_writes_completed_events(monkeypatch, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Seed schedule + standings targets without requiring schedule fetch.
    seed_result = seed_season_targets(tmp_path, season_id=18263)
    assert seed_result["total_targets"] == 2

    # Seed uses real current time; force deterministic due-state for this test timestamp.
    upsert_poll_target(
        tmp_path,
        target_type="schedule",
        target_key="18263",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=30)),
    )
    upsert_poll_target(
        tmp_path,
        target_type="standings",
        target_key="18263",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=30)),
    )

    monkeypatch.setattr("src.shl.poller.fetch_schedule", lambda season_id, cache_dir, **kwargs: [])
    monkeypatch.setattr("src.shl.poller.fetch_table", lambda season_id, cache_dir: [])

    due_before = list_due_poll_targets(tmp_path, now_iso=_iso(now))
    assert len(due_before) == 2
    assert {item.target_type for item in due_before} == {"schedule", "standings"}

    tick_results = run_poller_tick(tmp_path, now=now)
    assert len(tick_results) == 2
    assert {item["status"] for item in tick_results} == {"ok"}

    # Targets should no longer be due at the same instant after a successful tick.
    due_after = list_due_poll_targets(tmp_path, now_iso=_iso(now))
    assert due_after == []

    targets = list_poll_targets(tmp_path)
    assert len(targets) == 2
    for target in targets:
        assert target.error_count == 0
        assert target.last_success_at is not None
        assert target.next_poll_at is not None

    events = list_unprocessed_domain_events(tmp_path)
    assert len(events) == 2
    assert {event.event_type for event in events} == {"poll_completed"}


def test_failed_tick_updates_error_state_and_writes_failed_event(monkeypatch, tmp_path):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    upsert_poll_target(
        tmp_path,
        target_type="game",
        target_key="1004308",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=30)),
    )

    def fail_fetch_game(game_id, cache_dir):
        raise RuntimeError("upstream timeout")

    monkeypatch.setattr("src.shl.poller.fetch_game", fail_fetch_game)

    tick_results = run_poller_tick(tmp_path, now=now)
    assert len(tick_results) == 1

    result = tick_results[0]
    assert result["status"] == "error"
    assert result["target_type"] == "game"
    assert result["error_count"] == 1
    assert result["retry_in_seconds"] > 0
    assert result["recovery_mode"] == "backoff"
    assert result["due_age_seconds"] >= 30

    targets = list_poll_targets(tmp_path)
    assert len(targets) == 1
    assert targets[0].error_count == 1
    assert targets[0].last_error_at is not None

    events = list_unprocessed_domain_events(tmp_path)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "poll_failed"
    assert event.aggregate_key == "game:1004308"
    assert event.payload["recovery_mode"] == "backoff"
    assert event.payload["error_count"] == 1
