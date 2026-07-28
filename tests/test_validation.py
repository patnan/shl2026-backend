import pytest

from src.shl.api import (
    CalculateStandingsError,
    ParseOverviewStandingsError,
    ParseTopStatsError,
    build_validation_report,
    calculate_standings,
    compare_standings,
    extract_penalty_metadata,
    parse_overview_standings_html,
    validate_multiple_seasons,
    validate_season_standings,
)

def test_calculate_standings_applies_regulation_overtime_and_unfinished_points():
  standings = calculate_standings(
    [
      {
        "game": {
          "home_team": "A",
          "away_team": "B",
          "is_overtime": False,
          "is_shootout": False,
        },
        "score": {
          "home_score": 4,
          "away_score": 1,
          "state": "Final Score",
        },
      },
      {
        "game": {
          "home_team": "B",
          "away_team": "C",
          "is_overtime": True,
          "is_shootout": False,
        },
        "score": {
          "home_score": 3,
          "away_score": 2,
          "state": "Final Score",
        },
      },
      {
        "game": {
          "home_team": "C",
          "away_team": "B",
          "is_overtime": True,
          "is_shootout": True,
        },
        "score": {
          "home_score": 2,
          "away_score": 1,
          "state": "Final Score",
        },
      },
      {
        "game": {
          "home_team": "C",
          "away_team": "A",
          "is_overtime": False,
          "is_shootout": False,
        },
        "score": {
          "home_score": 1,
          "away_score": 1,
          "state": None,
        },
      },
    ]
  )

  assert standings == [
    {
      "team": "A",
      "rank": 1,
      "games_played": 2,
      "wins_regulation": 1,
      "wins_overtime": 0,
      "wins_shootout": 0,
      "wins_overtime_or_shootout": 0,
      "losses_regulation": 0,
      "losses_overtime": 0,
      "losses_shootout": 0,
      "losses_overtime_or_shootout": 0,
      "tied_after_regulation": 0,
      "unfinished_games": 1,
      "points": 4,
      "goals_for": 5,
      "goals_against": 2,
      "goal_difference": 3,
      "w": 1,
      "t": 0,
      "l": 0,
      "tp": 4,
      "otw": 0,
      "otl": 0,
      "gwsw": 0,
      "gwsl": 0,
    },
    {
      "team": "C",
      "rank": 2,
      "games_played": 3,
      "wins_regulation": 0,
      "wins_overtime": 0,
      "wins_shootout": 1,
      "wins_overtime_or_shootout": 1,
      "losses_regulation": 0,
      "losses_overtime": 1,
      "losses_shootout": 0,
      "losses_overtime_or_shootout": 1,
      "tied_after_regulation": 2,
      "unfinished_games": 1,
      "points": 4,
      "goals_for": 5,
      "goals_against": 5,
      "goal_difference": 0,
      "w": 0,
      "t": 2,
      "l": 0,
      "tp": 4,
      "otw": 0,
      "otl": 1,
      "gwsw": 1,
      "gwsl": 0,
    },
    {
      "team": "B",
      "rank": 3,
      "games_played": 3,
      "wins_regulation": 0,
      "wins_overtime": 1,
      "wins_shootout": 0,
      "wins_overtime_or_shootout": 1,
      "losses_regulation": 1,
      "losses_overtime": 0,
      "losses_shootout": 1,
      "losses_overtime_or_shootout": 1,
      "tied_after_regulation": 2,
      "unfinished_games": 0,
      "points": 3,
      "goals_for": 5,
      "goals_against": 8,
      "goal_difference": -3,
      "w": 0,
      "t": 2,
      "l": 1,
      "tp": 3,
      "otw": 1,
      "otl": 0,
      "gwsw": 0,
      "gwsl": 1,
    },
  ]


def test_calculate_standings_raises_for_invalid_game_shape():
  with pytest.raises(CalculateStandingsError, match="Each game must contain 'game' and 'score' dictionaries"):
    calculate_standings([{"game": {"home_team": "A", "away_team": "B"}}])


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
  calculated = calculate_standings(
    [
      {
        "game": {
          "home_team": "A",
          "away_team": "B",
          "is_overtime": False,
          "is_shootout": False,
        },
        "score": {
          "home_score": 4,
          "away_score": 1,
          "state": "Final Score",
        },
      }
    ]
  )

  assert overview == [
    {
      "rank": 1,
      "team": "A",
      "games_played": 1,
      "w": 1,
      "t": 0,
      "l": 0,
      "goals_for": 4,
      "goals_against": 1,
      "goal_difference": 3,
      "tp": 3,
      "otw": 0,
      "otl": 0,
      "gwsw": 0,
      "gwsl": 0,
    },
    {
      "rank": 2,
      "team": "B",
      "games_played": 1,
      "w": 0,
      "t": 0,
      "l": 1,
      "goals_for": 1,
      "goals_against": 4,
      "goal_difference": -3,
      "tp": 0,
      "otw": 0,
      "otl": 0,
      "gwsw": 0,
      "gwsl": 0,
    },
  ]
  assert compare_standings(calculated, overview) == []


def test_parse_overview_standings_html_raises_when_group_standings_missing():
  with pytest.raises(ParseOverviewStandingsError, match="Group Standings heading was not found"):
    parse_overview_standings_html("<html><body><p>no table</p></body></html>")


