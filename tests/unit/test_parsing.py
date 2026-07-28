import json

import pytest

from src.shl.api import (
    ParseScoreBlockError,
    ParseTopStatsError,
    extract_penalty_metadata,
    parse_actions,
    parse_goal_event_type,
    parse_players,
    parse_score_block,
    parse_top_stats,
)


def build_page_html(score_cell: str) -> str:
    return f"""
<html>
  <body>
    <table id="top-stats">
      <tr><th>HV 71 - Växjö Lakers HC</th></tr>
      <tr>
        <td>2026-03-12 19:00</td>
        <td>SHL</td>
        <td>Husqvarna Garden</td>
      </tr>
      <tr>
        <td>Shots</td>
        <td><strong>24</strong></td>
        <td>(13:3:8)</td>
        <td>{score_cell}</td>
        <td>Shots</td>
        <td><strong>23</strong></td>
        <td>(4:12:7)</td>
      </tr>
      <tr>
        <td></td>
        <td>12,50%</td>
        <td></td>
        <td>0,00%</td>
      </tr>
      <tr>
        <td>Saves</td>
        <td><strong>23</strong></td>
        <td>(4:12:7)</td>
        <td>Saves</td>
        <td><strong>21</strong></td>
        <td>(13:2:6)</td>
      </tr>
      <tr>
        <td></td>
        <td>100,00%</td>
        <td></td>
        <td>87,50%</td>
      </tr>
      <tr>
        <td>PIM</td>
        <td><strong>4</strong></td>
        <td>(0:4:0)</td>
        <td>
          <table>
            <tr><td>Line Up</td><td>Actions</td><td>Reports</td></tr>
          </table>
        </td>
        <td>PIM</td>
        <td><strong>6</strong></td>
        <td>(2:2:2)</td>
      </tr>
      <tr>
        <td>PP</td>
        <td><strong>33,33%</strong></td>
        <td>(04:09)</td>
        <td>PP</td>
        <td><strong>0,00%</strong></td>
        <td>(03:04)</td>
      </tr>
    </table>

    <table id="actions">
      <tr>
        <th>Actions</th>
        <th>Last update: 2026-03-12 21:43:31</th>
      </tr>
      <tr><th>3rd period</th></tr>
      <tr>
        <td>59:35</td>
        <td>3-0 (PP1) ENG</td>
        <td>HV71</td>
        <td>28. Kloos, Justin Glenn (9) 27. Ang, Jonathan 70. Rousek, Lukas Pos. Part.: 27 , 28 , 30 , 55 , 61 , 70 Neg. Part.: 11 , 21 , 25 , 40 , 62</td>
        <td>ignored fifth column</td>
      </tr>
      <tr>
        <td>58:30</td>
        <td>2 min</td>
        <td>VÄX</td>
        <td>49. Sahlin Wallenius, Leo Crosschecking (58:30 - 59:35)</td>
      </tr>
      <tr><th>2nd period</th></tr>
      <tr>
        <td>27:52</td>
        <td>2 min</td>
        <td>VÄX</td>
        <td>Team penalty Too many players on the ice (27:52 - 29:52)</td>
      </tr>
    </table>
  </body>
</html>
"""


@pytest.mark.parametrize(
  (
    "score_cell",
    "expected_current",
    "expected_home_score",
    "expected_away_score",
    "expected_periods",
    "expected_current_period",
    "expected_state",
  ),
    [
        (
            "3 - 2 (2-1, 0-1, 1-0) Final Score Spectators: 7975",
      "3-2",
      3,
      2,
            ["2-1", "0-1", "1-0"],
      3,
            "Final Score",
        ),
        (
            "3 - 4 (0-1, 1-2, 2-0, 0-1) Final Score Spectators: 8240",
            "3-4",
      3,
      4,
            ["0-1", "1-2", "2-0", "0-1"],
            4,
            "Final Score",
        ),
        (
            "4 - 3 (2-1, 1-1, 0-1, 0-0, 1-0) Final Score Spectators: 5350",
            "4-3",
      4,
      3,
            ["2-1", "1-1", "0-1", "0-0", "1-0"],
            5,
            "Final Score",
        ),
    ],
)
def test_parse_score_block_variants(
    score_cell,
    expected_current,
    expected_home_score,
    expected_away_score,
    expected_periods,
    expected_current_period,
    expected_state,
):
    score = parse_score_block(score_cell)

    assert score["current"] == expected_current
    assert score["home_score"] == expected_home_score
    assert score["away_score"] == expected_away_score
    assert score["periods"] == expected_periods
    assert score["current_period"] == expected_current_period
    assert score["state"] == expected_state


