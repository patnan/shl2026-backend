"""Team info endpoint."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.shl.routers._helpers import _meta, _serialize
from src.shl.stats import fetch_team_info, get_team_info
from src.shl.store import get_team_info_fetched_at

logger = logging.getLogger(__name__)


def create_router(cache_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/seasons/{season_id}/teams")
    def season_teams(season_id: int) -> Dict[str, Any]:
        teams = get_team_info(season_id, cache_dir)
        if teams is None:
            try:
                teams = fetch_team_info(season_id, cache_dir)
            except Exception:
                logger.exception("Failed to fetch team info for season %s", season_id)
                return JSONResponse(status_code=502, content={"error": "Failed to fetch team info from upstream."})
        return {
            "data": _serialize(teams),
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": get_team_info_fetched_at(cache_dir, season_id),
                **_meta(),
            },
        }

    return router
