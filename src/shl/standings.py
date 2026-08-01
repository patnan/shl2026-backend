import re
from pathlib import Path
from typing import List

from src.shl.helpers.extraction import fetch_html
from src.shl.helpers.parsing import clean_text
from src.shl.models import Game, StandingsRow
from src.shl.store import load_standings, save_standings


class CalculateStandingsError(RuntimeError):
    pass


class FetchTableError(RuntimeError):
    pass


class ParseOverviewStandingsError(RuntimeError):
    pass


def parse_overview_standings_html(html: str) -> List[StandingsRow]:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        heading = soup.find("h2", string=lambda value: value and clean_text(value) == "Group Standings")
        if heading is None:
            raise ParseOverviewStandingsError("Group Standings heading was not found")

        table = heading.find_parent("table", class_="tblContent")
        if table is None:
            raise ParseOverviewStandingsError("Group Standings table was not found")

        rows = table.find_all("tr", recursive=False)
        standings: List[StandingsRow] = []

        for row in rows:
            cells = row.find_all("td", recursive=False)
            if len(cells) < 12:
                continue

            values = [clean_text(cell.get_text(" ", strip=True)) for cell in cells]
            gf_ga_match = re.match(r"(\d+):(\d+)\s*\((-?\d+)\)", values[6])
            if gf_ga_match is None:
                raise ParseOverviewStandingsError(
                    f"Could not parse GF:GA (GD) value '{values[6]}' for team '{values[1]}'"
                )

            has_mobile_goal_difference_cell = len(values) >= 13
            tp_index = 8 if has_mobile_goal_difference_cell else 7
            otw_index = tp_index + 1
            otl_index = tp_index + 2
            gwsw_index = tp_index + 3
            gwsl_index = tp_index + 4

            standings.append(StandingsRow(
                rank=int(values[0]),
                team=values[1],
                games_played=int(values[2]),
                w=int(values[3]),
                t=int(values[4]),
                l=int(values[5]),
                goals_for=int(gf_ga_match.group(1)),
                goals_against=int(gf_ga_match.group(2)),
                goal_difference=int(gf_ga_match.group(3)),
                tp=int(values[tp_index]),
                otw=int(values[otw_index]),
                otl=int(values[otl_index]),
                gwsw=int(values[gwsw_index]),
                gwsl=int(values[gwsl_index]),
            ))

        if not standings:
            raise ParseOverviewStandingsError("No standings rows were found in Group Standings table")

        return standings
    except ParseOverviewStandingsError:
        raise
    except Exception as exc:
        raise ParseOverviewStandingsError(f"parse_overview_standings_html failed: {exc}") from exc



def calculate_standings(games: List[Game]) -> List[StandingsRow]:
    try:
        standings: Dict[str, Dict] = {}

        def ensure_team(team_name: str) -> Dict:
            if team_name not in standings:
                standings[team_name] = {
                    "rank": 0,
                    "team": team_name,
                    "games_played": 0,
                    "wins_regulation": 0,
                    "wins_overtime": 0,
                    "wins_shootout": 0,
                    "wins_overtime_or_shootout": 0,
                    "losses_regulation": 0,
                    "losses_overtime": 0,
                    "losses_shootout": 0,
                    "losses_overtime_or_shootout": 0,
                    "tied_after_regulation": 0,
                    "unfinished_games": 0,
                    "points": 0,
                    "goals_for": 0,
                    "goals_against": 0,
                    "goal_difference": 0,
                    "w": 0,
                    "t": 0,
                    "l": 0,
                    "tp": 0,
                    "otw": 0,
                    "otl": 0,
                    "gwsw": 0,
                    "gwsl": 0,
                }
            return standings[team_name]

        for game in games:
            if not isinstance(game, Game):
                raise CalculateStandingsError("Each item must be a Game instance")
            game_info = game.game
            score_info = game.score

            home_team = game_info.home_team
            away_team = game_info.away_team
            home_score = score_info.home_score
            away_score = score_info.away_score

            if not isinstance(home_team, str) or not isinstance(away_team, str):
                raise CalculateStandingsError("Each game must include string home_team and away_team values")
            if not isinstance(home_score, int) or not isinstance(away_score, int):
                raise CalculateStandingsError("Each game must include integer home_score and away_score values")

            home_entry = ensure_team(home_team)
            away_entry = ensure_team(away_team)

            home_entry["games_played"] += 1
            away_entry["games_played"] += 1
            home_entry["goals_for"] += home_score
            home_entry["goals_against"] += away_score
            away_entry["goals_for"] += away_score
            away_entry["goals_against"] += home_score

            is_finished = score_info.state == "Final Score"
            is_extra_time = game_info.is_overtime or game_info.is_shootout

            if not is_finished or home_score == away_score:
                home_entry["unfinished_games"] += 1
                away_entry["unfinished_games"] += 1
                home_entry["points"] += 1
                away_entry["points"] += 1
                continue

            winner_entry = home_entry if home_score > away_score else away_entry
            loser_entry = away_entry if home_score > away_score else home_entry

            if is_extra_time:
                home_entry["tied_after_regulation"] += 1
                away_entry["tied_after_regulation"] += 1
                winner_entry["wins_overtime_or_shootout"] += 1
                loser_entry["losses_overtime_or_shootout"] += 1
                winner_entry["points"] += 2
                loser_entry["points"] += 1

                if game_info.is_shootout:
                    winner_entry["wins_shootout"] += 1
                    loser_entry["losses_shootout"] += 1
                else:
                    winner_entry["wins_overtime"] += 1
                    loser_entry["losses_overtime"] += 1
            else:
                winner_entry["wins_regulation"] += 1
                loser_entry["losses_regulation"] += 1
                winner_entry["points"] += 3

        for entry in standings.values():
            entry["goal_difference"] = entry["goals_for"] - entry["goals_against"]

        sorted_standings = sorted(
            standings.values(),
            key=lambda entry: (
                -entry["points"],
                -entry["goal_difference"],
                -entry["goals_for"],
                entry["team"],
            ),
        )

        for index, entry in enumerate(sorted_standings, start=1):
            entry["rank"] = index
            entry["w"] = entry["wins_regulation"]
            entry["t"] = entry["tied_after_regulation"]
            entry["l"] = entry["losses_regulation"]
            entry["tp"] = entry["points"]
            entry["otw"] = entry["wins_overtime"]
            entry["otl"] = entry["losses_overtime"]
            entry["gwsw"] = entry["wins_shootout"]
            entry["gwsl"] = entry["losses_shootout"]

        return [StandingsRow.from_dict(e) for e in sorted_standings]
    except CalculateStandingsError:
        raise
    except Exception as exc:
        raise CalculateStandingsError(f"calculate_standings failed: {exc}") from exc


def fetch_table(season_id: int, db_dir: Path, force_reparse: bool = False) -> List[StandingsRow]:
    try:
        if not force_reparse:
            cached = load_standings(db_dir, season_id)
            if cached is not None:
                return cached

        url = f"https://stats.swehockey.se/ScheduleAndResults/Overview/{season_id}"
        html = fetch_html(url)
        standings = parse_overview_standings_html(html)
        save_standings(db_dir, season_id, standings)
        return standings
    except Exception as exc:
        raise FetchTableError(f"fetch_table failed for season '{season_id}': {exc}") from exc


fetchTable = fetch_table
