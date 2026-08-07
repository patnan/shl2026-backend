import re
from datetime import date, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.shl.helpers.extraction import (
    extract_live_games,
    extract_schedule_games,
)
from src.shl.models import ScheduleEntry, StandingsRow
from src.shl.store import load_live_games, load_schedule, load_standings, save_live_games, save_schedule


class FetchScheduleError(RuntimeError):
    pass


class GetGamesForDateError(RuntimeError):
    pass


class GetAllPlayedGamesError(RuntimeError):
    pass


class FetchLiveGamesError(RuntimeError):
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
        schedule, page_last_update = extract_schedule_games(url)
        save_schedule(db_dir, season_id, schedule, page_last_update)
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
    """Return all schedule entries that have a recorded result, up to and including yesterday.

    Only games with a date before today are included in standings calculation.
    Today's games (even if they have a result) are excluded to keep standings
    stable during game days.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        List of ScheduleEntry dataclasses with non-empty game_result and date < today.

    Raises:
        GetAllPlayedGamesError: If loading fails.
    """
    try:
        schedule = load_schedule(db_dir, season_id)
        if schedule is None:
            return []
        today_str = date.today().isoformat()
        return [entry for entry in schedule if entry.game_result and entry.date < today_str]
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
    """Compute standings from played schedule entries, with movement.

    Uses game results and overtime info directly from the schedule — no need
    to fetch individual game detail pages. Movement is calculated by comparing
    the current rank against the previously saved standings snapshot in the DB.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        Sorted list of StandingsRow dataclasses with movement set.
    """
    played = get_all_played_games(season_id, db_dir)
    standings = calculate_standings_from_schedule(played)

    # If no games played yet, build a placeholder table from the full schedule.
    if not standings:
        schedule = load_schedule(db_dir, season_id)
        if schedule:
            teams = sorted({
                t
                for entry in schedule
                for t in (entry.home_team, entry.away_team)
                if t
            })
            standings = [
                StandingsRow(
                    rank=1,
                    team=team,
                    games_played=0,
                    w=0, t=0, l=0,
                    goals_for=0, goals_against=0, goal_difference=0,
                    tp=0, otw=0, otl=0, gwsw=0, gwsl=0,
                )
                for team in teams
            ]
        return standings

    # Compute movement against previously saved standings.
    prev_standings = load_standings(db_dir, season_id)
    if prev_standings:
        prev_rank_by_team = {r.team: r.rank for r in prev_standings}
        standings = [
            StandingsRow(
                rank=r.rank,
                team=r.team,
                games_played=r.games_played,
                w=r.w,
                t=r.t,
                l=r.l,
                goals_for=r.goals_for,
                goals_against=r.goals_against,
                goal_difference=r.goal_difference,
                tp=r.tp,
                otw=r.otw,
                otl=r.otl,
                gwsw=r.gwsw,
                gwsl=r.gwsl,
                movement=r.rank - prev_rank_by_team.get(r.team, r.rank),
            )
            for r in standings
        ]

    return standings


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


def fetch_live_games(season_id: int, db_dir: Path) -> Tuple[List[ScheduleEntry], Optional[str]]:
    """Fetch today's live/upcoming games from the SweHockey Live page.

    Scrapes the Live page for the season and persists the result to the database.
    Unlike fetch_schedule, this always re-fetches (no cache check) because the
    live page changes frequently during game days.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        Tuple of (List of ScheduleEntry dataclasses for today's games,
        page_last_update timestamp or None).

    Raises:
        FetchLiveGamesError: If scraping or saving fails.
    """
    try:
        games, page_last_update = extract_live_games(season_id)
        save_live_games(db_dir, season_id, games, page_last_update)
        return games, page_last_update
    except Exception as exc:
        raise FetchLiveGamesError(f"fetch_live_games failed for season '{season_id}': {exc}") from exc


def get_live_games(season_id: int, db_dir: Path) -> Optional[List[ScheduleEntry]]:
    """Load the cached live games for a season, or None if not yet fetched."""
    return load_live_games(db_dir, season_id)


