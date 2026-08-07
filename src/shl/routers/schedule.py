"""Schedule, rounds, and games-by-date endpoints."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.shl.routers._helpers import _meta, _serialize
from src.shl.schedule import (
    get_all_played_games,
    get_games_for_date,
    get_live_games,
    get_next_round,
    get_played_rounds,
    get_rounds,
    get_schedule,
    get_todays_games,
    fetch_live_games,
)
from src.shl.store import (
    get_live_games_fetched_at,
    get_live_games_page_last_update,
    get_schedule_fetched_at,
    get_schedule_page_last_update,
)

logger = logging.getLogger(__name__)


def create_router(cache_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/seasons/{season_id}/schedule")
    def season_schedule(season_id: int) -> Dict[str, Any]:
        schedule = get_schedule(season_id, cache_dir)
        if schedule is None:
            raise HTTPException(status_code=404, detail=f"No schedule stored for season {season_id}")
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)
        page_last_update = get_schedule_page_last_update(cache_dir, season_id)

        return {
            "data": _serialize(schedule),
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": source_fetched_at,
                "page_last_update": page_last_update,
                **_meta(),
            },
        }

    @router.get("/seasons/{season_id}/rounds")
    def season_rounds(season_id: int) -> Dict[str, Any]:
        rounds = get_rounds(season_id, cache_dir)
        if not rounds:
            raise HTTPException(status_code=404, detail=f"No schedule stored for season {season_id}")
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)
        page_last_update = get_schedule_page_last_update(cache_dir, season_id)

        return {
            "data": [{"round": r["round"], "games": _serialize(r["games"])} for r in rounds],
            "meta": {
                "season_id": str(season_id),
                "total_rounds": len(rounds),
                "source_fetched_at": source_fetched_at,
                "page_last_update": page_last_update,
                **_meta(),
            },
        }

    @router.get("/seasons/{season_id}/rounds/played")
    def season_played_rounds(season_id: int) -> Dict[str, Any]:
        rounds = get_played_rounds(season_id, cache_dir)
        if not rounds:
            raise HTTPException(status_code=404, detail=f"No played rounds found for season {season_id}")
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)
        page_last_update = get_schedule_page_last_update(cache_dir, season_id)

        return {
            "data": [{"round": r["round"], "games": _serialize(r["games"])} for r in rounds],
            "meta": {
                "season_id": str(season_id),
                "total_rounds": len(rounds),
                "source_fetched_at": source_fetched_at,
                "page_last_update": page_last_update,
                **_meta(),
            },
        }

    @router.get("/seasons/{season_id}/rounds/next")
    def season_next_round(season_id: int) -> Dict[str, Any]:
        next_round = get_next_round(season_id, cache_dir)
        if next_round is None:
            raise HTTPException(status_code=404, detail=f"No upcoming round found for season {season_id}")
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)
        page_last_update = get_schedule_page_last_update(cache_dir, season_id)

        return {
            "data": {"round": next_round["round"], "games": _serialize(next_round["games"])},
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": source_fetched_at,
                "page_last_update": page_last_update,
                **_meta(),
            },
        }

    @router.get("/seasons/{season_id}/games/today")
    def season_todays_games(season_id: int) -> Dict[str, Any]:
        games = get_todays_games(season_id, cache_dir)
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)
        page_last_update = get_schedule_page_last_update(cache_dir, season_id)
        return {
            "data": _serialize(games),
            "meta": {
                "season_id": str(season_id),
                "count": len(games),
                "source_fetched_at": source_fetched_at,
                "page_last_update": page_last_update,
                **_meta(),
            },
        }

    @router.get("/seasons/{season_id}/games/live")
    def season_live_games(season_id: int) -> Dict[str, Any]:
        """Return today's live/upcoming games scraped from the SweHockey Live page.

        Data is refreshed every 25s by the poller. On first request (before poller
        has run), fetches on demand and caches the result.
        """
        games = get_live_games(season_id, cache_dir)
        if games is None:
            # Bootstrap cache on first request before poller has populated it.
            try:
                games, _, _ = fetch_live_games(season_id, cache_dir)
            except Exception:
                logger.exception("Failed to fetch live games for season %s", season_id)
                return JSONResponse(
                    status_code=502,
                    content={"error": "Failed to fetch live games from upstream."},
                )
        source_fetched_at = get_live_games_fetched_at(cache_dir, season_id)
        page_last_update = get_live_games_page_last_update(cache_dir, season_id)
        return {
            "data": _serialize(games),
            "meta": {
                "season_id": str(season_id),
                "count": len(games),
                "source_fetched_at": source_fetched_at,
                "page_last_update": page_last_update,
                **_meta(),
            },
        }

    @router.get("/seasons/{season_id}/games/played")
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

    @router.get("/seasons/{season_id}/games")
    def season_games(season_id: int, date: Optional[date] = None) -> Dict[str, Any]:
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)
        page_last_update = get_schedule_page_last_update(cache_dir, season_id)
        if date is not None:
            games = get_games_for_date(season_id, date.isoformat(), cache_dir)
            return {
                "data": _serialize(games),
                "meta": {
                    "season_id": str(season_id),
                    "date": date.isoformat(),
                    "source_schedule_fetched_at": source_fetched_at,
                    "page_last_update": page_last_update,
                    **_meta(),
                },
            }
        # No date filter — return all games.
        schedule = get_schedule(season_id, cache_dir)
        if schedule is None:
            return JSONResponse(
                status_code=404,
                content={"error": "Schedule not yet fetched for this season."},
            )
        return {
            "data": _serialize(schedule),
            "meta": {
                "season_id": str(season_id),
                "count": len(schedule),
                "source_schedule_fetched_at": source_fetched_at,
                "page_last_update": page_last_update,
                **_meta(),
            },
        }

    return router
