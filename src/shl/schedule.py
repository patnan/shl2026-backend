import re
from datetime import date, timezone
from pathlib import Path
from typing import Dict, List, Optional

from src.shl.helpers.extraction import (
    extract_schedule_games,
)
from src.shl.models import ScheduleEntry, StandingsRow
from src.shl.store import save_schedule, load_schedule


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

    Rounds are determined by the 'round' field in the schedule entries.
    If no round info is available, rounds are inferred by date (all games
    on the same date belong to the same round, numbered sequentially).

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

    # Check if explicit round info exists.
    has_rounds = any(entry.round for entry in schedule)

    if has_rounds:
        rounds_order: List[str] = []
        rounds_map: Dict[str, List[ScheduleEntry]] = {}
        for entry in schedule:
            round_key = entry.round or ""
            if round_key not in rounds_map:
                rounds_order.append(round_key)
                rounds_map[round_key] = []
            rounds_map[round_key].append(entry)
        return [{"round": r, "games": rounds_map[r]} for r in rounds_order]

    # Infer rounds from dates: each unique date = one round, numbered sequentially.
    dates_order: List[str] = []
    dates_map: Dict[str, List[ScheduleEntry]] = {}
    for entry in schedule:
        d = entry.date
        if d not in dates_map:
            dates_order.append(d)
            dates_map[d] = []
        dates_map[d].append(entry)

    return [{"round": str(i), "games": dates_map[d]} for i, d in enumerate(dates_order, start=1)]


def get_played_rounds(season_id: int, db_dir: Path) -> List[Dict]:
    """Group only played games (those with a result) into rounds.

    Uses the same round logic as get_rounds (explicit round field or
    date-based inference), then filters to only include entries with results.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        List of dicts, each with 'round' (str) and 'games' (List[ScheduleEntry]),
        containing only entries with a game_result. Rounds with no played games
        are excluded. Empty list if no schedule cached.
    """
    all_rounds = get_rounds(season_id, db_dir)
    result = []
    for r in all_rounds:
        played = [e for e in r["games"] if e.game_result]
        if played:
            result.append({"round": r["round"], "games": played})
    return result


def get_next_round(season_id: int, db_dir: Path) -> Optional[Dict]:
    """Get the next round to be played (first round with any unplayed game).

    Uses the same round logic as get_rounds (explicit round field or
    date-based inference).

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        Dict with 'round' (str) and 'games' (List[ScheduleEntry]) for the
        next unplayed round, or None if all rounds are complete or no schedule cached.
    """
    all_rounds = get_rounds(season_id, db_dir)
    for r in all_rounds:
        if any(not entry.game_result for entry in r["games"]):
            return r
    return None


def get_todays_games(season_id: int, db_dir: Path, today: Optional[date] = None) -> List[ScheduleEntry]:
    """Return today's games that are upcoming or in progress (no final result yet).

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.
        today: Override for the current date (defaults to UTC today).

    Returns:
        List of ScheduleEntry for today without a game_result. Empty if none.
    """
    schedule = load_schedule(db_dir, season_id)
    if schedule is None:
        return []

    today_str = (today or date.today()).isoformat()
    return [
        entry for entry in schedule
        if entry.date == today_str and not entry.game_result
    ]


def get_standings(season_id: int, db_dir: Path) -> List[StandingsRow]:
    """Compute standings from played schedule entries.

    Uses game results and overtime info directly from the schedule — no need
    to fetch individual game detail pages.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        Sorted list of StandingsRow dataclasses.
    """
    played = get_all_played_games(season_id, db_dir)
    return calculate_standings_from_schedule(played)


def calculate_standings_from_schedule(entries: List[ScheduleEntry]) -> List[StandingsRow]:
    """Calculate league standings from schedule entries with results.

    SHL scoring rules:
    - Regulation win: 3 points
    - OT/SO win: 2 points
    - OT/SO loss: 1 point
    - Regulation loss: 0 points

    Args:
        entries: List of ScheduleEntry with game_result set.

    Returns:
        Sorted list of StandingsRow dataclasses with rank assigned.
    """
    standings: Dict[str, Dict] = {}

    def ensure_team(team_name: str) -> Dict:
        if team_name not in standings:
            standings[team_name] = {
                "team": team_name,
                "games_played": 0,
                "w": 0, "t": 0, "l": 0,
                "goals_for": 0, "goals_against": 0, "goal_difference": 0,
                "points": 0,
                "otw": 0, "otl": 0, "gwsw": 0, "gwsl": 0,
            }
        return standings[team_name]

    for entry in entries:
        if not entry.home_team or not entry.away_team or not entry.game_result:
            continue

        # Parse score from game_result (e.g. "2 - 3" or "4-7")
        score_match = re.search(r"(\d+)\s*-\s*(\d+)", entry.game_result)
        if not score_match:
            continue

        home_score = int(score_match.group(1))
        away_score = int(score_match.group(2))
        ot = entry.overtime  # "OT", "SO", or ""

        home = ensure_team(entry.home_team)
        away = ensure_team(entry.away_team)

        home["games_played"] += 1
        away["games_played"] += 1
        home["goals_for"] += home_score
        home["goals_against"] += away_score
        away["goals_for"] += away_score
        away["goals_against"] += home_score

        if home_score == away_score:
            # Shouldn't happen for finished games, but handle gracefully
            home["points"] += 1
            away["points"] += 1
            home["t"] += 1
            away["t"] += 1
        elif home_score > away_score:
            winner, loser = home, away
            if ot == "OT":
                winner["points"] += 2
                loser["points"] += 1
                winner["otw"] += 1
                loser["otl"] += 1
                winner["t"] += 1
                loser["t"] += 1
            elif ot == "SO":
                winner["points"] += 2
                loser["points"] += 1
                winner["gwsw"] += 1
                loser["gwsl"] += 1
                winner["t"] += 1
                loser["t"] += 1
            else:
                winner["points"] += 3
                winner["w"] += 1
                loser["l"] += 1
        else:
            winner, loser = away, home
            if ot == "OT":
                winner["points"] += 2
                loser["points"] += 1
                winner["otw"] += 1
                loser["otl"] += 1
                winner["t"] += 1
                loser["t"] += 1
            elif ot == "SO":
                winner["points"] += 2
                loser["points"] += 1
                winner["gwsw"] += 1
                loser["gwsl"] += 1
                winner["t"] += 1
                loser["t"] += 1
            else:
                winner["points"] += 3
                winner["w"] += 1
                loser["l"] += 1

    for entry in standings.values():
        entry["goal_difference"] = entry["goals_for"] - entry["goals_against"]

    sorted_standings = sorted(
        standings.values(),
        key=lambda e: (-e["points"], -e["goal_difference"], -e["goals_for"], e["team"]),
    )

    return [
        StandingsRow(
            rank=i,
            team=e["team"],
            games_played=e["games_played"],
            w=e["w"],
            t=e["t"],
            l=e["l"],
            goals_for=e["goals_for"],
            goals_against=e["goals_against"],
            goal_difference=e["goal_difference"],
            tp=e["points"],
            otw=e["otw"],
            otl=e["otl"],
            gwsw=e["gwsw"],
            gwsl=e["gwsl"],
        )
        for i, e in enumerate(sorted_standings, start=1)
    ]


fetchSchedule = fetch_schedule
getGamesForDate = get_games_for_date
getAllPlayedGames = get_all_played_games
getSchedule = get_schedule
getStandings = get_standings
