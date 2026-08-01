import re
from pathlib import Path
from typing import Dict, List, Optional

from src.shl.helpers.extraction import (
    extract_schedule_games,
)
from src.shl.models import ScheduleEntry, StandingsRow
from src.shl.store import save_schedule, load_schedule, load_game
from src.shl.standings import calculate_standings


class FetchScheduleError(RuntimeError):
    pass


class GetGamesForDateError(RuntimeError):
    pass


class GetAllPlayedGamesError(RuntimeError):
    pass


def fetch_schedule(season_id: int, db_dir: Path, force_reparse: bool = False) -> List[ScheduleEntry]:
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
    try:
        schedule = load_schedule(db_dir, season_id)
        if schedule is None:
            return []
        return [entry for entry in schedule if entry.game_result]
    except Exception as exc:
        raise GetAllPlayedGamesError(f"get_all_played_games failed for season '{season_id}': {exc}") from exc


def get_schedule(season_id: int, db_dir: Path) -> Optional[List[ScheduleEntry]]:
    return load_schedule(db_dir, season_id)


def get_standings(season_id: int, db_dir: Path) -> List[StandingsRow]:
    played = get_all_played_games(season_id, db_dir)
    game_ids = [
        int(m.group(1))
        for entry in played
        if (m := re.search(r"/(\d+)$", entry.game_url))
    ]
    games = [g for game_id in game_ids if (g := load_game(db_dir, game_id)) is not None]
    return calculate_standings(games)


fetchSchedule = fetch_schedule
getGamesForDate = get_games_for_date
getAllPlayedGames = get_all_played_games
getSchedule = get_schedule
getStandings = get_standings
