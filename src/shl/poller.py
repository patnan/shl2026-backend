from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import random
import re
from time import perf_counter
from time import sleep as _sleep
from typing import Any, Dict, List, Optional

from src.shl.game import fetch_game
from src.shl.schedule import fetch_live_games, fetch_schedule, get_standings
from src.shl.standings import fetch_table
from src.shl.stats import fetch_goalie_stats, fetch_player_stats, fetch_rosters, fetch_team_info
from src.shl.models import PollTarget
from src.shl.store import (
    insert_domain_event,
    list_due_poll_targets,
    load_schedule,
    save_standings,
    upsert_poll_target,
    update_poll_error,
    update_poll_success,
)


class PollerError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


DEFAULT_SUCCESS_INTERVAL_SECONDS = {
    "game": 30,
    "schedule": 60,  # Default fallback, overridden dynamically.
    "standings": 5 * 60,
    "live_games": 30,              # Every 30 seconds.
    "player_stats": 2 * 60 * 60,  # Every 2 hours.
    "goalie_stats": 2 * 60 * 60,  # Every 2 hours.
    "rosters": 24 * 60 * 60,       # Every 24 hours.
    "team_info": 24 * 60 * 60,     # Every 24 hours.
}

# Dynamic schedule intervals based on game activity.
SCHEDULE_INTERVAL_LIVE_GAMES = 30          # Within active game window.
SCHEDULE_INTERVAL_GAME_DAY = 15 * 60      # Games today but outside active window.
SCHEDULE_INTERVAL_NO_GAMES = 2 * 60 * 60  # No games today at all.

DEFAULT_ERROR_BASE_INTERVAL_SECONDS = {
    "game": 30,
    "schedule": 60,
    "standings": 60,
    "live_games": 30,
    "player_stats": 5 * 60,
    "goalie_stats": 5 * 60,
    "rosters": 5 * 60,
    "team_info": 5 * 60,
}

CIRCUIT_BREAKER_ERROR_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN_SECONDS = {
    "game": 5 * 60,
    "schedule": 20 * 60,
    "standings": 10 * 60,
    "live_games": 5 * 60,
}
BACKOFF_JITTER_RATIO = 0.15


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _compute_success_next_poll(target_type: str, now: datetime, cache_dir: Optional[Path] = None, target_key: Optional[str] = None) -> str:
    if target_type == "schedule" and cache_dir is not None and target_key is not None:
        interval = _compute_schedule_interval(cache_dir, int(target_key), now)
    else:
        interval = DEFAULT_SUCCESS_INTERVAL_SECONDS.get(target_type, 60)
    return _to_iso(now + timedelta(seconds=interval))


def _compute_schedule_interval(cache_dir: Path, season_id: int, now: datetime) -> int:
    """Determine schedule polling interval based on current game activity.

    - No games today: every 2 hours.
    - Games today but outside active window: every 15 minutes.
    - Within active window (5 min before first game to 4h after last game starts): every 30 seconds.
    """
    schedule = load_schedule(cache_dir, season_id)
    if not schedule:
        return SCHEDULE_INTERVAL_NO_GAMES

    today_str = now.date().isoformat()
    todays_games = [e for e in schedule if e.date == today_str]

    if not todays_games:
        return SCHEDULE_INTERVAL_NO_GAMES

    # Parse start times for today's games.
    start_times: List[datetime] = []
    for entry in todays_games:
        if entry.time:
            try:
                hour, minute = entry.time.split(":")[:2]
                game_start = datetime(
                    now.year, now.month, now.day,
                    int(hour), int(minute), tzinfo=now.tzinfo,
                )
                start_times.append(game_start)
            except (ValueError, IndexError):
                pass

    if not start_times:
        # Games today but no parseable times — use game day interval.
        return SCHEDULE_INTERVAL_GAME_DAY

    first_start = min(start_times)
    last_start = max(start_times)

    # Active window: 5 min before first game to 4h after last game starts.
    window_begin = first_start - timedelta(minutes=5)
    window_end = last_start + timedelta(hours=4)

    if window_begin <= now <= window_end:
        return SCHEDULE_INTERVAL_LIVE_GAMES

    # Games today but outside active window.
    return SCHEDULE_INTERVAL_GAME_DAY