@pytest.mark.parametrize(
    ("player_text", "expected_players", "expected_numbers"),
    [
        (
            "28. Kloos, Justin Glenn (9) 27. Ang, Jonathan 70. Rousek, Lukas Pos. Part.: 27 , 28 , 30 , 55 , 61 , 70 Neg. Part.: 11 , 21 , 25 , 40 , 62",
            [
                "28. Kloos, Justin Glenn (9)",
                "27. Ang, Jonathan",
                "70. Rousek, Lukas",
            ],
            [28, 27, 70],
        ),
        (
            "33. Silfverberg, Jakob Missed Penalty Shot Saved By 1. Enroth, Jhonas",
            [
                "33. Silfverberg, Jakob Missed Penalty Shot Saved By",
                "1. Enroth, Jhonas",
            ],
            [33, 1],
        ),
        (
            "Team penalty Too many players on the ice (27:52 - 29:52)",
            ["Team penalty Too many players on the ice (27:52 - 29:52)"],
            [],
        ),
    ],
)
def test_parse_players(player_text, expected_players, expected_numbers):
    players, numbers = parse_players(player_text)

    assert players == expected_players
    assert numbers == expected_numbers


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        (
            "3-0 (PP1) ENG",
          {"home_score": 3, "away_score": 0, "strength": "PP1", "qualifier": "ENG"},
        ),
        (
            "2-0 (EQ)",
          {"home_score": 2, "away_score": 0, "strength": "EQ", "qualifier": None},
        ),
        ("2 min", None),
        ("GK Out", None),
    ],
)
def test_parse_goal_event_type(event_type, expected):
    assert parse_goal_event_type(event_type) == expected


@pytest.mark.parametrize(
    ("score_cell", "expected_is_overtime", "expected_is_shootout"),
    [
        ("3 - 0 (0-0, 1-0, 2-0) Final Score Spectators: 5860", False, False),
        ("3 - 4 (0-1, 1-2, 2-0, 0-1) Final Score Spectators: 8240", True, False),
        ("4 - 3 (2-1, 1-1, 0-1, 0-0, 1-0) Final Score Spectators: 5350", True, True),
    ],
)
def test_parse_top_stats_game_flags(score_cell, expected_is_overtime, expected_is_shootout):
    html = build_page_html(score_cell)
    data = parse_top_stats(html)

    assert data["game"]["is_overtime"] == expected_is_overtime
    assert data["game"]["is_shootout"] == expected_is_shootout


def test_parse_top_stats_extracts_combined_team_stats():
    html = build_page_html("3 - 0 (0-0, 1-0, 2-0) Final Score Spectators: 5860")
    data = parse_top_stats(html)

    assert data["game"]["home_team"] == "HV 71"
    assert data["game"]["away_team"] == "Växjö Lakers HC"
    assert data["score"] == {
      "current": "3-0",
      "home_score": 3,
      "away_score": 0,
        "periods": ["0-0", "1-0", "2-0"],
      "current_period": 3,
        "state": "Final Score",
    }

    home = data["teams"]["HV 71"]
    away = data["teams"]["Växjö Lakers HC"]

    assert home["shots"] == {"total": 24, "by_period": [13, 3, 8], "percentage": "12,50%"}
    assert home["saves"] == {"total": 23, "by_period": [4, 12, 7], "percentage": "100,00%"}
    assert home["pim"] == {"total": 4, "by_period": [0, 4, 0]}
    assert home["pp"] == {"percentage": "33,33%", "time": "04:09"}

    assert away["shots"] == {"total": 23, "by_period": [4, 12, 7], "percentage": "0,00%"}
    assert away["saves"] == {"total": 21, "by_period": [13, 2, 6], "percentage": "87,50%"}
    assert away["pim"] == {"total": 6, "by_period": [2, 2, 2]}
    assert away["pp"] == {"percentage": "0,00%", "time": "03:04"}


def test_parse_actions_extracts_event_lines_as_json_objects():
    html = build_page_html("3 - 0 (0-0, 1-0, 2-0) Final Score Spectators: 5860")
    actions = parse_actions(html)

    assert len(actions) == 3

    first = actions[0]
    assert first["period"] == "3rd period"
    assert first["game_time"] == "59:35"
    assert first["event_type"] == "goal"
    assert first["event_detail"] == "3-0 (PP1) ENG"
    assert first["team_abbrev"] == "HV71"
    assert first["players"] == [
        "28. Kloos, Justin Glenn (9)",
        "27. Ang, Jonathan",
        "70. Rousek, Lukas",
    ]
    assert first["player_numbers"] == [28, 27, 70]
    assert first["is_goal"] is True
    assert first["goal"] == {
      "home_score": 3,
      "away_score": 0,
      "strength": "PP1",
      "qualifier": "ENG",
    }

    second = actions[1]
    assert second["period"] == "3rd period"
    assert second["event_type"] == "penalty"
    assert second["event_detail"] == "2 min"
    assert second["team_abbrev"] == "VÄX"
    assert second["player_text"] == "49. Sahlin Wallenius, Leo"
    assert second["players"] == ["49. Sahlin Wallenius, Leo"]
    assert second["player_numbers"] == [49]
    assert second["penalty_reason"] == "Crosschecking"
    assert second["penalty_time_range"] == {"start": "58:30", "end": "59:35"}
    assert second["is_goal"] is False
    assert "goal" not in second

    third = actions[2]
    assert third["period"] == "2nd period"
    assert third["team_abbrev"] == "VÄX"
    assert third["player_text"] == "Team penalty"
    assert third["players"] == []
    assert third["player_numbers"] == []
    assert third["penalty_reason"] == "Too many players on the ice"
    assert third["penalty_time_range"] == {"start": "27:52", "end": "29:52"}