def get_live_points(season_id: int, db_dir: Path) -> Dict[str, int]:
    """Calculate provisional live points for each team from today's games.

    Scoring rules:
    - Game in progress with tied score: 0 points each (undecided).
    - Game in progress with leader (regulation): leader gets 3, loser gets 0.
    - Finished game in OT: winner 2, loser 1.
    - Finished game in SO: winner 2, loser 1.
    - Finished game in regulation: winner 3, loser 0.

    For in-progress games that are not tied, we assume regulation (3-0) since
    OT/SO can only be determined once the game ends. If the game is tied and
    in OT (4th period), both get 1 point provisionally.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        Dict mapping team name to provisional points from today's live games.
    """
    live = load_live_games(db_dir, season_id)
    if not live:
        return {}

    points: Dict[str, int] = {}

    for entry in live:
        if not entry.game_result or not entry.home_team or not entry.away_team:
            continue

        score_match = re.search(r"(\d+)\s*-\s*(\d+)", entry.game_result)
        if not score_match:
            continue

        home_score = int(score_match.group(1))
        away_score = int(score_match.group(2))
        ot = entry.overtime  # "OT", "SO", or ""

        home_team = entry.home_team
        away_team = entry.away_team
        points.setdefault(home_team, 0)
        points.setdefault(away_team, 0)

        if home_score == away_score:
            # Tied — if in OT/SO period, both get at least 1 point.
            period_count = len(re.findall(r"\d+-\d+", entry.periods)) if entry.periods else 0
            if period_count >= 4:
                points[home_team] += 1
                points[away_team] += 1
        elif home_score > away_score:
            if ot == "OT" or ot == "SO":
                points[home_team] += 2
                points[away_team] += 1
            else:
                points[home_team] += 3
        else:
            if ot == "OT" or ot == "SO":
                points[away_team] += 2
                points[home_team] += 1
            else:
                points[away_team] += 3

    return points


def get_live_standings(season_id: int, db_dir: Path) -> List[StandingsRow]:
    """Combine base standings with today's live points into a live standings table.

    Merges the static standings (games up to yesterday) with provisional live
    points from today's games, re-ranks, and calculates movement compared to
    the base standings rank.

    Movement convention: negative = moved up, positive = moved down.

    Args:
        season_id: SweHockey season/tournament ID.
        db_dir: Path to the cache/database directory.

    Returns:
        Sorted list of StandingsRow with updated tp, rank, and movement.
    """
    standings = get_standings(season_id, db_dir)
    live_points = get_live_points(season_id, db_dir)

    if not standings:
        return []

    # Base rank from standings before today's games.
    base_rank_by_team = {r.team: r.rank for r in standings}

    # Merge live points into standings.
    merged = []
    for row in standings:
        extra = live_points.get(row.team, 0)
        merged.append(StandingsRow(
            rank=row.rank,
            team=row.team,
            games_played=row.games_played,
            w=row.w, t=row.t, l=row.l,
            goals_for=row.goals_for,
            goals_against=row.goals_against,
            goal_difference=row.goal_difference,
            tp=row.tp + extra,
            otw=row.otw, otl=row.otl,
            gwsw=row.gwsw, gwsl=row.gwsl,
        ))

    # Re-sort and re-rank.
    merged.sort(key=lambda r: (-r.tp, -r.goal_difference, -r.goals_for, r.team))
    return [
        StandingsRow(
            rank=i,
            team=r.team,
            games_played=r.games_played,
            w=r.w, t=r.t, l=r.l,
            goals_for=r.goals_for,
            goals_against=r.goals_against,
            goal_difference=r.goal_difference,
            tp=r.tp,
            otw=r.otw, otl=r.otl,
            gwsw=r.gwsw, gwsl=r.gwsl,
            movement=i - base_rank_by_team.get(r.team, i),
        )
        for i, r in enumerate(merged, start=1)
    ]


def compare_live_standings(
    previous: List[StandingsRow], current: List[StandingsRow]
) -> List[Dict]:
    """Compare two live standings snapshots and detect position changes.

    Args:
        previous: Previous live standings snapshot.
        current: Current live standings snapshot.

    Returns:
        List of dicts describing changes:
        [{"team": str, "prev_rank": int, "new_rank": int, "movement": int}, ...]
        Only teams that changed position are included.
    """
    prev_rank_by_team = {r.team: r.rank for r in previous}
    changes = []

    for row in current:
        prev_rank = prev_rank_by_team.get(row.team)
        if prev_rank is None:
            continue
        if prev_rank != row.rank:
            changes.append({
                "team": row.team,
                "prev_rank": prev_rank,
                "new_rank": row.rank,
                "movement": row.rank - prev_rank,
            })

    return changes


fetchSchedule = fetch_schedule
getGamesForDate = get_games_for_date
getAllPlayedGames = get_all_played_games
getSchedule = get_schedule
getStandings = get_standings
