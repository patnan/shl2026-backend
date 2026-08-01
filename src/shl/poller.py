from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from time import sleep as _sleep
from typing import Dict, List

from src.shl.game import fetch_game
from src.shl.schedule import fetch_schedule
from src.shl.standings import fetch_table
from src.shl.store import (
    insert_domain_event,
    list_due_poll_targets,
    update_poll_error,
    update_poll_success,
)


class PollerError(RuntimeError):
    pass


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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _compute_success_next_poll(target_type: str, now: datetime) -> str:
    interval = DEFAULT_SUCCESS_INTERVAL_SECONDS.get(target_type, 60)
    return _to_iso(now + timedelta(seconds=interval))


def _compute_error_next_poll(target_type: str, now: datetime, current_error_count: int) -> str:
    base = DEFAULT_ERROR_BASE_INTERVAL_SECONDS.get(target_type, 60)
    # Simple exponential backoff capped at x32.
    multiplier = 2 ** min(max(current_error_count, 0), 5)
    return _to_iso(now + timedelta(seconds=base * multiplier))


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
    due_targets = list_due_poll_targets(cache_dir, _to_iso(now_value))

    results: List[Dict] = []

    for target in due_targets:
        target_id = int(target["id"])
        target_type = str(target["target_type"])
        target_key = str(target["target_key"])
        error_count = int(target.get("error_count", 0) or 0)
        started = perf_counter()

        try:
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
            })
        except Exception as exc:
            duration_ms = int((perf_counter() - started) * 1000)
            next_poll_at = _compute_error_next_poll(target_type, now_value, error_count)
            new_error_count = update_poll_error(cache_dir, target_id, duration_ms, next_poll_at)
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
                "error": str(exc),
            })

    return results


def run_poller_worker(
    cache_dir: Path,
    tick_interval_seconds: float = 5.0,
    max_ticks: int | None = None,
) -> Dict[str, int]:
    if tick_interval_seconds < 0:
        raise PollerError("tick_interval_seconds must be >= 0")
    if max_ticks is not None and max_ticks <= 0:
        raise PollerError("max_ticks must be > 0 when provided")

    ticks = 0
    ok_results = 0
    error_results = 0

    while True:
        tick_results = run_poller_tick(cache_dir)
        ticks += 1

        for result in tick_results:
            if result.get("status") == "ok":
                ok_results += 1
            elif result.get("status") == "error":
                error_results += 1

        if max_ticks is not None and ticks >= max_ticks:
            break

        _sleep(tick_interval_seconds)

    return {
        "ticks": ticks,
        "ok_results": ok_results,
        "error_results": error_results,
    }
