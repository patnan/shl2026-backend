import json
import re
from pathlib import Path
from typing import Dict, List

from src.shl.helpers.parsing import clean_text
from src.shl.game import compare_game_score_change, CompareGameScoreChangeError


class LoadGameObjectFromFileError(RuntimeError):
    pass


def load_game_object_from_file(file_path: str) -> Dict[str, object]:
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise LoadGameObjectFromFileError(f"File '{file_path}' does not contain a JSON object")
        return data
    except LoadGameObjectFromFileError:
        raise
    except Exception as exc:
        raise LoadGameObjectFromFileError(f"load_game_object_from_file failed for '{file_path}': {exc}") from exc


def compare_game_score_change_from_files(previous_file_path: str, current_file_path: str) -> Dict[str, object]:
    previous_game = load_game_object_from_file(previous_file_path)
    current_game = load_game_object_from_file(current_file_path)
    return compare_game_score_change(previous_game, current_game)


class ParseOverviewStandingsError(RuntimeError):
    pass


def parse_overview_standings_html(html: str) -> List[Dict]:
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
        standings: List[Dict] = []

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

            standings.append(
                {
                    "rank": int(values[0]),
                    "team": values[1],
                    "games_played": int(values[2]),
                    "w": int(values[3]),
                    "t": int(values[4]),
                    "l": int(values[5]),
                    "goals_for": int(gf_ga_match.group(1)),
                    "goals_against": int(gf_ga_match.group(2)),
                    "goal_difference": int(gf_ga_match.group(3)),
                    "tp": int(values[tp_index]),
                    "otw": int(values[otw_index]),
                    "otl": int(values[otl_index]),
                    "gwsw": int(values[gwsw_index]),
                    "gwsl": int(values[gwsl_index]),
                }
            )

        if not standings:
            raise ParseOverviewStandingsError("No standings rows were found in Group Standings table")

        return standings
    except ParseOverviewStandingsError:
        raise
    except Exception as exc:
        raise ParseOverviewStandingsError(f"parse_overview_standings_html failed: {exc}") from exc


def compare_standings(calculated: List[Dict], overview: List[Dict]) -> List[Dict]:
    comparison_fields = [
        "rank", "games_played", "w", "t", "l",
        "goals_for", "goals_against", "goal_difference",
        "tp", "otw", "otl", "gwsw", "gwsl",
    ]

    mismatches: List[Dict] = []
    calculated_by_team = {entry["team"]: entry for entry in calculated}
    overview_by_team = {entry["team"]: entry for entry in overview}

    for team in sorted(set(calculated_by_team) | set(overview_by_team)):
        calc = calculated_by_team.get(team)
        over = overview_by_team.get(team)

        if calc is None or over is None:
            mismatches.append({"team": team, "field": "team_presence", "calculated": calc is not None, "overview": over is not None})
            continue

        for field in comparison_fields:
            if calc.get(field) != over.get(field):
                mismatches.append({"team": team, "field": field, "calculated": calc.get(field), "overview": over.get(field)})

    calculated_order = [e["team"] for e in calculated]
    overview_order = [e["team"] for e in overview]
    if calculated_order != overview_order:
        mismatches.append({"team": None, "field": "team_order", "calculated": calculated_order, "overview": overview_order})

    return mismatches
