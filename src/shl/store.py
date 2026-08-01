import dataclasses
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.shl.models import Game, ScheduleEntry, StandingsRow


def cache_db_path(cache_dir: Path) -> Path:
    return cache_dir / "cache.db"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(cache_dir: Path) -> sqlite3.Connection:
    db_path = cache_db_path(cache_dir)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL,
            fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS standings (
            season_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL,
            fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            season_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL,
            fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Phase 1 Step 1: poller control schema.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS poll_targets (
            id INTEGER PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_key TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(target_type, target_key)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS poll_state (
            target_id INTEGER PRIMARY KEY,
            last_success_at TEXT,
            last_error_at TEXT,
            error_count INTEGER NOT NULL DEFAULT 0,
            next_poll_at TEXT,
            last_duration_ms INTEGER,
            FOREIGN KEY(target_id) REFERENCES poll_targets(id) ON DELETE CASCADE
        )
    """)

    # Phase 1 Step 1: outbox/event schema.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS domain_events (
            id INTEGER PRIMARY KEY,
            event_type TEXT NOT NULL,
            aggregate_key TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            processed_at TEXT
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_poll_targets_enabled ON poll_targets(enabled)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_poll_state_next_poll_at ON poll_state(next_poll_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_events_processed_at ON domain_events(processed_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_events_created_at ON domain_events(created_at)")
    conn.commit()
    return conn


def load_game(cache_dir: Path, game_id: int) -> Optional[Game]:
    with _connect(cache_dir) as conn:
        row = conn.execute("SELECT data FROM games WHERE game_id = ?", (game_id,)).fetchone()
    return Game.from_dict(json.loads(row[0])) if row else None


def save_game(cache_dir: Path, game_id: int, game: Game) -> None:
    with _connect(cache_dir) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO games (game_id, data, fetched_at) VALUES (?, ?, datetime('now'))",
            (game_id, json.dumps(dataclasses.asdict(game), ensure_ascii=False)),
        )


def load_standings(cache_dir: Path, season_id: int) -> Optional[List[StandingsRow]]:
    with _connect(cache_dir) as conn:
        row = conn.execute("SELECT data FROM standings WHERE season_id = ?", (season_id,)).fetchone()
    return [StandingsRow.from_dict(e) for e in json.loads(row[0])] if row else None


def save_standings(cache_dir: Path, season_id: int, standings: List[StandingsRow]) -> None:
    with _connect(cache_dir) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO standings (season_id, data, fetched_at) VALUES (?, ?, datetime('now'))",
            (season_id, json.dumps([dataclasses.asdict(s) for s in standings], ensure_ascii=False)),
        )


def load_schedule(cache_dir: Path, season_id: int) -> Optional[List[ScheduleEntry]]:
    with _connect(cache_dir) as conn:
        row = conn.execute("SELECT data FROM schedule WHERE season_id = ?", (season_id,)).fetchone()
    return [ScheduleEntry.from_dict(e) for e in json.loads(row[0])] if row else None


def save_schedule(cache_dir: Path, season_id: int, schedule: List[ScheduleEntry]) -> None:
    with _connect(cache_dir) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO schedule (season_id, data, fetched_at) VALUES (?, ?, datetime('now'))",
            (season_id, json.dumps([dataclasses.asdict(e) for e in schedule], ensure_ascii=False)),
        )


def upsert_poll_target(
    cache_dir: Path,
    target_type: str,
    target_key: str,
    enabled: bool = True,
    next_poll_at: Optional[str] = None,
) -> int:
    now = _utc_now_iso()
    with _connect(cache_dir) as conn:
        row = conn.execute(
            "SELECT id FROM poll_targets WHERE target_type = ? AND target_key = ?",
            (target_type, target_key),
        ).fetchone()

        if row is None:
            conn.execute(
                """
                INSERT INTO poll_targets (target_type, target_key, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (target_type, target_key, 1 if enabled else 0, now, now),
            )
            target_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            conn.execute(
                """
                INSERT OR REPLACE INTO poll_state (target_id, next_poll_at)
                VALUES (?, ?)
                """,
                (target_id, next_poll_at or now),
            )
            return target_id

        target_id = int(row[0])
        conn.execute(
            "UPDATE poll_targets SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, now, target_id),
        )
        if next_poll_at is not None:
            conn.execute(
                """
                INSERT INTO poll_state (target_id, next_poll_at)
                VALUES (?, ?)
                ON CONFLICT(target_id) DO UPDATE SET next_poll_at = excluded.next_poll_at
                """,
                (target_id, next_poll_at),
            )
        return target_id


def list_due_poll_targets(cache_dir: Path, now_iso: Optional[str] = None) -> List[Dict[str, Any]]:
    now_value = now_iso or _utc_now_iso()
    with _connect(cache_dir) as conn:
        rows = conn.execute(
            """
            SELECT
                t.id,
                t.target_type,
                t.target_key,
                t.enabled,
                s.last_success_at,
                s.last_error_at,
                s.error_count,
                s.next_poll_at,
                s.last_duration_ms
            FROM poll_targets t
            LEFT JOIN poll_state s ON s.target_id = t.id
            WHERE t.enabled = 1
              AND (s.next_poll_at IS NULL OR s.next_poll_at <= ?)
            ORDER BY COALESCE(s.next_poll_at, ''), t.id
            """,
            (now_value,),
        ).fetchall()

    result: List[Dict[str, Any]] = []
    for row in rows:
        result.append({
            "id": int(row[0]),
            "target_type": row[1],
            "target_key": row[2],
            "enabled": bool(row[3]),
            "last_success_at": row[4],
            "last_error_at": row[5],
            "error_count": int(row[6] or 0),
            "next_poll_at": row[7],
            "last_duration_ms": row[8],
        })
    return result


def update_poll_success(cache_dir: Path, target_id: int, duration_ms: int, next_poll_at: str) -> None:
    now = _utc_now_iso()
    with _connect(cache_dir) as conn:
        conn.execute(
            """
            INSERT INTO poll_state (target_id, last_success_at, last_error_at, error_count, next_poll_at, last_duration_ms)
            VALUES (?, ?, NULL, 0, ?, ?)
            ON CONFLICT(target_id) DO UPDATE SET
                last_success_at = excluded.last_success_at,
                last_error_at = excluded.last_error_at,
                error_count = excluded.error_count,
                next_poll_at = excluded.next_poll_at,
                last_duration_ms = excluded.last_duration_ms
            """,
            (target_id, now, next_poll_at, duration_ms),
        )


def update_poll_error(cache_dir: Path, target_id: int, duration_ms: int, next_poll_at: str) -> int:
    now = _utc_now_iso()
    with _connect(cache_dir) as conn:
        row = conn.execute("SELECT error_count FROM poll_state WHERE target_id = ?", (target_id,)).fetchone()
        previous_error_count = int(row[0]) if row and row[0] is not None else 0
        new_error_count = previous_error_count + 1
        conn.execute(
            """
            INSERT INTO poll_state (target_id, last_error_at, error_count, next_poll_at, last_duration_ms)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(target_id) DO UPDATE SET
                last_error_at = excluded.last_error_at,
                error_count = excluded.error_count,
                next_poll_at = excluded.next_poll_at,
                last_duration_ms = excluded.last_duration_ms
            """,
            (target_id, now, new_error_count, next_poll_at, duration_ms),
        )
    return new_error_count


def insert_domain_event(cache_dir: Path, event_type: str, aggregate_key: str, payload: Dict[str, Any]) -> int:
    with _connect(cache_dir) as conn:
        conn.execute(
            "INSERT INTO domain_events (event_type, aggregate_key, payload_json) VALUES (?, ?, ?)",
            (event_type, aggregate_key, json.dumps(payload, ensure_ascii=False)),
        )
        return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def list_unprocessed_domain_events(cache_dir: Path, limit: int = 100) -> List[Dict[str, Any]]:
    with _connect(cache_dir) as conn:
        rows = conn.execute(
            """
            SELECT id, event_type, aggregate_key, payload_json, created_at, processed_at
            FROM domain_events
            WHERE processed_at IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    events: List[Dict[str, Any]] = []
    for row in rows:
        events.append({
            "id": int(row[0]),
            "event_type": row[1],
            "aggregate_key": row[2],
            "payload": json.loads(row[3]),
            "created_at": row[4],
            "processed_at": row[5],
        })
    return events


def mark_domain_event_processed(cache_dir: Path, event_id: int, processed_at: Optional[str] = None) -> None:
    with _connect(cache_dir) as conn:
        conn.execute(
            "UPDATE domain_events SET processed_at = ? WHERE id = ?",
            (processed_at or _utc_now_iso(), event_id),
        )