def test_combined_output_shape_has_expected_keys():
    html = build_page_html("3 - 0 (0-0, 1-0, 2-0) Final Score Spectators: 5860")
    top = parse_top_stats(html)
    top["actions"] = parse_actions(html)

    payload = json.loads(json.dumps(top, ensure_ascii=False))
    assert set(payload.keys()) == {"game", "score", "teams", "actions"}
    assert isinstance(payload["actions"], list)
    assert payload["actions"][0]["game_time"] == "59:35"
    assert payload["actions"][0]["event_type"] == "goal"


def test_parse_score_block_without_final_score_label_sets_state_none():
    score = parse_score_block("1 - 0 (1-0, 0-0, 0-0) Spectators: 1000")
    assert score["current"] == "1-0"
    assert score["home_score"] == 1
    assert score["away_score"] == 0
    assert score["periods"] == ["1-0", "0-0", "0-0"]
    assert score["current_period"] == 3
    assert score["state"] is None


def test_parse_score_block_invalid_raises_value_error():
  with pytest.raises(ParseScoreBlockError, match="Could not parse final score"):
        parse_score_block("No numeric score here")


def test_parse_players_empty_text_returns_empty_lists():
    players, numbers = parse_players("")
    assert players == []
    assert numbers == []


def test_parse_players_multiple_entries_without_pos_part():
    players, numbers = parse_players("12. A, Player 34. B, Player")
    assert players == ["12. A, Player", "34. B, Player"]
    assert numbers == [12, 34]


def test_parse_goal_event_type_with_extra_spaces():
    goal = parse_goal_event_type("  4 - 3   (  OT )   GWG  ")
    assert goal == {"home_score": 4, "away_score": 3, "strength": "OT", "qualifier": "GWG"}


def test_parse_actions_returns_empty_when_actions_table_missing():
    html = "<html><body><table><tr><td>No actions here</td></tr></table></body></html>"
    assert parse_actions(html) == []


def test_parse_actions_ignores_rows_without_valid_game_time():
    html = """
<html><body>
  <table>
    <tr><th>Actions</th><th>Last update: now</th></tr>
    <tr><th>1st period</th></tr>
    <tr><td>bad</td><td>2 min</td><td>AAA</td><td>12. Player, Test</td></tr>
    <tr><td>12:34</td><td>2 min</td><td>AAA</td><td>12. Player, Test</td></tr>
  </table>
</body></html>
"""
    actions = parse_actions(html)
    assert len(actions) == 1
    assert actions[0]["game_time"] == "12:34"
    assert actions[0]["event_type"] == "penalty"
    assert actions[0]["event_detail"] == "2 min"


def test_parse_actions_preserves_none_period_when_no_period_header_match():
    html = """
<html><body>
  <table>
    <tr><th>Actions</th><th>Last update: now</th></tr>
    <tr><th>Overtime</th></tr>
    <tr><td>61:00</td><td>PS</td><td>AAA</td><td>12. Player, Test</td></tr>
  </table>
</body></html>
"""
    actions = parse_actions(html)
    assert len(actions) == 1
    assert actions[0]["period"] == "period 4"
    assert actions[0]["event_type"] == "PS"


def test_parse_top_stats_raises_when_top_table_missing():
    with pytest.raises(ParseTopStatsError, match="Top stats table was not found"):
        parse_top_stats("<html><body><table><tr><td>nothing</td></tr></table></body></html>")


def test_parse_top_stats_raises_on_invalid_shots_row_structure():
  html = build_page_html("3 - 0 (0-0, 1-0, 2-0) Final Score Spectators: 5860")
  html = html.replace("<td>(4:12:7)</td>", "", 1)
  with pytest.raises(ParseTopStatsError, match="Shots row does not have the expected structure"):
    parse_top_stats(html)


