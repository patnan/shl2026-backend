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


def test_seed_season_targets_once_mode(tmp_path):
    from src.shl.poller import seed_season_targets

    result = seed_season_targets(tmp_path, season_id=18263, once=True)

    # once mode skips live_games
    assert result["one_shot"] == 1
    assert result["total_targets"] == 6
    assert "live_games_target" not in result
    assert result["schedule_target"] == 1

    targets = list_poll_targets(tmp_path)
    assert len(targets) == 6
    target_types = {t.target_type for t in targets}
    assert "live_games" not in target_types
    # All targets should be marked one_shot
    assert all(t.one_shot for t in targets)


def test_one_shot_target_disabled_after_success(monkeypatch, tmp_path):
    from src.shl.poller import run_poller_tick

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    upsert_poll_target(
        tmp_path,
        target_type="standings",
        target_key="18263",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
        one_shot=True,
    )

    monkeypatch.setattr("src.shl.poller.fetch_table", lambda season_id, db_dir: [])

    results = run_poller_tick(tmp_path, now=now)
    assert len(results) == 1
    assert results[0]["status"] == "ok"

    # Target should be disabled after success
    targets = list_poll_targets(tmp_path)
    assert len(targets) == 1
    assert targets[0].enabled is False
    assert targets[0].one_shot is True


def test_one_shot_target_not_disabled_on_error(monkeypatch, tmp_path):
    from src.shl.poller import run_poller_tick

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    upsert_poll_target(
        tmp_path,
        target_type="standings",
        target_key="18263",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
        one_shot=True,
    )

    def fake_fetch_table(season_id, db_dir):
        raise RuntimeError("network error")

    monkeypatch.setattr("src.shl.poller.fetch_table", fake_fetch_table)

    results = run_poller_tick(tmp_path, now=now)
    assert len(results) == 1
    assert results[0]["status"] == "error"

    # Target should still be enabled (will retry)
    targets = list_poll_targets(tmp_path)
    assert len(targets) == 1
    assert targets[0].enabled is True


def test_compute_error_next_poll_uses_circuit_breaker_cooldown(monkeypatch):
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr("src.shl.poller.random.randint", lambda low, high: high)

    # Error count at threshold should switch to the larger cooldown window.
    next_poll_at = _compute_error_next_poll("schedule", now, current_error_count=5)
    retry_seconds = int((datetime.fromisoformat(next_poll_at) - now).total_seconds())
    assert retry_seconds >= 20 * 60


def test_live_games_interval_active_during_game_window(monkeypatch, tmp_path):
    from src.shl.poller import _compute_live_games_interval, LIVE_GAMES_INTERVAL_ACTIVE
    from src.shl.models import ScheduleEntry
    from src.shl.store import save_schedule

    entries = [
        ScheduleEntry(date="2026-08-07", time="16:00", home_team="A", away_team="B",
                      game_result="", periods="", spectators="", venue="", game_url="", round=""),
        ScheduleEntry(date="2026-08-07", time="19:00", home_team="C", away_team="D",
                      game_result="", periods="", spectators="", venue="", game_url="", round=""),
    ]
    save_schedule(tmp_path, 21139, entries)

    # 17:00 is within window (15:45 to 22:00)
    now = datetime(2026, 8, 7, 17, 0, 0, tzinfo=timezone.utc)
    assert _compute_live_games_interval(tmp_path, 21139, now) == LIVE_GAMES_INTERVAL_ACTIVE


def test_live_games_interval_idle_outside_game_window(monkeypatch, tmp_path):
    from src.shl.poller import _compute_live_games_interval, LIVE_GAMES_INTERVAL_IDLE
    from src.shl.models import ScheduleEntry
    from src.shl.store import save_schedule

    entries = [
        ScheduleEntry(date="2026-08-07", time="16:00", home_team="A", away_team="B",
                      game_result="", periods="", spectators="", venue="", game_url="", round=""),
        ScheduleEntry(date="2026-08-07", time="19:00", home_team="C", away_team="D",
                      game_result="", periods="", spectators="", venue="", game_url="", round=""),
    ]
    save_schedule(tmp_path, 21139, entries)

    # 10:00 is before window (15:45)
    now = datetime(2026, 8, 7, 10, 0, 0, tzinfo=timezone.utc)
    assert _compute_live_games_interval(tmp_path, 21139, now) == LIVE_GAMES_INTERVAL_IDLE
    assert LIVE_GAMES_INTERVAL_IDLE == 120 * 60

    # 23:00 is after window (22:00)
    now = datetime(2026, 8, 7, 23, 0, 0, tzinfo=timezone.utc)
    assert _compute_live_games_interval(tmp_path, 21139, now) == LIVE_GAMES_INTERVAL_IDLE


def test_live_games_interval_idle_when_no_games_today(tmp_path):
    from src.shl.poller import _compute_live_games_interval, LIVE_GAMES_INTERVAL_IDLE
    from src.shl.models import ScheduleEntry
    from src.shl.store import save_schedule

    entries = [
        ScheduleEntry(date="2026-08-08", time="18:00", home_team="A", away_team="B",
                      game_result="", periods="", spectators="", venue="", game_url="", round=""),
    ]
    save_schedule(tmp_path, 21139, entries)

    now = datetime(2026, 8, 7, 17, 0, 0, tzinfo=timezone.utc)
    assert _compute_live_games_interval(tmp_path, 21139, now) == LIVE_GAMES_INTERVAL_IDLE


