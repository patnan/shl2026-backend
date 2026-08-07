"""Health check and root endpoint."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter


def create_router(cache_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/")
    def root() -> Dict[str, Any]:
        """List all available API endpoints with descriptions."""
        return {
            "name": "SHL Data API",
            "version": "0.1.0",
            "endpoints": [
                {"path": "/health", "method": "GET", "description": "Health check"},
                {"path": "/devices", "method": "POST", "description": "Register a device for push notifications"},
                {"path": "/devices", "method": "DELETE", "description": "Unregister a device from push notifications"},
                {"path": "/seasons/{season_id}/schedule", "method": "GET", "description": "Full season schedule"},
                {"path": "/seasons/{season_id}/rounds", "method": "GET", "description": "Schedule grouped by round"},
                {"path": "/seasons/{season_id}/rounds/played", "method": "GET", "description": "Completed rounds only"},
                {"path": "/seasons/{season_id}/rounds/next", "method": "GET", "description": "Next upcoming round"},
                {"path": "/seasons/{season_id}/games/today", "method": "GET", "description": "Today's games"},
                {"path": "/seasons/{season_id}/games/live", "method": "GET", "description": "Live/upcoming games from SweHockey Live page"},
                {"path": "/seasons/{season_id}/games/played", "method": "GET", "description": "All played games"},
                {"path": "/seasons/{season_id}/games?date={YYYY-MM-DD}", "method": "GET", "description": "Games for a specific date"},
                {"path": "/seasons/{season_id}/standings", "method": "GET", "description": "Current standings computed from played games"},
                {"path": "/seasons/{season_id}/players", "method": "GET", "description": "Player scoring leaders (optional ?team= filter)"},
                {"path": "/seasons/{season_id}/goalies", "method": "GET", "description": "Goalie stats (optional ?team= filter)"},
                {"path": "/seasons/{season_id}/teams", "method": "GET", "description": "Team info with logos and abbreviations"},
                {"path": "/seasons/{season_id}/players/{team}", "method": "GET", "description": "Team roster with merged shl.se data"},
                {"path": "/seasons/{season_id}/players/{team}/{jersey}", "method": "GET", "description": "Single player detail (roster + shl.se)"},
                {"path": "/seasons/{season_id}/players/{team}/{jersey}/stats", "method": "GET", "description": "Player game stats (GP, G, A, TP, PIM, etc.)"},
                {"path": "/games/{game_id}", "method": "GET", "description": "Full game detail by game ID"},
                {"path": "/portraits/{filename}", "method": "GET", "description": "Player portrait image"},
            ],
        }

    @router.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    return router
