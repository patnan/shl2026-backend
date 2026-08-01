import json

import pytest

from src.shl.game import CompareGameScoreChangeError
from src.shl.api import compare_game_score_change
from src.shl.models import Game, ScoringEvent
from tests.helpers import compare_game_score_change_from_files, LoadGameObjectFromFileError


def cmp(prev_dict, curr_dict):
    return compare_game_score_change(Game.from_dict(prev_dict), Game.from_dict(curr_dict))

from src.shl.models import ScoreChangeResult, ScoringEvent

def test_compare_game_score_change_detects_scoring_team_from_current_scores():
  previous = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "1-1"},
  }
  current = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "2-1"},
  }

  result = cmp(previous, current)
  assert result == ScoreChangeResult(
    scored=True,
    teams_scored=[
      ScoringEvent(team="Brynäs IF", goals_added=1, scorer=None, scorer_players=None, game_time=None)
    ],
    score="2-1",
    previous_score="1-1",
  )


def test_compare_game_score_change_supports_final_score_shape():
  previous = {
    "game": {"home_team": "Brynäs IF", "away_team": "Örebro HK"},
    "score": {"current": "3-3", "home_score": 3, "away_score": 3},
  }
  current = {
    "game": {"home_team": "Brynäs IF", "away_team": "Örebro HK"},
    "score": {"current": "4-3", "home_score": 4, "away_score": 3},
  }

  result = cmp(previous, current)
  assert result.scored is True
  assert result.teams_scored == [
    ScoringEvent(team="Brynäs IF", goals_added=1, scorer=None, scorer_players=None, game_time=None)
  ]
  assert result.score == "4-3"


def test_compare_game_score_change_reports_no_score_change():
  previous = {
    "game": {"home_team": "A", "away_team": "B"},
    "score": {"home_score": 2, "away_score": 1},
  }
  current = {
    "game": {"home_team": "A", "away_team": "B"},
    "score": {"home_score": 2, "away_score": 1},
  }

  result = cmp(previous, current)
  assert result == ScoreChangeResult(
    scored=False,
    teams_scored=[],
    score="2-1",
    previous_score="2-1",
  )


def test_compare_game_score_change_from_files_loads_two_dicts_and_compares(tmp_path):
  previous_file = tmp_path / "prev.json"
  current_file = tmp_path / "curr.json"

  previous_file.write_text(
    json.dumps({"game": {"home_team": "A", "away_team": "B"}, "score": {"current": "0-0"}}),
    encoding="utf-8",
  )
  current_file.write_text(
    json.dumps({"game": {"home_team": "A", "away_team": "B"}, "score": {"current": "0-1"}}),
    encoding="utf-8",
  )

  result = compare_game_score_change_from_files(str(previous_file), str(current_file))
  assert result.scored is True
  assert result.teams_scored == [
    ScoringEvent(team="B", goals_added=1, scorer=None, scorer_players=None, game_time=None)
  ]
  assert result.score == "0-1"


def test_load_game_object_from_file_raises_for_non_object(tmp_path):
  f = tmp_path / "bad.json"
  f.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

  from tests.helpers import load_game_object_from_file
  with pytest.raises(LoadGameObjectFromFileError, match="does not contain a JSON object"):
    load_game_object_from_file(str(f))


def test_compare_game_score_change_returns_scorer_and_time_from_actions():
  previous = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "1-1"},
    "actions": [
      {
        "game_time": "10:00",
        "event_type": "goal",
        "player_text": "11. Home, Player",
        "players": ["11. Home, Player"],
        "goal": {"home_score": 1, "away_score": 0},
      },
      {
        "game_time": "12:00",
        "event_type": "goal",
        "player_text": "21. Away, Player",
        "players": ["21. Away, Player"],
        "goal": {"home_score": 1, "away_score": 1},
      },
    ],
  }

  current = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "2-1"},
    "actions": [
      {
        "game_time": "10:00",
        "event_type": "goal",
        "player_text": "11. Home, Player",
        "players": ["11. Home, Player"],
        "goal": {"home_score": 1, "away_score": 0},
      },
      {
        "game_time": "12:00",
        "event_type": "goal",
        "player_text": "21. Away, Player",
        "players": ["21. Away, Player"],
        "goal": {"home_score": 1, "away_score": 1},
      },
      {
        "game_time": "15:34",
        "event_type": "goal",
        "player_text": "19. Kinnvall, Oskar",
        "players": ["19. Kinnvall, Oskar"],
        "goal": {"home_score": 2, "away_score": 1},
      },
    ],
  }

  result = cmp(previous, current)
  assert result.teams_scored == [
    ScoringEvent(
      team="Brynäs IF",
      goals_added=1,
      scorer="19. Kinnvall, Oskar",
      scorer_players=["19. Kinnvall, Oskar"],
      game_time="15:34",
    )
  ]


