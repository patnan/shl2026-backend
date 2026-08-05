"""Fetch and read player stats, goalie stats, and rosters from SweHockey."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from src.shl.helpers.extraction import fetch_html
from src.shl.helpers.stats_parsing import (
    parse_leading_goalies,
    parse_scoring_leaders,
    parse_team_abbreviations,
    parse_team_rosters,
)
from src.shl.models import GoalieStat, PlayerStat, RosterEntry, TeamInfo
from src.shl.store import (
    load_goalie_stats,
    load_player_stats,
    load_rosters,
    load_team_info,
    save_goalie_stats,
    save_player_stats,
    save_rosters,
    save_team_info,
)


SCORING_LEADERS_URL = "https://stats.swehockey.se/Players/Statistics/ScoringLeaders/{season_id}"
LEADING_GOALIES_URL = "https://stats.swehockey.se/Players/Statistics/LeadingGoaliesSVS/{season_id}"
TEAM_ROSTER_URL = "https://stats.swehockey.se/Teams/Info/TeamRoster/{season_id}"


class FetchPlayerStatsError(RuntimeError):
    pass


class FetchGoalieStatsError(RuntimeError):
    pass


class FetchRostersError(RuntimeError):
    pass


class FetchTeamInfoError(RuntimeError):
    pass


def fetch_player_stats(season_id: int, db_dir: Path, force_reparse: bool = False) -> List[PlayerStat]:
    """Fetch scoring leaders from SweHockey, parse and persist.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.
        force_reparse: If True, always re-scrape regardless of cache state.

    Returns:
        List of PlayerStat dataclasses.
    """
    try:
        if not force_reparse:
            cached = load_player_stats(db_dir, season_id)
            if cached is not None:
                return cached

        url = SCORING_LEADERS_URL.format(season_id=season_id)
        html = fetch_html(url)
        stats = parse_scoring_leaders(html)
        save_player_stats(db_dir, season_id, stats)
        return stats
    except FetchPlayerStatsError:
        raise
    except Exception as exc:
        raise FetchPlayerStatsError(f"fetch_player_stats failed for season '{season_id}': {exc}") from exc


def fetch_goalie_stats(season_id: int, db_dir: Path, force_reparse: bool = False) -> List[GoalieStat]:
    """Fetch leading goalies from SweHockey, parse and persist.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.
        force_reparse: If True, always re-scrape regardless of cache state.

    Returns:
        List of GoalieStat dataclasses.
    """
    try:
        if not force_reparse:
            cached = load_goalie_stats(db_dir, season_id)
            if cached is not None:
                return cached

        url = LEADING_GOALIES_URL.format(season_id=season_id)
        html = fetch_html(url)
        stats = parse_leading_goalies(html)
        save_goalie_stats(db_dir, season_id, stats)
        return stats
    except FetchGoalieStatsError:
        raise
    except Exception as exc:
        raise FetchGoalieStatsError(f"fetch_goalie_stats failed for season '{season_id}': {exc}") from exc


def fetch_rosters(season_id: int, db_dir: Path, force_reparse: bool = False) -> List[RosterEntry]:
    """Fetch team rosters from SweHockey, parse and persist.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.
        force_reparse: If True, always re-scrape regardless of cache state.

    Returns:
        List of RosterEntry dataclasses for all teams.
    """
    try:
        if not force_reparse:
            cached = load_rosters(db_dir, season_id)
            if cached is not None:
                return cached

        url = TEAM_ROSTER_URL.format(season_id=season_id)
        html = fetch_html(url)
        rosters = parse_team_rosters(html)
        save_rosters(db_dir, season_id, rosters)
        return rosters
    except FetchRostersError:
        raise
    except Exception as exc:
        raise FetchRostersError(f"fetch_rosters failed for season '{season_id}': {exc}") from exc


def get_player_stats(season_id: int, db_dir: Path) -> Optional[List[PlayerStat]]:
    """Load cached player stats, or None if not yet fetched."""
    return load_player_stats(db_dir, season_id)


def get_goalie_stats(season_id: int, db_dir: Path) -> Optional[List[GoalieStat]]:
    """Load cached goalie stats, or None if not yet fetched."""
    return load_goalie_stats(db_dir, season_id)


def get_rosters(season_id: int, db_dir: Path) -> Optional[List[RosterEntry]]:
    """Load cached rosters, or None if not yet fetched."""
    return load_rosters(db_dir, season_id)


def fetch_team_info(season_id: int, db_dir: Path, force_reparse: bool = False) -> List[TeamInfo]:
    """Fetch team abbreviations from SweHockey, parse and persist.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.
        force_reparse: If True, always re-scrape regardless of cache state.

    Returns:
        List of TeamInfo dataclasses.
    """
    try:
        if not force_reparse:
            cached = load_team_info(db_dir, season_id)
            if cached is not None:
                return cached

        url = TEAM_ROSTER_URL.format(season_id=season_id)
        html = fetch_html(url)
        teams = parse_team_abbreviations(html)
        save_team_info(db_dir, season_id, teams)
        return teams
    except FetchTeamInfoError:
        raise
    except Exception as exc:
        raise FetchTeamInfoError(f"fetch_team_info failed for season '{season_id}': {exc}") from exc


def get_team_info(season_id: int, db_dir: Path) -> Optional[List[TeamInfo]]:
    """Load cached team info, or None if not yet fetched."""
    return load_team_info(db_dir, season_id)
