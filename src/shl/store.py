import dataclasses
import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from src.shl.models import Game, ScheduleEntry, StandingsRow


def cache_db_path(cache_dir: Path) -> Path:
    return cache_dir / "cache.db"


def _connect(cache_dir: Path) -> sqlite3.Connection:
    db_path = cache_db_path(cache_dir)
    conn = sqlite3.connect(db_path)
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