def test_compare_game_score_change_returns_scorer_and_time_from_new_non_goal_action():
  previous = {
    "game": {"home_team": "Brynäs IF", "away_team": "Örebro HK"},
    "score": {"final": "3-3"},
    "actions": [
      {
        "period": "period 4",
        "game_time": "63:01",
        "event_type": "",
        "team_abbrev": "ÖHK",
        "player_text": "Team penalty PenaltyShot",
        "players": ["Team penalty PenaltyShot"],
      }
    ],
  }

  current = {
    "game": {"home_team": "Brynäs IF", "away_team": "Örebro HK"},
    "score": {"final": "4-3"},
    "actions": [
      {
        "period": "period 4",
        "game_time": "63:01",
        "event_type": "PS",
        "team_abbrev": "BIF",
        "player_text": "33. Silfverberg, Jakob Missed Penalty Shot Saved By 1. Enroth, Jhonas",
        "players": [
          "33. Silfverberg, Jakob Missed Penalty Shot Saved By",
          "1. Enroth, Jhonas",
        ],
      },
      {
        "period": "period 4",
        "game_time": "63:01",
        "event_type": "",
        "team_abbrev": "ÖHK",
        "player_text": "Team penalty PenaltyShot",
        "players": ["Team penalty PenaltyShot"],
      },
    ],
  }

  result = cmp(previous, current)
  assert result.teams_scored == [
    ScoringEvent(
      team="Brynäs IF",
      goals_added=1,
      scorer="33. Silfverberg, Jakob Missed Penalty Shot Saved By 1. Enroth, Jhonas",
      scorer_players=[
        "33. Silfverberg, Jakob Missed Penalty Shot Saved By",
        "1. Enroth, Jhonas",
      ],
      game_time="63:01",
    )
  ]


def test_compare_game_score_change_detects_new_scored_game_winning_shot_without_main_score_change():
  previous = {
    "game": {"home_team": "Brynäs IF", "away_team": "Örebro HK"},
    "score": {"current": "3-3"},
    "actions": [
      {
        "period": "period 5",
        "game_time": "65:00",
        "event_type": "GWS",
        "team_abbrev": "ÖHK",
        "player_text": "21. Puistola, Patrik vs. goalie 45. Clara, Damian",
        "players": ["21. Puistola, Patrik", "45. Clara, Damian"],
        "is_goal": False,
        "shot_outcome": "missed",
      }
    ],
  }

  current = {
    "game": {"home_team": "Brynäs IF", "away_team": "Örebro HK"},
    "score": {"current": "3-3"},
    "actions": [
      {
        "period": "period 5",
        "game_time": "65:00",
        "event_type": "GWS",
        "team_abbrev": "BIF",
        "player_text": "52. Kopacka, Jack vs. goalie 1. Enroth, Jhonas",
        "players": ["52. Kopacka, Jack", "1. Enroth, Jhonas"],
        "is_goal": True,
        "shot_outcome": "scored",
      },
      {
        "period": "period 5",
        "game_time": "65:00",
        "event_type": "GWS",
        "team_abbrev": "ÖHK",
        "player_text": "21. Puistola, Patrik vs. goalie 45. Clara, Damian",
        "players": ["21. Puistola, Patrik", "45. Clara, Damian"],
        "is_goal": False,
        "shot_outcome": "missed",
      },
    ],
  }

  result = cmp(previous, current)
  assert result.scored is True
  assert result.teams_scored == [
    ScoringEvent(
      team="Brynäs IF",
      goals_added=1,
      scorer="52. Kopacka, Jack vs. goalie 1. Enroth, Jhonas",
      scorer_players=["52. Kopacka, Jack", "1. Enroth, Jhonas"],
      game_time="65:00",
    )
  ]


def test_compare_game_score_change_raises_when_score_is_missing():
  with pytest.raises(CompareGameScoreChangeError):
    compare_game_score_change(
      Game.from_dict({"game": {"home_team": "A", "away_team": "B"}, "score": {"current": "0-0"}}),
      "not a game",
    )