def _apply_jitter(interval_seconds: int, jitter_ratio: float = BACKOFF_JITTER_RATIO) -> int:
    if interval_seconds <= 0:
        return 0
    low = max(1, int(interval_seconds * (1.0 - jitter_ratio)))
    high = max(low, int(interval_seconds * (1.0 + jitter_ratio)))
    return random.randint(low, high)


def _compute_error_next_poll(target_type: str, now: datetime, current_error_count: int) -> str:
    base = DEFAULT_ERROR_BASE_INTERVAL_SECONDS.get(target_type, 60)
    cooldown = CIRCUIT_BREAKER_COOLDOWN_SECONDS.get(target_type, 10 * 60)
    # Simple exponential backoff capped at x32.
    multiplier = 2 ** min(max(current_error_count, 0), 5)
    backoff = base * multiplier
    if current_error_count >= CIRCUIT_BREAKER_ERROR_THRESHOLD:
        backoff = max(backoff, cooldown)
    return _to_iso(now + timedelta(seconds=_apply_jitter(backoff)))


def _seconds_until(now: datetime, next_poll_at: str) -> int:
    try:
        next_value = datetime.fromisoformat(next_poll_at)
    except ValueError:
        return 0
    delta = next_value - now
    return max(0, int(delta.total_seconds()))


def _due_age_seconds(now: datetime, next_poll_at: str) -> int:
    try:
        next_value = datetime.fromisoformat(next_poll_at)
    except ValueError:
        return 0
    if now <= next_value:
        return 0
    return int((now - next_value).total_seconds())


def _log_result(result: Dict) -> None:
    logger.info("poller_result %s", json.dumps(result, ensure_ascii=False, sort_keys=True))


def _summarize_tick(results: List[Dict], started: datetime, completed: datetime) -> Dict:
    total = len(results)
    ok = sum(1 for item in results if item.get("status") == "ok")
    errors = sum(1 for item in results if item.get("status") == "error")
    durations = [int(item.get("duration_ms", 0) or 0) for item in results]
    stale = sum(1 for item in results if int(item.get("due_age_seconds", 0) or 0) > 0)
    return {
        "tick_started_at": _to_iso(started),
        "tick_completed_at": _to_iso(completed),
        "due_targets": total,
        "ok_results": ok,
        "error_results": errors,
        "stale_targets": stale,
        "success_ratio": (ok / total) if total else 1.0,
        "avg_duration_ms": int(sum(durations) / total) if total else 0,
        "max_duration_ms": max(durations) if durations else 0,
    }




def seed_season_targets(
    cache_dir: Path,
    season_id: int,
    force_reparse_schedule: bool = False,
    once: bool = False,
) -> Dict[str, int]:
    """Seed poll targets for a season.

    Args:
        cache_dir: Path to the cache/database directory.
        season_id: SweHockey season/tournament ID.
        force_reparse_schedule: Force schedule refetch on next poll.
        once: If True, seed all targets except live_games as one_shot
              (disabled after first successful run). Useful for past seasons.
    """
    now_iso = _to_iso(_now_utc())

    # Targets to seed. Skip live_games in once mode (useless for past seasons).
    targets = ["schedule", "standings", "player_stats", "goalie_stats", "rosters", "team_info"]
    if not once:
        targets.append("live_games")

    for target_type in targets:
        upsert_poll_target(
            cache_dir,
            target_type=target_type,
            target_key=str(season_id),
            enabled=True,
            next_poll_at=now_iso,
            one_shot=once,
        )

    result: Dict[str, int] = {
        "season_id": season_id,
        "one_shot": 1 if once else 0,
    }
    for t in targets:
        result[f"{t}_target"] = 1
    result["total_targets"] = len(targets)
    return result


