"""Parsers for SweHockey player stats, goalie stats, and roster pages."""
from __future__ import annotations

import re
from typing import List

from bs4 import BeautifulSoup

from src.shl.models import GoalieStat, PlayerStat, RosterEntry


def _parse_int(value: str, default: int = 0) -> int:
    """Parse an integer from a string, returning default on failure."""
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return default


def _parse_float(value: str, default: float = 0.0) -> float:
    """Parse a float from a string, handling comma decimals."""
    try:
        return float(value.strip().replace(",", "."))
    except (ValueError, AttributeError):
        return default


def _parse_plus_minus(value: str) -> int:
    """Parse +/- from 'goals_for:goals_against' format (e.g. '53:36' -> +17)."""
    match = re.match(r"(\d+):(\d+)", value.strip())
    if match:
        return int(match.group(1)) - int(match.group(2))
    # Try plain integer
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return 0


def parse_scoring_leaders(html: str) -> List[PlayerStat]:
    """Parse the ScoringLeaders page into a list of PlayerStat.

    Looks for the table with class 'tblContent' containing columns:
    Rk, No, Name, Team, Pos, GP, G, A, TP, AVG., PIM, +/-
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="tblContent")
    if not table:
        return []

    results: List[PlayerStat] = []
    rows = table.find_all("tr")

    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cells) < 12:
            continue
        # Skip header rows (first cell would be "Rk" or non-numeric)
        if not cells[0].isdigit():
            continue

        results.append(PlayerStat(
            rank=_parse_int(cells[0]),
            jersey=_parse_int(cells[1]),
            name=cells[2],
            team=cells[3],
            position=cells[4],
            games_played=_parse_int(cells[5]),
            goals=_parse_int(cells[6]),
            assists=_parse_int(cells[7]),
            total_points=_parse_int(cells[8]),
            points_per_game=_parse_float(cells[9]),
            penalty_minutes=_parse_int(cells[10]),
            plus_minus=_parse_plus_minus(cells[11]),
        ))

    return results


def parse_leading_goalies(html: str) -> List[GoalieStat]:
    """Parse the LeadingGoaliesSVS page into a list of GoalieStat.

    Looks for the table with class 'tblContent' containing columns:
    Rk, No, Name, Team, GP, GPI, MIP, SOG, GA, GAA, SVS, SVS%, SO, W, L, W%
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="tblContent")
    if not table:
        return []

    results: List[GoalieStat] = []
    rows = table.find_all("tr")
    rank_counter = 0

    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cells) < 16:
            continue
        # Skip header rows
        if cells[1] == "No" or cells[2] == "Name":
            continue
        # Data rows have a jersey number in cells[1]
        if not cells[1].isdigit():
            continue

        # Rank may be empty for lower-ranked goalies; use sequential counter
        if cells[0].isdigit():
            rank_counter = _parse_int(cells[0])
        else:
            rank_counter += 1

        results.append(GoalieStat(
            rank=rank_counter,
            jersey=_parse_int(cells[1]),
            name=cells[2],
            team=cells[3],
            games_played=_parse_int(cells[4]),
            games_played_in=_parse_int(cells[5]),
            minutes_in_play=cells[6],
            shots_on_goal=_parse_int(cells[7]),
            goals_against=_parse_int(cells[8]),
            goals_against_avg=_parse_float(cells[9]),
            saves=_parse_int(cells[10]),
            save_percentage=_parse_float(cells[11]),
            shutouts=_parse_int(cells[12]),
            wins=_parse_int(cells[13]),
            losses=_parse_int(cells[14]),
            win_percentage=_parse_float(cells[15]),
        ))

    return results


def parse_team_rosters(html: str) -> List[RosterEntry]:
    """Parse the TeamRoster page into a list of RosterEntry.

    The page has one tblContent table per team. Each table starts with
    the team name row, a 'Team Roster' row, a header row, then player rows.
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="tblContent")
    if not tables:
        return []

    results: List[RosterEntry] = []
    seen_teams: set = set()

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # First row contains the team name
        first_cells = [td.get_text(strip=True) for td in rows[0].find_all(["td", "th"])]
        if not first_cells:
            continue

        # Team name is the first non-empty cell (skip duplicates and '[Top]')
        team_name = ""
        for cell_text in first_cells:
            if cell_text and cell_text != "[Top]" and "Team Roster" not in cell_text and "Team Officials" not in cell_text:
                team_name = cell_text
                break

        if not team_name:
            continue

        # Skip Team Officials tables
        row_texts = " ".join(td.get_text(strip=True) for td in rows[1].find_all(["td", "th"])) if len(rows) > 1 else ""
        if "Team Officials" in row_texts:
            continue

        # Skip duplicate tables for same team
        if team_name in seen_teams:
            continue
        seen_teams.add(team_name)

        # Parse player rows (skip header rows)
        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < 9:
                continue
            # Player rows start with a jersey number
            if not cells[0].isdigit():
                continue

            results.append(RosterEntry(
                team=team_name,
                jersey=_parse_int(cells[0]),
                name=cells[1],
                birthdate=cells[2],
                position=cells[3],
                handedness=cells[4],
                height=_parse_int(cells[5]),
                weight=_parse_int(cells[6]),
                nationality=cells[7],
                youth_club=cells[8] if len(cells) > 8 else "",
            ))

    return results