def test_compare_game_score_change_regulation_goal_with_scorer():
  previous = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "0-0"},
    "actions": [],
  }
  current = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "1-0"},
    "actions": [
      {
        "period": "1st period",
        "game_time": "08:42",
        "event_type": "goal",
        "player_text": "19. Kinnvall, Oskar",
        "players": ["19. Kinnvall, Oskar"],
        "goal": {"home_score": 1, "away_score": 0, "strength": "EQ", "qualifier": None},
      },
    ],
  }

  result = cmp(previous, current)
  assert result.scored is True
  assert result.teams_scored == [
    ScoringEvent(
      team="Brynäs IF",
      goals_added=1,
      scorer="19. Kinnvall, Oskar",
      scorer_players=["19. Kinnvall, Oskar"],
      game_time="08:42",
    )
  ]


def test_compare_game_score_change_overtime_goal_with_scorer():
  previous = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "2-2"},
    "actions": [],
  }
  current = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "3-2"},
    "actions": [
      {
        "period": "period 4",
        "game_time": "63:15",
        "event_type": "goal",
        "player_text": "19. Kinnvall, Oskar",
        "players": ["19. Kinnvall, Oskar"],
        "goal": {"home_score": 3, "away_score": 2, "strength": "OT", "qualifier": None},
      },
    ],
  }

  result = cmp(previous, current)
  assert result.scored is True
  assert result.teams_scored == [
    ScoringEvent(
      team="Brynäs IF",
      goals_added=1,
      scorer="19. Kinnvall, Oskar",
      scorer_players=["19. Kinnvall, Oskar"],
      game_time="63:15",
    )
  ]


def test_compare_game_score_change_penalty_shot_goal():
  previous = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "1-1"},
    "actions": [],
  }
  current = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "2-1"},
    "actions": [
      {
        "period": "2nd period",
        "game_time": "32:10",
        "event_type": "PS",
        "player_text": "19. Kinnvall, Oskar",
        "players": ["19. Kinnvall, Oskar"],
        "is_goal": True,
      },
    ],
  }

  result = cmp(previous, current)
  assert result.scored is True
  assert result.teams_scored[0].team == "Brynäs IF"
  assert result.teams_scored[0].game_time == "32:10"


def test_compare_game_score_change_missed_penalty_shot_no_goal():
  previous = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "1-1"},
    "actions": [],
  }
  current = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "1-1"},
    "actions": [
      {
        "period": "2nd period",
        "game_time": "32:10",
        "event_type": "PS",
        "player_text": "19. Kinnvall, Oskar Missed Penalty Shot Saved By 1. Enroth, Jhonas",
        "players": ["19. Kinnvall, Oskar Missed Penalty Shot Saved By", "1. Enroth, Jhonas"],
        "is_goal": False,
      },
    ],
  }

  result = cmp(previous, current)
  assert result.scored is False
  assert result.teams_scored == []


def test_compare_game_score_change_multiple_goals_in_diff():
  previous = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "1-1"},
    "actions": [],
  }
  current = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF"},
    "score": {"current": "3-2"},
    "actions": [
      {
        "period": "2nd period",
        "game_time": "25:00",
        "event_type": "goal",
        "player_text": "19. Kinnvall, Oskar",
        "players": ["19. Kinnvall, Oskar"],
        "goal": {"home_score": 2, "away_score": 1, "strength": "EQ", "qualifier": None},
      },
      {
        "period": "2nd period",
        "game_time": "27:30",
        "event_type": "goal",
        "player_text": "21. Away, Player",
        "players": ["21. Away, Player"],
        "goal": {"home_score": 2, "away_score": 2, "strength": "EQ", "qualifier": None},
      },
      {
        "period": "2nd period",
        "game_time": "29:15",
        "event_type": "goal",
        "player_text": "28. Kloos, Justin",
        "players": ["28. Kloos, Justin"],
        "goal": {"home_score": 3, "away_score": 2, "strength": "PP1", "qualifier": None},
      },
    ],
  }

  result = cmp(previous, current)
  assert result.scored is True
  assert len(result.teams_scored) == 2
  home = next(t for t in result.teams_scored if t.team == "Brynäs IF")
  away = next(t for t in result.teams_scored if t.team == "Luleå HF")
  assert home.goals_added == 2
  assert away.goals_added == 1