def _run_target(cache_dir: Path, target_type: str, target_key: str) -> None:
    if target_type == "game":
        # Game targets are now only fetched on-demand (triggered by schedule score change).
        # Direct polling just refreshes the game detail page.
        game_id = int(target_key)
        fetch_game(game_id, cache_dir, force_reparse=True)
        return

    if target_type == "schedule":
        season_id = int(target_key)

        # Load previous schedule and standings.
        prev_schedule = load_schedule(cache_dir, season_id) or []
        prev_standings = get_standings(season_id, cache_dir)

        # Build lookup of previous scores by game_url.
        prev_scores: Dict[str, str] = {}
        for entry in prev_schedule:
            if entry.game_url:
                prev_scores[entry.game_url] = entry.game_result

        # Fetch fresh schedule.
        fetch_schedule(season_id, cache_dir, force_reparse=True)
        new_schedule = load_schedule(cache_dir, season_id) or []

        # Detect per-game score changes and emit events.
        # Skip event emission on initial seed (no previous schedule) to avoid
        # flooding the notifier with hundreds of historical events.
        if not prev_schedule:
            logger.info(
                "initial_seed season=%d games_with_results=%d — skipping event emission",
                season_id,
                sum(1 for e in new_schedule if e.game_result),
            )
        else:
            changed_count = 0
            for entry in new_schedule:
                if not entry.game_url or not entry.game_result:
                    continue
                prev_result = prev_scores.get(entry.game_url, "")
                if entry.game_result != prev_result:
                    game_id_match = re.search(r"/(\d+)$", entry.game_url)
                    if game_id_match:
                        game_id = int(game_id_match.group(1))
                        insert_domain_event(
                            cache_dir,
                            "score_changed",
                            f"game:{game_id}",
                            {
                                "game_id": game_id,
                                "home_team": entry.home_team,
                                "away_team": entry.away_team,
                                "score": entry.game_result,
                                "previous_score": prev_result,
                                "overtime": entry.overtime,
                            },
                        )
                        # Fetch game detail page for period/clock/scorer info.
                        try:
                            fetch_game(game_id, cache_dir, force_reparse=True)
                        except Exception as exc:
                            logger.warning("Failed to fetch game detail for %d: %s", game_id, exc)
                        changed_count += 1

            if changed_count > 0:
                logger.info("schedule_changes season=%d changed_games=%d", season_id, changed_count)

        # Check standings changes.
        new_standings = get_standings(season_id, cache_dir)
        if prev_standings and new_standings and prev_standings != new_standings:
            insert_domain_event(
                cache_dir,
                "standings_changed",
                f"season:{target_key}",
                {
                    "season_id": season_id,
                    "standings": [
                        {
                            "rank": r.rank,
                            "team": r.team,
                            "games_played": r.games_played,
                            "tp": r.tp,
                        }
                        for r in new_standings
                    ],
                },
            )

        # Save standings snapshot for movement calculation on next tick.
        if new_standings:
            save_standings(cache_dir, season_id, new_standings)

        return

    if target_type == "standings":
        fetch_table(int(target_key), cache_dir)
        return

    if target_type == "player_stats":
        fetch_player_stats(int(target_key), cache_dir, force_reparse=True)
        return

    if target_type == "goalie_stats":
        fetch_goalie_stats(int(target_key), cache_dir, force_reparse=True)
        return

    if target_type == "rosters":
        fetch_rosters(int(target_key), cache_dir, force_reparse=True)
        return

    if target_type == "team_info":
        fetch_team_info(int(target_key), cache_dir, force_reparse=True)
        return

    if target_type == "live_games":
        fetch_live_games(int(target_key), cache_dir)
        return

    raise PollerError(f"Unsupported target_type '{target_type}'")


