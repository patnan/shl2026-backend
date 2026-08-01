import pytest

from src.shl.standings import CalculateStandingsError
from src.shl.api import calculate_standings
from src.shl.models import Game, StandingsRow
from tests.helpers import (
    ParseOverviewStandingsError,
    compare_standings,
    parse_overview_standings_html,
)


def make_game(home, away, home_score, away_score, state, is_overtime=False, is_shootout=False):
    return Game.from_dict({
        "game": {"home_team": home, "away_team": away, "is_overtime": is_overtime, "is_shootout": is_shootout},
        "score": {"current": f"{home_score}-{away_score}", "home_score": home_score, "away_score": away_score, "state": state},
    })


def test_calculate_standings_applies_regulation_overtime_and_unfinished_points():
  standings = calculate_standings([
    make_game("A", "B", 4, 1, "Final Score"),
    make_game("B", "C", 3, 2, "Final Score", is_overtime=True),
    make_game("C", "B", 2, 1, "Final Score", is_overtime=True, is_shootout=True),
    make_game("C", "A", 1, 1, None),
  ])

  assert standings == [
    StandingsRow(
      team="A", rank=1, games_played=2,
      goals_for=5, goals_against=2, goal_difference=3,
      w=1, t=0, l=0, tp=4, otw=0, otl=0, gwsw=0, gwsl=0,
    ),
    StandingsRow(
      team="C", rank=2, games_played=3,
      goals_for=5, goals_against=5, goal_difference=0,
      w=0, t=2, l=0, tp=4, otw=0, otl=1, gwsw=1, gwsl=0,
    ),
    StandingsRow(
      team="B", rank=3, games_played=3,
      goals_for=5, goals_against=8, goal_difference=-3,
      w=0, t=2, l=1, tp=3, otw=1, otl=0, gwsw=0, gwsl=1,
    ),
  ]


def test_calculate_standings_raises_for_invalid_game_shape():
  with pytest.raises(CalculateStandingsError):
    calculate_standings(["not a game"])


def test_parse_overview_standings_html_and_compare_matches_calculated_shape():
  html = """
<html><body>
  <table class="tblContent" width="100%">
    <tr>
      <td class="tdTitle" colspan="3"><h2>Group Standings</h2></td>
      <th class="tdTitleRight" colspan="8">1 Rounds (1 Games)</th>
    </tr>
    <tr>
      <th>RK</th><th>Team</th><th>GP</th><th>W</th><th>T</th><th>L</th><th>GF:GA (GD)</th><th>TP</th><th>OTW</th><th>OTL</th><th>GWSW</th><th>GWSL</th>
    </tr>
    <tr>
      <td>1</td><td>A</td><td>1</td><td>1</td><td>0</td><td>0</td><td>4:1 (3)</td><td>3</td><td>0</td><td>0</td><td>0</td><td>0</td>
    </tr>
    <tr>
      <td>2</td><td>B</td><td>1</td><td>0</td><td>0</td><td>1</td><td>1:4 (-3)</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td>
    </tr>
  </table>
</body></html>
"""

  overview = parse_overview_standings_html(html)
  calculated = calculate_standings([
    make_game("A", "B", 4, 1, "Final Score"),
  ])

  assert overview == [
    StandingsRow(rank=1, team="A", games_played=1, w=1, t=0, l=0, goals_for=4, goals_against=1, goal_difference=3, tp=3, otw=0, otl=0, gwsw=0, gwsl=0),
    StandingsRow(rank=2, team="B", games_played=1, w=0, t=0, l=1, goals_for=1, goals_against=4, goal_difference=-3, tp=0, otw=0, otl=0, gwsw=0, gwsl=0),
  ]
  assert compare_standings(calculated, overview) == []


def test_parse_overview_standings_html_raises_when_group_standings_missing():
  with pytest.raises(ParseOverviewStandingsError, match="Group Standings heading was not found"):
    parse_overview_standings_html("<html><body><p>no table</p></body></html>")
