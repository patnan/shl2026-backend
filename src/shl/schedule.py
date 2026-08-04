import re
from pathlib import Path
from typing import Dict, List, Optional

from src.shl.helpers.extraction import (
    extract_schedule_games,
)
from src.shl.models import ScheduleEntry, StandingsRow
from src.shl.store import save_schedule, load_schedule, load_games_batch
from src.shl.standings import calculate_standings


class FetchScheduleError(RuntimeError):
    pass


class GetGamesForDateError(RuntimeError):
    pass


class GetAllPlayedGamesError(RuntimeError):
    pass


def fetch_schedule(season_id: int, db_dir: Path, force_reparse: bool = False) -> List[ScheduleEntry]:
    """Fetch the season schedule, using cached data if available.

    Scrapes the SweHockey schedule page on cache miss or when force_reparse is True,
    and persists the result to the database.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.
        force_reparse: If True, always re-scrape regardless of cache state.

    Returns:
        List of ScheduleEntry dataclasses for the season.

    Raises:
        FetchScheduleError: If scraping or loading fails.
    """
    try:
        if not force_reparse:
            cached = load_schedule(db_dir, season_id)
            if cached is not None:
                return cached

        url = f"https://stats.swehockey.se/ScheduleAndResults/Schedule/{season_id}"
        schedule = extract_schedule_games(url)
        save_schedule(db_dir, season_id, schedule)
        return schedule
    except Exception as exc:
        raise FetchScheduleError(f"fetch_schedule failed for season '{season_id}': {exc}") from exc


def get_games_for_date(season_id: int, game_date: str, db_dir: Path) -> List[ScheduleEntry]:
    """Return schedule entries matching a specific date from the cached schedule.

    Args:
        season_id: SweHockey season/tournament ID.
        game_date: Date string (YYYY-MM-DD) to filter by.
        db_dir: Path to the cache/database directory.

    Returns:
        List of matching ScheduleEntry dataclasses (empty if no schedule cached).

    Raises:
        GetGamesForDateError: If loading or filtering fails.
    """
    try:
        schedule = load_schedule(db_dir, season_id)
        if schedule is None:
            return []
        return [entry for entry in schedule if entry.date.startswith(game_date)]
    except Exception as exc:
        raise GetGamesForDateError(
            f"get_games_for_date failed for season '{season_id}' and date '{game_date}': {exc}"
        ) from exc


def get_all_played_games(season_id: int, db_dir: Path) -> List[ScheduleEntry]:
    """Return all schedule entries that have a recorded result.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        List of ScheduleEntry dataclasses with non-empty game_result.

    Raises:
        GetAllPlayedGamesError: If loading fails.
    """
    try:
        schedule = load_schedule(db_dir, season_id)
        if schedule is None:
            return []
        return [entry for entry in schedule if entry.game_result]
    except Exception as exc:
        raise GetAllPlayedGamesError(f"get_all_played_games failed for season '{season_id}': {exc}") from exc


def get_schedule(season_id: int, db_dir: Path) -> Optional[List[ScheduleEntry]]:
    """Load the cached schedule for a season, or None if not yet fetched."""
    return load_schedule(db_dir, season_id)


def get_rounds(season_id: int, db_dir: Path) -> List[Dict]:
    """Group the cached schedule into rounds with their contained games.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        List of dicts, each with 'round' (str) and 'games' (List[ScheduleEntry]),
        ordered by first appearance in the schedule. Empty list if no schedule cached.
    """
    schedule = load_schedule(db_dir, season_id)
    if schedule is None:
        return []

    rounds_order: List[str] = []
    rounds_map: Dict[str, List[ScheduleEntry]] = {}

    for entry in schedule:
        round_key = entry.round or ""
        if round_key not in rounds_map:
            rounds_order.append(round_key)
            rounds_map[round_key] = []
        rounds_map[round_key].append(entry)

    return [{"round": r, "games": rounds_map[r]} for r in rounds_order]


def get_standings(season_id: int, db_dir: Path) -> List[StandingsRow]:
    """Compute standings from all played games in the cached schedule.

    Loads all games referenced by the schedule in a single batch query
    and calculates the standings table.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        Sorted list of StandingsRow dataclasses.
    """
    played = get_all_played_games(season_id, db_dir)
    game_ids = [
        int(m.group(1))
        for entry in played
        if (m := re.search(r"/(\d+)$", entry.game_url))
    ]
    games = load_games_batch(db_dir, game_ids)
    return calculate_standings(games)


fetchSchedule = fetch_schedule
getGamesForDate = get_games_for_date
getAllPlayedGames = get_all_played_games
getSchedule = get_schedule
getStandings = get_standings
