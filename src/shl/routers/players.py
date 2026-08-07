"""Player stats, goalie stats, roster, and merged player endpoints."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.shl.routers._helpers import _meta, _serialize
from src.shl.shl_se import (
    fetch_shl_se_player,
    fetch_shl_se_team_players,
    get_shl_se_player,
    get_shl_se_team_players,
)
from src.shl.stats import (
    fetch_rosters,
    fetch_team_player_stats,
    get_goalie_stats,
    get_player_stats,
    get_rosters,
)
from src.shl.store import (
    get_goalie_stats_fetched_at,
    get_player_stats_fetched_at,
    get_rosters_fetched_at,
    get_team_player_stats_fetched_at,
)

logger = logging.getLogger(__name__)


def create_router(cache_dir: Path) -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------------
    # Helper: lazy-load rosters + merge shl.se data
    # ------------------------------------------------------------------

    def _get_rosters_lazy(season_id: int) -> Optional[list]:
        """Get rosters with lazy-load from SweHockey if not cached."""
        rosters = get_rosters(season_id, cache_dir)
        if rosters is None:
            try:
                rosters = fetch_rosters(season_id, cache_dir)
            except Exception:
                logger.exception("Failed to fetch rosters for season %s", season_id)
                return None
        return rosters

    def _merge_player(roster_entry: object, shl_se_data: Optional[dict]) -> dict:
        """Merge a RosterEntry with shl.se player data into a single dict (static data only)."""
        merged = roster_entry.to_dict()
        if shl_se_data:
            merged["first_name"] = shl_se_data.get("first_name", "")
            merged["last_name"] = shl_se_data.get("last_name", "")
            merged["portrait_url"] = shl_se_data.get("portrait_url", "")
            merged["team_code"] = shl_se_data.get("team_code", "")
            merged["shl_se_uuid"] = shl_se_data.get("shl_se_uuid", "")
        else:
            merged["first_name"] = ""
            merged["last_name"] = ""
            merged["portrait_url"] = ""
            merged["team_code"] = ""
            merged["shl_se_uuid"] = ""
        return merged

    # ------------------------------------------------------------------
    # Scoring leaders and goalie stats
    # ------------------------------------------------------------------

    @router.get("/seasons/{season_id}/players")
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

    @router.get("/seasons/{season_id}/goalies")
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

    # ------------------------------------------------------------------
    # Player game stats (dynamic, fetched on demand)
    # ------------------------------------------------------------------

    @router.get("/seasons/{season_id}/players/{team}/{jersey}/stats")
    def player_stats_detail(season_id: int, team: str, jersey: int) -> Dict[str, Any]:
        """Get dynamic game stats for a single player (fetched on demand from PlayersByTeam)."""
        try:
            all_stats = fetch_team_player_stats(season_id, cache_dir)
        except Exception:
            logger.exception("Failed to fetch team player stats for season %s", season_id)
            return JSONResponse(status_code=502, content={"error": "Failed to fetch player stats from upstream."})

        stat = next(
            (s for s in all_stats if s.team == team and s.jersey == jersey),
            None,
        )
        if stat is None:
            raise HTTPException(status_code=404, detail=f"Stats not found for {team} #{jersey}")

        return {
            "data": stat.to_dict(),
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": get_team_player_stats_fetched_at(cache_dir, season_id),
                **_meta(),
            },
        }

    # ------------------------------------------------------------------
    # Merged player detail (roster + shl.se)
    # ------------------------------------------------------------------

    @router.get("/seasons/{season_id}/players/{team}/{jersey}")
    def merged_player_detail(season_id: int, team: str, jersey: int) -> Dict[str, Any]:
        """Get a single player with merged SweHockey roster + shl.se data."""
        rosters = _get_rosters_lazy(season_id)
        if rosters is None:
            return JSONResponse(status_code=502, content={"error": "Failed to fetch roster data from upstream."})

        # Find player in roster by team + jersey
        entry = next(
            (r for r in rosters if r.team == team and r.jersey == jersey),
            None,
        )
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Player not found: {team} #{jersey}")

        # Get shl.se data (lazy-load)
        shl_se_data = get_shl_se_player(season_id, team, jersey, cache_dir)
        if shl_se_data is None:
            try:
                shl_se_data = fetch_shl_se_player(season_id, team, jersey, cache_dir)
            except Exception:
                logger.warning("Could not fetch shl.se data for %s #%d", team, jersey)

        return {
            "data": _merge_player(entry, shl_se_data),
            "meta": {
                "season_id": str(season_id),
                "source_fetched_at": get_rosters_fetched_at(cache_dir, season_id),
                **_meta(),
            },
        }

    # ------------------------------------------------------------------
    # Merged team roster
    # ------------------------------------------------------------------

    @router.get("/seasons/{season_id}/players/{team}")
    def merged_team_players(season_id: int, team: str) -> Dict[str, Any]:
        """Get all players for a team with merged SweHockey roster + shl.se data."""
        rosters = _get_rosters_lazy(season_id)
        if rosters is None:
            return JSONResponse(status_code=502, content={"error": "Failed to fetch roster data from upstream."})

        # Filter roster by team
        team_roster = [r for r in rosters if r.team == team]
        if not team_roster:
            raise HTTPException(status_code=404, detail=f"No players found for team: {team}")

        # Get shl.se data for entire team (lazy-load)
        _MIN_ROSTER_SIZE = 5
        shl_se_players = get_shl_se_team_players(season_id, team, cache_dir)
        if not shl_se_players or len(shl_se_players) < _MIN_ROSTER_SIZE:
            try:
                shl_se_players = fetch_shl_se_team_players(season_id, team, cache_dir, force_refresh=True)
            except Exception:
                logger.warning("Could not fetch shl.se team data for %s", team)
                shl_se_players = []

        # Index shl.se players by jersey number for O(1) lookup
        shl_se_by_jersey: Dict[int, dict] = {}
        for p in (shl_se_players or []):
            shl_se_by_jersey[p.get("jersey_number", 0)] = p

        merged = [_merge_player(r, shl_se_by_jersey.get(r.jersey)) for r in team_roster]

        return {
            "data": merged,
            "meta": {
                "season_id": str(season_id),
                "count": len(merged),
                "source_fetched_at": get_rosters_fetched_at(cache_dir, season_id),
                **_meta(),
            },
        }

    return router
