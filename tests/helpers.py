import dataclasses
import json
from pathlib import Path
from typing import List

from src.shl.game import compare_game_score_change, CompareGameScoreChangeError
from src.shl.models import Game, ScoreChangeResult, StandingsRow
from src.shl.standings import parse_overview_standings_html, ParseOverviewStandingsError


class LoadGameObjectFromFileError(RuntimeError):
    pass


def load_game_object_from_file(file_path: str) -> Game:
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise LoadGameObjectFromFileError(f"File '{file_path}' does not contain a JSON object")
        return Game.from_dict(data)
    except LoadGameObjectFromFileError:
        raise
    except Exception as exc:
        raise LoadGameObjectFromFileError(f"load_game_object_from_file failed for '{file_path}': {exc}") from exc


def compare_game_score_change_from_files(previous_file_path: str, current_file_path: str) -> ScoreChangeResult:
    previous_game = load_game_object_from_file(previous_file_path)
    current_game = load_game_object_from_file(current_file_path)
    return compare_game_score_change(previous_game, current_game)


def compare_standings(calculated: List[StandingsRow], overview: List[StandingsRow]) -> List[dict]:
    comparison_fields = [
        "rank", "games_played", "w", "t", "l",
        "goals_for", "goals_against", "goal_difference",
        "tp", "otw", "otl", "gwsw", "gwsl",
    ]

    mismatches: List[Dict] = []
    calculated_by_team = {entry.team: dataclasses.asdict(entry) for entry in calculated}
    overview_by_team = {entry.team: dataclasses.asdict(entry) for entry in overview}

    for team in sorted(set(calculated_by_team) | set(overview_by_team)):
        calc = calculated_by_team.get(team)
        over = overview_by_team.get(team)

        if calc is None or over is None:
            mismatches.append({"team": team, "field": "team_presence", "calculated": calc is not None, "overview": over is not None})
            continue

        for field in comparison_fields:
            if calc.get(field) != over.get(field):
                mismatches.append({"team": team, "field": field, "calculated": calc.get(field), "overview": over.get(field)})

    calculated_order = [e.team for e in calculated]
    overview_order = [e.team for e in overview]
    if calculated_order != overview_order:
        mismatches.append({"team": None, "field": "team_order", "calculated": calculated_order, "overview": overview_order})

    return mismatches
