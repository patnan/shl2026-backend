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
from src.shl.schedule import fetch_schedule
from src.shl.standings import fetch_table
from src.shl.models import PollTarget, ScheduleEntry
from src.shl.store import (
    insert_domain_event,
    list_due_poll_targets,
    load_schedule,
    upsert_poll_target,
    update_poll_error,
    update_poll_success,
)


class PollerError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


DEFAULT_SUCCESS_INTERVAL_SECONDS = {
    "game": 60,
    "schedule": 15 * 60,
    "standings": 5 * 60,
}

DEFAULT_ERROR_BASE_INTERVAL_SECONDS = {
    "game": 30,
    "schedule": 60,
    "standings": 60,
}

CIRCUIT_BREAKER_ERROR_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN_SECONDS = {
    "game": 5 * 60,
    "schedule": 20 * 60,
    "standings": 10 * 60,
}
BACKOFF_JITTER_RATIO = 0.15


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _compute_success_next_poll(target_type: str, now: datetime) -> str:
    interval = DEFAULT_SUCCESS_INTERVAL_SECONDS.get(target_type, 60)
    return _to_iso(now + timedelta(seconds=interval))


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


def _extract_game_ids_from_schedule_entries(entries: List[object]) -> List[int]:
    game_ids = set()
    for entry in entries:
        game_url = getattr(entry, "game_url", "")
        match = re.search(r"/(\d+)$", game_url)
        if match is None:
            continue
        game_ids.add(int(match.group(1)))
    return sorted(game_ids)


# Maximum duration (hours) a game can be considered active after its start time.
GAME_ACTIVE_WINDOW_HOURS = 4


def _find_schedule_entry_for_game(cache_dir: Path, game_id: int) -> Optional[ScheduleEntry]:
    """Look up the schedule entry for a game ID across all cached schedules."""
    from src.shl.store import Store
    store = Store(cache_dir)
    conn = store._get_conn()
    rows = conn.execute("SELECT data FROM schedule").fetchall()
    for row in rows:
        entries = [ScheduleEntry.from_dict(e) for e in json.loads(row[0])]
        for entry in entries:
            match = re.search(r"/(\d+)$", entry.game_url)
            if match and int(match.group(1)) == game_id:
                return entry
    return None


def _is_game_active(cache_dir: Path, game_id: int, now: datetime) -> tuple[bool, Optional[str]]:
    """Determine if a game should be actively polled right now.

    Returns:
        (should_poll, deferred_next_poll_at):
        - (True, None) if the game is currently active and should be polled.
        - (False, next_poll_at) if the game should be deferred until the given time.
    """
    entry = _find_schedule_entry_for_game(cache_dir, game_id)
    if entry is None:
        # No schedule info — poll it (first run before schedule is cached).
        return True, None

    # If the game already has a final result, defer it far into the future.
    if entry.game_result:
        deferred = _to_iso(now + timedelta(hours=24))
        return False, deferred

    # Parse game date and time.
    try:
        game_date = datetime.fromisoformat(entry.date).date() if entry.date else None
    except ValueError:
        game_date = None

    if game_date is None:
        return True, None

    # Parse start time (HH:MM format).
    game_start: Optional[datetime] = None
    if entry.time:
        try:
            hour, minute = entry.time.split(":")[:2]
            game_start = datetime(
                game_date.year, game_date.month, game_date.day,
                int(hour), int(minute), tzinfo=timezone.utc,
            )
        except (ValueError, IndexError):
            pass

    today = now.date()

    # Game is in the past (date before today) — defer.
    if game_date < today:
        deferred = _to_iso(now + timedelta(hours=24))
        return False, deferred

    # Game is in the future (date after today) — defer until game start.
    if game_date > today:
        if game_start:
            deferred = _to_iso(game_start - timedelta(minutes=5))
        else:
            deferred = _to_iso(datetime(game_date.year, game_date.month, game_date.day, tzinfo=timezone.utc))
        return False, deferred

    # Game is today — check if within the active window.
    if game_start:
        window_end = game_start + timedelta(hours=GAME_ACTIVE_WINDOW_HOURS)
        if now < game_start - timedelta(minutes=5):
            # Too early — defer until just before start.
            return False, _to_iso(game_start - timedelta(minutes=5))
        if now > window_end:
            # Game window passed — defer.
            return False, _to_iso(now + timedelta(hours=24))
        # Within active window — poll.
        return True, None

    # Today but no start time — poll it.
    return True, None


def seed_season_targets(
    cache_dir: Path,
    season_id: int,
    include_games: bool = True,
    force_reparse_schedule: bool = False,
) -> Dict[str, int]:
    now_iso = _to_iso(_now_utc())

    upsert_poll_target(
        cache_dir,
        target_type="schedule",
        target_key=str(season_id),
        enabled=True,
        next_poll_at=now_iso,
    )
    upsert_poll_target(
        cache_dir,
        target_type="standings",
        target_key=str(season_id),
        enabled=True,
        next_poll_at=now_iso,
    )

    game_targets_created = 0
    game_ids: List[int] = []

    if include_games:
        schedule_entries = fetch_schedule(
            season_id,
            cache_dir,
            force_reparse=force_reparse_schedule,
        )
        game_ids = _extract_game_ids_from_schedule_entries(schedule_entries)
        for game_id in game_ids:
            upsert_poll_target(
                cache_dir,
                target_type="game",
                target_key=str(game_id),
                enabled=True,
                next_poll_at=now_iso,
            )
        game_targets_created = len(game_ids)

    return {
        "season_id": season_id,
        "schedule_target": 1,
        "standings_target": 1,
        "game_targets": game_targets_created,
        "total_targets": 2 + game_targets_created,
    }


def _run_target(cache_dir: Path, target_type: str, target_key: str) -> None:
    if target_type == "game":
        fetch_game(int(target_key), cache_dir)
        return

    if target_type == "schedule":
        fetch_schedule(int(target_key), cache_dir)
        return

    if target_type == "standings":
        fetch_table(int(target_key), cache_dir)
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
            # Skip game targets that are not currently active.
            if target_type == "game":
                should_poll, deferred = _is_game_active(cache_dir, int(target_key), now_value)
                if not should_poll:
                    duration_ms = int((perf_counter() - started) * 1000)
                    update_poll_success(cache_dir, target_id, duration_ms, deferred)
                    results.append({
                        "target_id": target_id,
                        "target_type": target_type,
                        "target_key": target_key,
                        "status": "skipped",
                        "duration_ms": duration_ms,
                        "next_poll_at": deferred,
                        "due_age_seconds": due_age_seconds,
                    })
                    _log_result(results[-1])
                    continue

            _run_target(cache_dir, target_type, target_key)
            duration_ms = int((perf_counter() - started) * 1000)
            next_poll_at = _compute_success_next_poll(target_type, now_value)
            update_poll_success(cache_dir, target_id, duration_ms, next_poll_at)
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