def test_validate_season_standings_accepts_cached_inputs_and_builds_report():
  games = [
    {
      "game": {
        "home_team": "A",
        "away_team": "B",
        "is_overtime": False,
        "is_shootout": False,
      },
      "score": {
        "home_score": 4,
        "away_score": 1,
        "state": "Final Score",
      },
    }
  ]
  overview_html = """
<html><body>
  <table class="tblContent" width="100%">
    <tr><td class="tdTitle" colspan="3"><h2>Group Standings</h2></td></tr>
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

  validation = validate_season_standings(18263, games=games, overview_html=overview_html)
  report = build_validation_report(validation)

  assert validation["matches"] is True
  assert validation["mismatches"] == []
  assert report == {
    "season_id": 18263,
    "schedule_url": "https://stats.swehockey.se/ScheduleAndResults/Schedule/18263",
    "overview_url": "https://stats.swehockey.se/ScheduleAndResults/Overview/18263",
    "matches": True,
    "mismatch_count": 0,
    "team_count": 2,
    "mismatches": [],
  }


def test_validate_multiple_seasons_summarizes_matches_mismatches_and_failures(monkeypatch):
  def fake_load_or_fetch_season_validation_inputs(
    season_id,
    cache_dir=None,
    progress_callback=None,
    games=None,
    overview_html=None,
  ):
    return {
      "games": [],
      "overview_html": "<html></html>",
      "games_source": "provided",
      "overview_source": "provided",
      "games_cache_path": None,
      "overview_cache_path": None,
    }

  def fake_validate_season_standings(season_id, progress_callback=None, games=None, overview_html=None):
    if season_id == 100:
      return {
        "season_id": 100,
        "schedule_url": "https://stats.swehockey.se/ScheduleAndResults/Schedule/100",
        "overview_url": "https://stats.swehockey.se/ScheduleAndResults/Overview/100",
        "matches": True,
        "mismatches": [],
        "calculated_standings": [],
        "overview_standings": [{"team": "A"}],
      }
    if season_id == 200:
      return {
        "season_id": 200,
        "schedule_url": "https://stats.swehockey.se/ScheduleAndResults/Schedule/200",
        "overview_url": "https://stats.swehockey.se/ScheduleAndResults/Overview/200",
        "matches": False,
        "mismatches": [{"team": "B", "field": "tp", "calculated": 10, "overview": 9}],
        "calculated_standings": [],
        "overview_standings": [{"team": "B"}],
      }
    raise RuntimeError("boom")

  monkeypatch.setattr("src.shl.api.load_or_fetch_season_validation_inputs", fake_load_or_fetch_season_validation_inputs)
  monkeypatch.setattr("src.shl.api.validate_season_standings", fake_validate_season_standings)

  summary = validate_multiple_seasons([100, 200, 300])

  assert summary == {
    "season_ids": [100, 200, 300],
    "total_seasons": 3,
    "successful_seasons": 2,
    "failed_seasons": 1,
    "matching_seasons": 1,
    "mismatching_seasons": 1,
    "all_match": False,
    "results": [
      {
        "season_id": 100,
        "schedule_url": "https://stats.swehockey.se/ScheduleAndResults/Schedule/100",
        "overview_url": "https://stats.swehockey.se/ScheduleAndResults/Overview/100",
        "matches": True,
        "mismatch_count": 0,
        "team_count": 1,
        "mismatches": [],
        "error": None,
        "games_source": "provided",
        "overview_source": "provided",
        "games_cache_path": None,
        "overview_cache_path": None,
      },
      {
        "season_id": 200,
        "schedule_url": "https://stats.swehockey.se/ScheduleAndResults/Schedule/200",
        "overview_url": "https://stats.swehockey.se/ScheduleAndResults/Overview/200",
        "matches": False,
        "mismatch_count": 1,
        "team_count": 1,
        "mismatches": [{"team": "B", "field": "tp", "calculated": 10, "overview": 9}],
        "error": None,
        "games_source": "provided",
        "overview_source": "provided",
        "games_cache_path": None,
        "overview_cache_path": None,
      },
      {
        "season_id": 300,
        "schedule_url": "https://stats.swehockey.se/ScheduleAndResults/Schedule/300",
        "overview_url": "https://stats.swehockey.se/ScheduleAndResults/Overview/300",
        "matches": False,
        "mismatch_count": None,
        "team_count": 0,
        "mismatches": [],
        "error": "boom",
        "games_source": None,
        "overview_source": None,
        "games_cache_path": None,
        "overview_cache_path": None,
      },
    ],
  }


def test_validate_multiple_seasons_uses_cache_and_saves_missing_files(tmp_path, monkeypatch):
  games = [
    {
      "game": {
        "home_team": "A",
        "away_team": "B",
        "is_overtime": False,
        "is_shootout": False,
      },
      "score": {
        "home_score": 4,
        "away_score": 1,
        "state": "Final Score",
      },
    }
  ]
  overview_html = """
<html><body>
  <table class="tblContent" width="100%">
    <tr><td class="tdTitle" colspan="3"><h2>Group Standings</h2></td></tr>
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
  calls = {"games": 0, "overview": 0}

  def fake_extract_games_from_listing_with_progress(listing_url, progress_callback=None):
    calls["games"] += 1
    return games

  def fake_fetch_html(url, timeout=20):
    calls["overview"] += 1
    return overview_html

  monkeypatch.setattr("src.shl.api.extract_games_from_listing_with_progress", fake_extract_games_from_listing_with_progress)
  monkeypatch.setattr("src.shl.api.fetch_html", fake_fetch_html)

  first = validate_multiple_seasons([18263], cache_dir=tmp_path)
  assert calls == {"games": 1, "overview": 1}
  assert (tmp_path / "games_18263.json").exists()
  assert (tmp_path / "overview_18263.html").exists()
  assert first["results"][0]["games_source"] == "live"
  assert first["results"][0]["overview_source"] == "live"

  second = validate_multiple_seasons([18263], cache_dir=tmp_path)
  assert calls == {"games": 1, "overview": 1}
  assert second["all_match"] is True
  assert second["results"][0]["games_source"] == "cache"
  assert second["results"][0]["overview_source"] == "cache"


