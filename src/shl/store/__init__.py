import dataclasses
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from src.shl.models import (
    DomainEvent,
    Game,
    GoalieStat,
    PlayerStat,
    PollTarget,
    RosterEntry,
    ScheduleEntry,
    StandingsRow,
    TeamInfo,
    TeamPlayerStat,
)

_logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS games (
    game_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS standings (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS schedule (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS poll_targets (
    id INTEGER PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_key TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    one_shot INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(target_type, target_key)
);
CREATE TABLE IF NOT EXISTS poll_state (
    target_id INTEGER PRIMARY KEY,
    last_success_at TEXT,
    last_error_at TEXT,
    error_count INTEGER NOT NULL DEFAULT 0,
    next_poll_at TEXT,
    last_duration_ms INTEGER,
    FOREIGN KEY(target_id) REFERENCES poll_targets(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS domain_events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed_at TEXT
);
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY,
    fcm_token TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL DEFAULT 'android',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_poll_targets_enabled ON poll_targets(enabled);
CREATE INDEX IF NOT EXISTS idx_poll_state_next_poll_at ON poll_state(next_poll_at);
CREATE INDEX IF NOT EXISTS idx_domain_events_processed_at ON domain_events(processed_at);
CREATE INDEX IF NOT EXISTS idx_domain_events_created_at ON domain_events(created_at);
CREATE INDEX IF NOT EXISTS idx_devices_fcm_token ON devices(fcm_token);
CREATE TABLE IF NOT EXISTS player_stats (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS goalie_stats (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS rosters (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS team_info (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS team_player_stats (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS shl_se_players (
    season_id INTEGER NOT NULL,
    team TEXT NOT NULL,
    jersey INTEGER NOT NULL,
    data TEXT NOT NULL,
    portrait_path TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (season_id, team, jersey)
);
CREATE TABLE IF NOT EXISTS live_games (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """Thread-safe SQLite store with WAL mode and single schema initialization."""

    def __init__(self, cache_dir: Path) -> None:
        self._db_path = cache_dir / "cache.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        # Initialize schema once on the creating thread's connection.
        conn = self._get_conn()
        conn.executescript(_SCHEMA_SQL)
        self._run_migrations(conn)

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """Add missing columns to existing tables (idempotent)."""
        migrations = [
            ("poll_targets", "one_shot", "INTEGER NOT NULL DEFAULT 0"),
            ("live_games", "page_last_update", "TEXT"),
            ("schedule", "page_last_update", "TEXT"),
        ]
        for table, column, col_def in migrations:
            cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
                _logger.info("Migrated: added %s.%s", table, column)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Return a per-thread connection (created lazily)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    # ------------------------------------------------------------------
    # Games
    # ------------------------------------------------------------------

    def load_game(self, game_id: int) -> Optional[Game]:
        row = self._get_conn().execute(
            "SELECT data FROM games WHERE game_id = ?", (game_id,)
        ).fetchone()
        return Game.from_dict(json.loads(row[0])) if row else None

    def load_games_batch(self, game_ids: List[int]) -> List[Game]:
        if not game_ids:
            return []
        placeholders = ",".join("?" for _ in game_ids)
        rows = self._get_conn().execute(
            f"SELECT data FROM games WHERE game_id IN ({placeholders})",
            tuple(game_ids),
        ).fetchall()
        return [Game.from_dict(json.loads(row[0])) for row in rows]

    def get_game_fetched_at(self, game_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT fetched_at FROM games WHERE game_id = ?", (game_id,)
        ).fetchone()
        return row[0] if row else None

    def save_game(self, game_id: int, game: Game) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO games (game_id, data, fetched_at) VALUES (?, ?, ?)",
            (game_id, json.dumps(dataclasses.asdict(game), ensure_ascii=False), _utc_now_iso()),
        )
        conn.commit()

    def get_games_freshness(self, game_ids: List[int]) -> dict:
        if not game_ids:
            return {
                "requested_game_count": 0,
                "cached_game_count": 0,
                "latest_fetched_at": None,
                "oldest_fetched_at": None,
            }
        placeholders = ",".join("?" for _ in game_ids)
        row = self._get_conn().execute(
            f"SELECT COUNT(*), MAX(fetched_at), MIN(fetched_at) FROM games WHERE game_id IN ({placeholders})",
            tuple(game_ids),
        ).fetchone()
        return {
            "requested_game_count": len(game_ids),
            "cached_game_count": int(row[0] or 0),
            "latest_fetched_at": row[1],
            "oldest_fetched_at": row[2],
        }

    # ------------------------------------------------------------------
    # Standings
    # ------------------------------------------------------------------

    def load_standings(self, season_id: int) -> Optional[List[StandingsRow]]:
        row = self._get_conn().execute(
            "SELECT data FROM standings WHERE season_id = ?", (season_id,)
        ).fetchone()
        return [StandingsRow.from_dict(e) for e in json.loads(row[0])] if row else None

    def get_standings_fetched_at(self, season_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT fetched_at FROM standings WHERE season_id = ?", (season_id,)
        ).fetchone()
        return row[0] if row else None

    def save_standings(self, season_id: int, standings: List[StandingsRow]) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO standings (season_id, data, fetched_at) VALUES (?, ?, ?)",
            (season_id, json.dumps([dataclasses.asdict(s) for s in standings], ensure_ascii=False), _utc_now_iso()),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------------

    def load_schedule(self, season_id: int) -> Optional[List[ScheduleEntry]]:
        row = self._get_conn().execute(
            "SELECT data FROM schedule WHERE season_id = ?", (season_id,)
        ).fetchone()
        return [ScheduleEntry.from_dict(e) for e in json.loads(row[0])] if row else None

    def get_schedule_fetched_at(self, season_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT fetched_at FROM schedule WHERE season_id = ?", (season_id,)
        ).fetchone()
        return row[0] if row else None

    def get_schedule_page_last_update(self, season_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT page_last_update FROM schedule WHERE season_id = ?", (season_id,)
        ).fetchone()
        return row[0] if row else None

    def save_schedule(self, season_id: int, schedule: List[ScheduleEntry], page_last_update: Optional[str] = None) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO schedule (season_id, data, fetched_at, page_last_update) VALUES (?, ?, ?, ?)",
            (season_id, json.dumps([dataclasses.asdict(e) for e in schedule], ensure_ascii=False), _utc_now_iso(), page_last_update),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Player stats
    # ------------------------------------------------------------------

    def load_player_stats(self, season_id: int) -> Optional[List[PlayerStat]]:
        row = self._get_conn().execute(
            "SELECT data FROM player_stats WHERE season_id = ?", (season_id,)
        ).fetchone()
        return [PlayerStat.from_dict(e) for e in json.loads(row[0])] if row else None

    def get_player_stats_fetched_at(self, season_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT fetched_at FROM player_stats WHERE season_id = ?", (season_id,)
        ).fetchone()
        return row[0] if row else None

    def save_player_stats(self, season_id: int, stats: List[PlayerStat]) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO player_stats (season_id, data, fetched_at) VALUES (?, ?, ?)",
            (season_id, json.dumps([dataclasses.asdict(e) for e in stats], ensure_ascii=False), _utc_now_iso()),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Goalie stats
    # ------------------------------------------------------------------

    def load_goalie_stats(self, season_id: int) -> Optional[List[GoalieStat]]:
        row = self._get_conn().execute(
            "SELECT data FROM goalie_stats WHERE season_id = ?", (season_id,)
        ).fetchone()
        return [GoalieStat.from_dict(e) for e in json.loads(row[0])] if row else None

    def get_goalie_stats_fetched_at(self, season_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT fetched_at FROM goalie_stats WHERE season_id = ?", (season_id,)
        ).fetchone()
        return row[0] if row else None

    def save_goalie_stats(self, season_id: int, stats: List[GoalieStat]) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO goalie_stats (season_id, data, fetched_at) VALUES (?, ?, ?)",
            (season_id, json.dumps([dataclasses.asdict(e) for e in stats], ensure_ascii=False), _utc_now_iso()),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Rosters
    # ------------------------------------------------------------------

    def load_rosters(self, season_id: int) -> Optional[List[RosterEntry]]:
        row = self._get_conn().execute(
            "SELECT data FROM rosters WHERE season_id = ?", (season_id,)
        ).fetchone()
        return [RosterEntry.from_dict(e) for e in json.loads(row[0])] if row else None

    def get_rosters_fetched_at(self, season_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT fetched_at FROM rosters WHERE season_id = ?", (season_id,)
        ).fetchone()
        return row[0] if row else None

    def save_rosters(self, season_id: int, rosters: List[RosterEntry]) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO rosters (season_id, data, fetched_at) VALUES (?, ?, ?)",
            (season_id, json.dumps([dataclasses.asdict(e) for e in rosters], ensure_ascii=False), _utc_now_iso()),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Team info
    # ------------------------------------------------------------------

    def load_team_info(self, season_id: int) -> Optional[List[TeamInfo]]:
        row = self._get_conn().execute(
            "SELECT data FROM team_info WHERE season_id = ?", (season_id,)
        ).fetchone()
        return [TeamInfo.from_dict(e) for e in json.loads(row[0])] if row else None

    def get_team_info_fetched_at(self, season_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT fetched_at FROM team_info WHERE season_id = ?", (season_id,)
        ).fetchone()
        return row[0] if row else None

    def save_team_info(self, season_id: int, teams: List[TeamInfo]) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO team_info (season_id, data, fetched_at) VALUES (?, ?, ?)",
            (season_id, json.dumps([dataclasses.asdict(e) for e in teams], ensure_ascii=False), _utc_now_iso()),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Team player stats
    # ------------------------------------------------------------------

    def load_team_player_stats(self, season_id: int) -> Optional[List[TeamPlayerStat]]:
        row = self._get_conn().execute(
            "SELECT data FROM team_player_stats WHERE season_id = ?", (season_id,)
        ).fetchone()
        return [TeamPlayerStat.from_dict(e) for e in json.loads(row[0])] if row else None

    def get_team_player_stats_fetched_at(self, season_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT fetched_at FROM team_player_stats WHERE season_id = ?", (season_id,)
        ).fetchone()
        return row[0] if row else None

    def save_team_player_stats(self, season_id: int, stats: List[TeamPlayerStat]) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO team_player_stats (season_id, data, fetched_at) VALUES (?, ?, ?)",
            (season_id, json.dumps([dataclasses.asdict(e) for e in stats], ensure_ascii=False), _utc_now_iso()),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # SHL.se players
    # ------------------------------------------------------------------

    def save_shl_se_player(self, season_id: int, team: str, jersey: int, data: dict, portrait_path: Optional[str]) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO shl_se_players (season_id, team, jersey, data, portrait_path, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
            (season_id, team, jersey, json.dumps(data, ensure_ascii=False), portrait_path, _utc_now_iso()),
        )
        conn.commit()

    def load_shl_se_player(self, season_id: int, team: str, jersey: int) -> Optional[dict]:
        row = self._get_conn().execute(
            "SELECT team, jersey, data, portrait_path, fetched_at FROM shl_se_players WHERE season_id = ? AND team = ? AND jersey = ?",
            (season_id, team, jersey),
        ).fetchone()
        if row is None:
            return None
        return {
            "team": row[0],
            "jersey": row[1],
            "data": json.loads(row[2]),
            "portrait_path": row[3],
            "fetched_at": row[4],
        }

    def load_shl_se_team_players(self, season_id: int, team: str) -> List[dict]:
        rows = self._get_conn().execute(
            "SELECT team, jersey, data, portrait_path, fetched_at FROM shl_se_players WHERE season_id = ? AND team = ?",
            (season_id, team),
        ).fetchall()
        return [
            {
                "team": row[0],
                "jersey": row[1],
                "data": json.loads(row[2]),
                "portrait_path": row[3],
                "fetched_at": row[4],
            }
            for row in rows
        ]

    def get_shl_se_player_fetched_at(self, season_id: int, team: str, jersey: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT fetched_at FROM shl_se_players WHERE season_id = ? AND team = ? AND jersey = ?",
            (season_id, team, jersey),
        ).fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------
    # Live games
    # ------------------------------------------------------------------

    def load_live_games(self, season_id: int) -> Optional[List[ScheduleEntry]]:
        row = self._get_conn().execute(
            "SELECT data FROM live_games WHERE season_id = ?", (season_id,)
        ).fetchone()
        return [ScheduleEntry.from_dict(e) for e in json.loads(row[0])] if row else None

    def get_live_games_fetched_at(self, season_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT fetched_at FROM live_games WHERE season_id = ?", (season_id,)
        ).fetchone()
        return row[0] if row else None

    def save_live_games(self, season_id: int, games: List[ScheduleEntry], page_last_update: Optional[str] = None) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO live_games (season_id, data, fetched_at, page_last_update) VALUES (?, ?, ?, ?)",
            (season_id, json.dumps([dataclasses.asdict(e) for e in games], ensure_ascii=False), _utc_now_iso(), page_last_update),
        )
        conn.commit()

    def get_live_games_page_last_update(self, season_id: int) -> Optional[str]:
        row = self._get_conn().execute(
            "SELECT page_last_update FROM live_games WHERE season_id = ?", (season_id,)
        ).fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------
    # Poll targets
    # ------------------------------------------------------------------

    def upsert_poll_target(
        self,
        target_type: str,
        target_key: str,
        enabled: bool = True,
        next_poll_at: Optional[str] = None,
        one_shot: bool = False,
    ) -> int:
        now = _utc_now_iso()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id FROM poll_targets WHERE target_type = ? AND target_key = ?",
            (target_type, target_key),
        ).fetchone()

        if row is None:
            cursor = conn.execute(
                "INSERT INTO poll_targets (target_type, target_key, enabled, one_shot, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (target_type, target_key, 1 if enabled else 0, 1 if one_shot else 0, now, now),
            )
            target_id = cursor.lastrowid
            conn.execute(
                "INSERT OR REPLACE INTO poll_state (target_id, next_poll_at) VALUES (?, ?)",
                (target_id, next_poll_at or now),
            )
            conn.commit()
            return target_id

        target_id = int(row[0])
        conn.execute(
            "UPDATE poll_targets SET enabled = ?, one_shot = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, 1 if one_shot else 0, now, target_id),
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
        conn.commit()
        return target_id

    def list_due_poll_targets(self, now_iso: Optional[str] = None) -> List[PollTarget]:
        now_value = now_iso or _utc_now_iso()
        rows = self._get_conn().execute(
            """
            SELECT
                t.id, t.target_type, t.target_key, t.enabled, t.one_shot,
                t.created_at, t.updated_at,
                s.last_success_at, s.last_error_at, s.error_count,
                s.next_poll_at, s.last_duration_ms
            FROM poll_targets t
            LEFT JOIN poll_state s ON s.target_id = t.id
            WHERE t.enabled = 1
              AND (s.next_poll_at IS NULL OR s.next_poll_at <= ?)
            ORDER BY COALESCE(s.next_poll_at, ''), t.id
            """,
            (now_value,),
        ).fetchall()
        return [self._row_to_poll_target(row) for row in rows]

    def list_poll_targets(
        self,
        target_type: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[PollTarget]:
        where_clauses = []
        params: list = []

        if target_type is not None:
            where_clauses.append("t.target_type = ?")
            params.append(target_type)
        if enabled_only:
            where_clauses.append("t.enabled = 1")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        rows = self._get_conn().execute(
            f"""
            SELECT
                t.id, t.target_type, t.target_key, t.enabled, t.one_shot,
                t.created_at, t.updated_at,
                s.last_success_at, s.last_error_at, s.error_count,
                s.next_poll_at, s.last_duration_ms
            FROM poll_targets t
            LEFT JOIN poll_state s ON s.target_id = t.id
            {where_sql}
            ORDER BY t.id ASC
            """,
            tuple(params),
        ).fetchall()
        return [self._row_to_poll_target(row) for row in rows]

    def update_poll_success(self, target_id: int, duration_ms: int, next_poll_at: str) -> None:
        now = _utc_now_iso()
        conn = self._get_conn()
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
        conn.commit()

    def update_poll_error(self, target_id: int, duration_ms: int, next_poll_at: str) -> int:
        now = _utc_now_iso()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT error_count FROM poll_state WHERE target_id = ?", (target_id,)
        ).fetchone()
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
        conn.commit()
        return new_error_count

    # ------------------------------------------------------------------
    # Domain events
    # ------------------------------------------------------------------

    def insert_domain_event(self, event_type: str, aggregate_key: str, payload: dict) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO domain_events (event_type, aggregate_key, payload_json) VALUES (?, ?, ?)",
            (event_type, aggregate_key, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
        event_id = cursor.lastrowid
        _logger.info("domain_event event_type=%s aggregate_key=%s event_id=%d", event_type, aggregate_key, event_id)
        return event_id

    def list_unprocessed_domain_events(self, limit: int = 100) -> List[DomainEvent]:
        rows = self._get_conn().execute(
            """
            SELECT id, event_type, aggregate_key, payload_json, created_at, processed_at
            FROM domain_events
            WHERE processed_at IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            DomainEvent(
                id=int(row[0]),
                event_type=row[1],
                aggregate_key=row[2],
                payload=json.loads(row[3]),
                created_at=row[4],
                processed_at=row[5],
            )
            for row in rows
        ]

    def mark_domain_event_processed(self, event_id: int, processed_at: Optional[str] = None) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE domain_events SET processed_at = ? WHERE id = ?",
            (processed_at or _utc_now_iso(), event_id),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    def register_device(self, fcm_token: str, platform: str = "android") -> int:
        now = _utc_now_iso()
        conn = self._get_conn()
        cursor = conn.execute(
            """
            INSERT INTO devices (fcm_token, platform, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(fcm_token) DO UPDATE SET
                platform = excluded.platform,
                updated_at = excluded.updated_at
            """,
            (fcm_token, platform, now, now),
        )
        conn.commit()
        # Return id of inserted or existing row.
        row = conn.execute("SELECT id FROM devices WHERE fcm_token = ?", (fcm_token,)).fetchone()
        return int(row[0])

    def unregister_device(self, fcm_token: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM devices WHERE fcm_token = ?", (fcm_token,))
        conn.commit()
        return cursor.rowcount > 0

    def list_device_tokens(self) -> List[str]:
        rows = self._get_conn().execute("SELECT fcm_token FROM devices").fetchall()
        return [row[0] for row in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_poll_target(row) -> PollTarget:
        return PollTarget(
            id=int(row[0]),
            target_type=row[1],
            target_key=row[2],
            enabled=bool(row[3]),
            one_shot=bool(row[4]),
            created_at=row[5],
            updated_at=row[6],
            last_success_at=row[7],
            last_error_at=row[8],
            error_count=int(row[9] or 0),
            next_poll_at=row[10],
            last_duration_ms=row[11],
        )


# ------------------------------------------------------------------
# Module-level convenience functions (backward compatibility)
# ------------------------------------------------------------------
# These are used by consumers that pass cache_dir. They create a
# short-lived Store per call. For performance, consumers should
# hold a Store instance and call methods directly.

_store_cache: Dict[Path, Store] = {}


def _store(cache_dir: Path) -> Store:
    resolved = cache_dir.resolve()
    store = _store_cache.get(resolved)
    if store is None:
        store = Store(cache_dir)
        _store_cache[resolved] = store
    return store


# ------------------------------------------------------------------
# Dynamic wrapper generation (backward-compatible module-level API)
# ------------------------------------------------------------------
# Callers import e.g. `from src.shl.store import load_game` and call
# `load_game(cache_dir, game_id)`. These delegate to _store(cache_dir).method(...).

import inspect as _inspect


def cache_db_path(cache_dir: Path) -> Path:
    """Return the SQLite database path for a given cache directory."""
    return cache_dir / "cache.db"


# Names that are handled by __getattr__ (all Store public methods).
_STORE_METHODS = [
    name for name, _ in _inspect.getmembers(Store, predicate=_inspect.isfunction)
    if not name.startswith("_")
]


def __getattr__(name: str):
    """Auto-generate module-level wrappers for Store methods.

    When callers do `from src.shl.store import load_game`, Python calls
    __getattr__('load_game'). We return a function that takes cache_dir
    as first arg and delegates to _store(cache_dir).method(...).
    """
    if name in _STORE_METHODS:
        def _wrapper(cache_dir: Path, *args, **kwargs):
            return getattr(_store(cache_dir), name)(*args, **kwargs)
        _wrapper.__name__ = name
        _wrapper.__qualname__ = name
        # Cache it on the module to avoid repeated __getattr__ calls.
        globals()[name] = _wrapper
        return _wrapper
    raise AttributeError(f"module 'src.shl.store' has no attribute {name!r}")
