import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional


def cache_db_path(cache_dir: Path) -> Path:
    return cache_dir / "cache.db"


def _connect(cache_dir: Path) -> sqlite3.Connection:
    db_path = cache_db_path(cache_dir)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS games (
            season_id INTEGER PRIMARY KEY,
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
    conn.commit()
    return conn


def load_games(cache_dir: Path, season_id: int) -> Optional[List[Dict]]:
    with _connect(cache_dir) as conn:
        row = conn.execute("SELECT data FROM games WHERE season_id = ?", (season_id,)).fetchone()
    return json.loads(row[0]) if row else None


def save_games(cache_dir: Path, season_id: int, games: List[Dict]) -> None:
    with _connect(cache_dir) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO games (season_id, data, fetched_at) VALUES (?, ?, datetime('now'))",
            (season_id, json.dumps(games, ensure_ascii=False)),
        )


def load_standings(cache_dir: Path, season_id: int) -> Optional[List[Dict]]:
    with _connect(cache_dir) as conn:
        row = conn.execute("SELECT data FROM standings WHERE season_id = ?", (season_id,)).fetchone()
    return json.loads(row[0]) if row else None


def save_standings(cache_dir: Path, season_id: int, standings: List[Dict]) -> None:
    with _connect(cache_dir) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO standings (season_id, data, fetched_at) VALUES (?, ?, datetime('now'))",
            (season_id, json.dumps(standings, ensure_ascii=False)),
        )
