from __future__ import annotations

import dataclasses
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException

from src.shl.schedule import (
    get_all_played_games,
    get_games_for_date,
    get_schedule,
    get_standings,
)
from src.shl.store import get_games_freshness, get_schedule_fetched_at
from src.shl.store import get_game_fetched_at, load_game


def _serialize(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    return value


def _meta() -> Dict[str, str]:
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _extract_game_ids(entries: list[Any]) -> list[int]:
    ids: list[int] = []
    for entry in entries:
        game_url = getattr(entry, "game_url", "")
        match = re.search(r"/(\d+)$", game_url)
        if match is None:
            continue
        ids.append(int(match.group(1)))
    return ids


def create_app(cache_dir: Path) -> FastAPI:
    app = FastAPI(
        title="SHL Data API",
        version="0.1.0",
        description="Read-only API over persisted SHL schedule, game metadata, and standings data.",
    )

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/seasons/{season_id}/schedule")
    def season_schedule(season_id: int) -> Dict[str, Any]:
        schedule = get_schedule(season_id, cache_dir)
        if schedule is None:
            raise HTTPException(status_code=404, detail=f"No schedule stored for season {season_id}")
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)

        return {
            "data": _serialize(schedule),
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": source_fetched_at,
                **_meta(),
            },
        }

    @app.get("/seasons/{season_id}/games")
    def season_games_by_date(season_id: int, date: date) -> Dict[str, Any]:
        games = get_games_for_date(season_id, date.isoformat(), cache_dir)
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)
        return {
            "data": _serialize(games),
            "meta": {
                "season_id": str(season_id),
                "date": date.isoformat(),
                "source_schedule_fetched_at": source_fetched_at,
                **_meta(),
            },
        }

    @app.get("/seasons/{season_id}/games/played")
    def season_played_games(season_id: int) -> Dict[str, Any]:
        played_games = get_all_played_games(season_id, cache_dir)
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)
        return {
            "data": _serialize(played_games),
            "meta": {
                "season_id": str(season_id),
                "source_schedule_fetched_at": source_fetched_at,
                **_meta(),
            },
        }

    @app.get("/games/{game_id}")
    def game_details(game_id: int) -> Dict[str, Any]:
        game = load_game(cache_dir, game_id)
        if game is None:
            raise HTTPException(status_code=404, detail=f"No game stored for game_id {game_id}")

        source_fetched_at = get_game_fetched_at(cache_dir, game_id)
        return {
            "data": _serialize(game),
            "meta": {
                "game_id": str(game_id),
                "source_fetched_at": source_fetched_at,
                **_meta(),
            },
        }

    @app.get("/seasons/{season_id}/standings")
    def season_standings(season_id: int) -> Dict[str, Any]:
        standings = get_standings(season_id, cache_dir)
        played_games = get_all_played_games(season_id, cache_dir)
        played_game_ids = _extract_game_ids(played_games)
        games_freshness = get_games_freshness(cache_dir, played_game_ids)
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)
        return {
            "data": _serialize(standings),
            "meta": {
                "season_id": str(season_id),
                "source_schedule_fetched_at": source_fetched_at,
                "source_games_latest_fetched_at": games_freshness["latest_fetched_at"],
                "source_games_oldest_fetched_at": games_freshness["oldest_fetched_at"],
                "source_games_cached_count": games_freshness["cached_game_count"],
                "source_games_requested_count": games_freshness["requested_game_count"],
                **_meta(),
            },
        }

    return app