def test_parse_top_stats_handles_five_period_shootout_format():
    html = build_page_html("4 - 3 (2-1, 1-1, 0-1, 0-0, 1-0) Final Score Spectators: 5860")
    data = parse_top_stats(html)
    assert data["score"]["periods"] == ["2-1", "1-1", "0-1", "0-0", "1-0"]
    assert data["game"]["is_overtime"] is True
    assert data["game"]["is_shootout"] is True


def test_parse_actions_infers_period_4_for_overtime_without_header():
    html = """
<html><body>
  <table>
    <tr><th>Actions</th><th>Last update: now</th></tr>
    <tr><th>3rd period</th></tr>
    <tr><td>59:59</td><td>GK Out</td><td>AAA</td><td>1. Player, One</td></tr>
    <tr><td>64:42</td><td>GK Out</td><td>AAA</td><td>1. Player, One</td></tr>
  </table>
</body></html>
"""
    actions = parse_actions(html, score_period_count=4)
    assert actions[0]["period"] == "3rd period"
    assert actions[1]["period"] == "period 4"


def test_parse_actions_infers_period_5_for_shootout_without_header():
    html = """
<html><body>
  <table>
    <tr><th>Actions</th><th>Last update: now</th></tr>
    <tr><th>3rd period</th></tr>
    <tr><td>63:01</td><td>PS</td><td>AAA</td><td>33. Player, Test</td></tr>
    <tr><td>65:00</td><td>GK Out</td><td>AAA</td><td>1. Player, One</td></tr>
  </table>
</body></html>
"""
    actions = parse_actions(html, score_period_count=5)
    assert actions[0]["period"] == "period 4"
    assert actions[0]["is_goal"] is True
    assert actions[1]["period"] == "period 5"


def test_parse_actions_marks_ps_as_missed_when_text_contains_missed_penalty_shot():
    html = """
<html><body>
  <table>
    <tr><th>Actions</th><th>Last update: now</th></tr>
    <tr><th>Overtime</th></tr>
    <tr>
      <td>63:01</td><td>PS</td><td>BIF</td><td>33. Silfverberg, Jakob</td><td>Missed Penalty Shot Saved By 1. Enroth, Jhonas</td>
    </tr>
  </table>
</body></html>
"""

    actions = parse_actions(html, score_period_count=5)
    assert len(actions) == 1
    assert actions[0]["event_type"] == "PS"
    assert actions[0]["player_text"] == "33. Silfverberg, Jakob Missed Penalty Shot Saved By 1. Enroth, Jhonas"
    assert actions[0]["is_goal"] is False


def test_parse_actions_parses_game_winning_shots_subsection():
  html = """
<html><body>
  <table>
  <tr><th>Actions</th><th>Last update: now</th></tr>
  <tr><th>Game Winning Shots</th></tr>
  <tr><td>Scored</td><td>1 - 0</td><td>BIF</td><td>52. Kopacka, Jack vs. goalie 1. Enroth, Jhonas</td><td></td></tr>
  <tr><td>Missed</td><td>1 - 0</td><td>ÖHK</td><td>89. Karlkvist, Patrik vs. goalie 45. Clara, Damian</td><td></td></tr>
  </table>
</body></html>
"""

  actions = parse_actions(html, score_period_count=5)
  assert len(actions) == 2
  assert actions[0]["period"] == "period 5"
  assert actions[0]["event_type"] == "GWS"
  assert actions[0]["is_goal"] is True
  assert actions[0]["shot_outcome"] == "scored"
  assert actions[0]["goal"] == {
    "home_score": 1,
    "away_score": 0,
    "strength": "GWS",
    "qualifier": "scored",
  }
  assert actions[0]["players"] == ["52. Kopacka, Jack vs. goalie", "1. Enroth, Jhonas"]

  assert actions[1]["period"] == "period 5"
  assert actions[1]["event_type"] == "GWS"
  assert actions[1]["is_goal"] is False
  assert actions[1]["shot_outcome"] == "missed"


def test_extract_penalty_metadata_for_player_penalty():
  meta = extract_penalty_metadata("27. Ang, Jonathan Slashing (54:38 - 56:38)")
  assert meta["clean_player_text"] == "27. Ang, Jonathan"
  assert meta["players"] == ["27. Ang, Jonathan"]
  assert meta["player_numbers"] == [27]
  assert meta["reason"] == "Slashing"
  assert meta["time_range"] == {"start": "54:38", "end": "56:38"}


def test_extract_penalty_metadata_for_team_penalty():
  meta = extract_penalty_metadata("Team penalty Too many players on the ice (27:52 - 29:52)")
  assert meta["clean_player_text"] == "Team penalty"
  assert meta["players"] == []
  assert meta["player_numbers"] == []
  assert meta["reason"] == "Too many players on the ice"
  assert meta["time_range"] == {"start": "27:52", "end": "29:52"}


