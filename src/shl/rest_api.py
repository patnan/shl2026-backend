from __future__ import annotations

import dataclasses
import logging
import os
import re
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.shl.schedule import (
    get_all_played_games,
    get_games_for_date,
    get_next_round,
    get_played_rounds,
    get_rounds,
    get_schedule,
    get_standings,
    get_todays_games,
)
from src.shl.store import get_games_freshness, get_schedule_fetched_at
from src.shl.store import get_game_fetched_at, load_game
from src.shl.store import register_device, unregister_device
from src.shl.stats import get_goalie_stats, get_player_stats, get_rosters, get_team_info
from src.shl.store import get_player_stats_fetched_at, get_goalie_stats_fetched_at, get_rosters_fetched_at, get_team_info_fetched_at


# ---------------------------------------------------------------------------
# Rate limiter (in-memory, per-IP)
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Simple sliding-window rate limiter keyed by client IP."""

    def __init__(self, requests_per_minute: int = 60) -> None:
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60.0
        self._hits: Dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        hits = self._hits[client_ip]
        # Prune expired entries.
        self._hits[client_ip] = [t for t in hits if t > window_start]
        if len(self._hits[client_ip]) >= self.requests_per_minute:
            return False
        self._hits[client_ip].append(now)
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def create_app(cache_dir: Path) -> FastAPI:
    app = FastAPI(
        title="SHL Data API",
        version="0.1.0",
        description="Read-only API over persisted SHL schedule, game metadata, and standings data.",
    )

    # CORS — allowed origins configurable via env var (comma-separated).
    # Defaults to permissive for development; set SHL_CORS_ORIGINS in production.
    allowed_origins = os.environ.get("SHL_CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allowed_origins],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    # Rate limiting.
    rate_limit = int(os.environ.get("SHL_RATE_LIMIT_PER_MINUTE", "60"))
    limiter = _RateLimiter(requests_per_minute=rate_limit)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        # Skip rate limiting for health checks.
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        if not limiter.is_allowed(client_ip):
            logger.warning("rate_limited client_ip=%s path=%s", client_ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Try again later."},
            )
        return await call_next(request)

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/devices")
    def device_register(request_body: Dict[str, Any]) -> Dict[str, Any]:
        fcm_token = request_body.get("fcm_token")
        if not fcm_token or not isinstance(fcm_token, str):
            raise HTTPException(status_code=400, detail="fcm_token is required")
        platform = request_body.get("platform", "android")
        device_id = register_device(cache_dir, fcm_token, platform)
        return {"device_id": device_id, "status": "registered"}

    @app.delete("/devices")
    def device_unregister(request_body: Dict[str, Any]) -> Dict[str, Any]:
        fcm_token = request_body.get("fcm_token")
        if not fcm_token or not isinstance(fcm_token, str):
            raise HTTPException(status_code=400, detail="fcm_token is required")
        removed = unregister_device(cache_dir, fcm_token)
        if not removed:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"status": "unregistered"}

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

    @app.get("/seasons/{season_id}/rounds")
    def season_rounds(season_id: int) -> Dict[str, Any]:
        rounds = get_rounds(season_id, cache_dir)
        if not rounds:
            raise HTTPException(status_code=404, detail=f"No schedule stored for season {season_id}")
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)

        return {
            "data": [{"round": r["round"], "games": _serialize(r["games"])} for r in rounds],
            "meta": {
                "season_id": str(season_id),
                "total_rounds": len(rounds),
                "source_fetched_at": source_fetched_at,
                **_meta(),
            },
        }

    @app.get("/seasons/{season_id}/rounds/played")
    def season_played_rounds(season_id: int) -> Dict[str, Any]:
        rounds = get_played_rounds(season_id, cache_dir)
        if not rounds:
            raise HTTPException(status_code=404, detail=f"No played rounds found for season {season_id}")
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)

        return {
            "data": [{"round": r["round"], "games": _serialize(r["games"])} for r in rounds],
            "meta": {
                "season_id": str(season_id),
                "total_rounds": len(rounds),
                "source_fetched_at": source_fetched_at,
                **_meta(),
            },
        }

    @app.get("/seasons/{season_id}/rounds/next")
    def season_next_round(season_id: int) -> Dict[str, Any]:
        next_round = get_next_round(season_id, cache_dir)
        if next_round is None:
            raise HTTPException(status_code=404, detail=f"No upcoming round found for season {season_id}")
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)

        return {
            "data": {"round": next_round["round"], "games": _serialize(next_round["games"])},
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": source_fetched_at,
                **_meta(),
            },
        }

    @app.get("/seasons/{season_id}/games/today")
    def season_todays_games(season_id: int) -> Dict[str, Any]:
        games = get_todays_games(season_id, cache_dir)
        source_fetched_at = get_schedule_fetched_at(cache_dir, season_id)
        return {
            "data": _serialize(games),
            "meta": {
                "season_id": str(season_id),
                "count": len(games),
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

    # ------------------------------------------------------------------
    # Player stats
    # ------------------------------------------------------------------

    @app.get("/seasons/{season_id}/players")
    def season_player_stats(season_id: int, team: Optional[str] = None) -> Dict[str, Any]:
        stats = get_player_stats(season_id, cache_dir)
        if stats is None:
            return JSONResponse(status_code=404, content={"error": "Player stats not yet fetched for this season."})
        if team:
            stats = [s for s in stats if s.team.upper() == team.upper()]
        return {
            "data": _serialize(stats),
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": get_player_stats_fetched_at(cache_dir, season_id),
                **_meta(),
            },
        }

    @app.get("/seasons/{season_id}/goalies")
    def season_goalie_stats(season_id: int, team: Optional[str] = None) -> Dict[str, Any]:
        stats = get_goalie_stats(season_id, cache_dir)
        if stats is None:
            return JSONResponse(status_code=404, content={"error": "Goalie stats not yet fetched for this season."})
        if team:
            stats = [s for s in stats if s.team.upper() == team.upper()]
        return {
            "data": _serialize(stats),
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": get_goalie_stats_fetched_at(cache_dir, season_id),
                **_meta(),
            },
        }

    @app.get("/seasons/{season_id}/rosters")
    def season_rosters(season_id: int, team: Optional[str] = None) -> Dict[str, Any]:
        rosters = get_rosters(season_id, cache_dir)
        if rosters is None:
            return JSONResponse(status_code=404, content={"error": "Rosters not yet fetched for this season."})
        if team:
            rosters = [r for r in rosters if r.team.upper() == team.upper() or r.team == team]
        return {
            "data": _serialize(rosters),
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": get_rosters_fetched_at(cache_dir, season_id),
                **_meta(),
            },
        }

    @app.get("/seasons/{season_id}/teams")
    def season_teams(season_id: int) -> Dict[str, Any]:
        teams = get_team_info(season_id, cache_dir)
        if teams is None:
            return JSONResponse(status_code=404, content={"error": "Team info not yet fetched for this season."})
        return {
            "data": _serialize(teams),
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": get_team_info_fetched_at(cache_dir, season_id),
                **_meta(),
            },
        }

    return app
