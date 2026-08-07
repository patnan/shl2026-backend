"""Single game detail endpoint."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from src.shl.routers._helpers import _meta, _serialize
from src.shl.store import get_game_fetched_at


def create_router(cache_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/games/{game_id}")
    def game_details(game_id: int) -> Dict[str, Any]:
        # Always fetch fresh data from SweHockey (no caching).
        try:
            from src.shl.game import fetch_game
            game = fetch_game(game_id, cache_dir, force_reparse=True)
        except Exception:
            raise HTTPException(status_code=404, detail=f"Game not found for game_id {game_id}")

        source_fetched_at = get_game_fetched_at(cache_dir, game_id)
        return {
            "data": _serialize(game),
            "meta": {
                "game_id": str(game_id),
                "source_fetched_at": source_fetched_at,
                **_meta(),
            },
        }

    return router