def run_poller_tick(cache_dir: Path, now: datetime | None = None) -> List[Dict]:
    now_value = now or _now_utc()
    tick_started = _now_utc()
    due_targets = list_due_poll_targets(cache_dir, _to_iso(now_value))

    results: List[Dict] = []

    for target in due_targets:
        target_id = target.id
        target_type = target.target_type
        target_key = target.target_key
        error_count = target.error_count
        due_age_seconds = 0
        if target.next_poll_at:
            due_age_seconds = _due_age_seconds(now_value, target.next_poll_at)
        started = perf_counter()

        try:
            _run_target(cache_dir, target_type, target_key)
            duration_ms = int((perf_counter() - started) * 1000)
            next_poll_at = _compute_success_next_poll(target_type, now_value, cache_dir, target_key)
            update_poll_success(cache_dir, target_id, duration_ms, next_poll_at)

            # Disable one_shot targets after successful execution.
            if target.one_shot:
                upsert_poll_target(cache_dir, target_type=target_type, target_key=target_key, enabled=False, one_shot=True)
                logger.info("one_shot_disabled target_id=%d type=%s key=%s", target_id, target_type, target_key)

            insert_domain_event(
                cache_dir,
                "poll_completed",
                f"{target_type}:{target_key}",
                {
                    "target_id": target_id,
                    "target_type": target_type,
                    "target_key": target_key,
                    "duration_ms": duration_ms,
                    "next_poll_at": next_poll_at,
                },
            )
            results.append({
                "target_id": target_id,
                "target_type": target_type,
                "target_key": target_key,
                "status": "ok",
                "duration_ms": duration_ms,
                "next_poll_at": next_poll_at,
                "due_age_seconds": due_age_seconds,
            })
        except Exception as exc:
            duration_ms = int((perf_counter() - started) * 1000)
            next_poll_at = _compute_error_next_poll(target_type, now_value, error_count)
            new_error_count = update_poll_error(cache_dir, target_id, duration_ms, next_poll_at)
            retry_in_seconds = _seconds_until(now_value, next_poll_at)
            recovery_mode = "circuit_open" if new_error_count >= CIRCUIT_BREAKER_ERROR_THRESHOLD else "backoff"
            insert_domain_event(
                cache_dir,
                "poll_failed",
                f"{target_type}:{target_key}",
                {
                    "target_id": target_id,
                    "target_type": target_type,
                    "target_key": target_key,
                    "duration_ms": duration_ms,
                    "next_poll_at": next_poll_at,
                    "error_count": new_error_count,
                    "retry_in_seconds": retry_in_seconds,
                    "recovery_mode": recovery_mode,
                    "error": str(exc),
                },
            )
            results.append({
                "target_id": target_id,
                "target_type": target_type,
                "target_key": target_key,
                "status": "error",
                "duration_ms": duration_ms,
                "next_poll_at": next_poll_at,
                "error_count": new_error_count,
                "retry_in_seconds": retry_in_seconds,
                "recovery_mode": recovery_mode,
                "due_age_seconds": due_age_seconds,
                "error": str(exc),
            })

        _log_result(results[-1])

    tick_summary = _summarize_tick(results, tick_started, _now_utc())
    logger.info("poller_tick_summary %s", json.dumps(tick_summary, ensure_ascii=False, sort_keys=True))

    return results


def run_poller_worker(
    cache_dir: Path,
    tick_interval_seconds: float = 5.0,
    max_ticks: int | None = None,
) -> Dict[str, Any]:
    if tick_interval_seconds < 0:
        raise PollerError("tick_interval_seconds must be >= 0")
    if max_ticks is not None and max_ticks <= 0:
        raise PollerError("max_ticks must be > 0 when provided")

    ticks = 0
    ok_results = 0
    error_results = 0
    stale_targets = 0
    total_duration_ms = 0
    max_duration_ms = 0
    worker_started = _now_utc()

    while True:
        tick_results = run_poller_tick(cache_dir)
        ticks += 1

        for result in tick_results:
            if result.get("status") == "ok":
                ok_results += 1
            elif result.get("status") == "error":
                error_results += 1
            duration_ms = int(result.get("duration_ms", 0) or 0)
            total_duration_ms += duration_ms
            max_duration_ms = max(max_duration_ms, duration_ms)
            if int(result.get("due_age_seconds", 0) or 0) > 0:
                stale_targets += 1

        if max_ticks is not None and ticks >= max_ticks:
            break

        _sleep(tick_interval_seconds)

    worker_summary = {
        "ticks": ticks,
        "ok_results": ok_results,
        "error_results": error_results,
        "stale_targets": stale_targets,
        "total_results": ok_results + error_results,
        "avg_duration_ms": int(total_duration_ms / (ok_results + error_results)) if (ok_results + error_results) else 0,
        "max_duration_ms": max_duration_ms,
        "worker_started_at": _to_iso(worker_started),
        "worker_completed_at": _to_iso(_now_utc()),
    }
    logger.info("poller_worker_summary %s", json.dumps(worker_summary, ensure_ascii=False, sort_keys=True))
    return worker_summary
