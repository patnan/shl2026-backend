"""Standings endpoints."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

from src.shl.routers._helpers import _extract_game_ids, _meta, _serialize
from src.shl.schedule import (
    get_all_played_games,
    get_live_standings,
    get_standings,
)
from src.shl.store import (
    get_games_freshness,
    get_live_games_fetched_at,
    get_schedule_fetched_at,
)


def create_router(cache_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/seasons/{season_id}/standings")
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

    @router.get("/seasons/{season_id}/standings/live")
    def season_standings_live(season_id: int) -> Dict[str, Any]:
        live_standings = get_live_standings(season_id, cache_dir)
        live_fetched_at = get_live_games_fetched_at(cache_dir, season_id)

        return {
            "data": _serialize(live_standings),
            "meta": {
                "season_id": str(season_id),
                "source_live_games_fetched_at": live_fetched_at,
                **_meta(),
            },
        }

    return router