def test_live_games_poller_emits_game_state_changed_on_finish(monkeypatch, tmp_path):
    from src.shl.models import ScheduleEntry
    from src.shl.store import save_live_games

    now = datetime(2026, 8, 7, 18, 0, 0, tzinfo=timezone.utc)

    upsert_poll_target(
        tmp_path,
        target_type="live_games",
        target_key="21139",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
    )

    # Pre-populate with an in-progress game.
    prev_games = [
        ScheduleEntry(
            date="2026-08-07", time="16:00", home_team="Rögle BK", away_team="IF Malmö Redhawks",
            game_result="3 - 2", periods="(1-1, 2-1)", spectators="", venue="",
            game_url="https://stats.swehockey.se/Game/Events/1113947", round="",
            status="3rd period (05:00)", game_clock="05:00", current_period="3rd period",
        ),
    ]
    save_live_games(tmp_path, 21139, prev_games)

    # After fetch, the game is finished.
    new_games = [
        ScheduleEntry(
            date="2026-08-07", time="16:00", home_team="Rögle BK", away_team="IF Malmö Redhawks",
            game_result="4 - 2", periods="(1-1, 2-1, 1-0)", spectators="", venue="",
            game_url="https://stats.swehockey.se/Game/Events/1113947", round="",
            status="Game Finished", game_clock="", current_period="",
        ),
    ]

    def fake_fetch_live_games(season_id, cache_dir):
        save_live_games(cache_dir, season_id, new_games)
        return new_games, "2026-08-07 18:00:00"

    monkeypatch.setattr("src.shl.poller.fetch_live_games", fake_fetch_live_games)
    monkeypatch.setattr("src.shl.poller.get_live_standings", lambda season_id, cache_dir: [])
    monkeypatch.setattr("src.shl.poller.compare_live_standings", lambda prev, curr: [])

    results = run_poller_tick(tmp_path, now=now)
    assert len(results) == 1
    assert results[0]["status"] == "ok"

    events = list_unprocessed_domain_events(tmp_path)
    # Should have poll_completed + game_state_changed
    state_events = [e for e in events if e.event_type == "game_state_changed"]
    assert len(state_events) == 1
    payload = state_events[0].payload
    assert payload["game_id"] == 1113947
    assert payload["home_team"] == "Rögle BK"
    assert payload["away_team"] == "IF Malmö Redhawks"
    assert payload["score"] == "4 - 2"
    assert payload["current_state"] == "Game Finished"
    assert payload["previous_state"] == "3rd period (05:00)"


def test_live_games_poller_no_event_when_already_finished(monkeypatch, tmp_path):
    from src.shl.models import ScheduleEntry
    from src.shl.store import save_live_games

    now = datetime(2026, 8, 7, 19, 0, 0, tzinfo=timezone.utc)

    upsert_poll_target(
        tmp_path,
        target_type="live_games",
        target_key="21139",
        enabled=True,
        next_poll_at=_iso(now - timedelta(seconds=1)),
    )

    # Both previous and new state are finished — should not emit again.
    finished_game = ScheduleEntry(
        date="2026-08-07", time="16:00", home_team="Rögle BK", away_team="IF Malmö Redhawks",
        game_result="4 - 2", periods="(1-1, 2-1, 1-0)", spectators="", venue="",
        game_url="https://stats.swehockey.se/Game/Events/1113947", round="",
        status="Game Finished", game_clock="", current_period="",
    )
    save_live_games(tmp_path, 21139, [finished_game])

    def fake_fetch_live_games(season_id, cache_dir):
        # Status changes from "Game Finished" to "Final Score" (moves to final section)
        final_game = ScheduleEntry(
            date="2026-08-07", time="16:00", home_team="Rögle BK", away_team="IF Malmö Redhawks",
            game_result="4 - 2", periods="(1-1, 2-1, 1-0)", spectators="", venue="",
            game_url="https://stats.swehockey.se/Game/Events/1113947", round="",
            status="Final Score", game_clock="", current_period="",
        )
        save_live_games(cache_dir, season_id, [final_game])
        return [final_game], "2026-08-07 19:00:00"

    monkeypatch.setattr("src.shl.poller.fetch_live_games", fake_fetch_live_games)
    monkeypatch.setattr("src.shl.poller.get_live_standings", lambda season_id, cache_dir: [])
    monkeypatch.setattr("src.shl.poller.compare_live_standings", lambda prev, curr: [])

    results = run_poller_tick(tmp_path, now=now)
    assert results[0]["status"] == "ok"

    events = list_unprocessed_domain_events(tmp_path)
    state_events = [e for e in events if e.event_type == "game_state_changed"]
    # "Game Finished" -> "Final Score" should NOT emit again (both are finished)
    assert len(state_events) == 0
