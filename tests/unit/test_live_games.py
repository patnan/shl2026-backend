"""Tests for live games: parsing, fetch/get, store, and API endpoint."""
import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from src.shl.helpers.extraction import (
    ExtractLiveGamesError,
    extract_live_games,
    parse_live_games_html,
)
from src.shl.models import ScheduleEntry
from src.shl.schedule import FetchLiveGamesError, fetch_live_games, get_live_games
from src.shl.store import Store


# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

LIVE_PAGE_HTML = """
<html>
<body>
<div class="row bgContainer">
  <div class="row"><div class="tdTitle pageTitle col-5"><h2>Games</h2></div><div class="tdTitleRight pageTitleRight col-7">
                Last update: 2026-08-07 17:45:48
            </div></div>
  <div class="col-12 p-0"><div class="tdSubTitle pageSubTitle">Upcoming / In Progress</div></div>
  <div class="col-12">
    <div class="row d-flex d-sm-none">
      <div class="col-12">
        <div class="tdOdd row p-1 TodaysGamesGame">
          <div class="col-5 p-1 text-right"><div class="h2 font-weight-bold">Rögle BK</div></div>
          <div class="col-2 p-1 text-center Result">
            <div class="col-12 p-0 m-0 text-center"><a class="m-0 p-0" href="
      javascript:openonlinewindow('/Game/Events/1113947','')
    ">2 - 1</a></div>
            <div class="col-12 p-0 m-0 text-center">
                  (1-1, 1-0)
                </div>
          </div>
          <div class="col-5 p-1 text-left"><div class="h2 font-weight-bold">IF Malmö Redhawks</div></div>
        </div>
        <div class="tdOdd row pt-0 mt-0 TodaysGamesGame">
          <div class="col-12 m-0 text-center">2nd period
                     (15:30)
                  </div>
        </div>
      </div>
    </div>
    <div class="tdOdd p-1 row d-none d-sm-flex">
      <div class="col-12 p-0"><div class="row p-0"><div class="col-5"><div class="row">
        <div class="col-4 text-right"><div class="h2 font-weight-bold">Rögle BK</div></div>
        <div class="col-4 text-center Result">
          <div class="col-12 p-0 m-0 text-center"><a class="m-0 p-0" href="
      javascript:openonlinewindow('/Game/Events/1113947','')
    ">2 - 1</a></div>
          <div class="col-12 p-0 m-0 text-center">
                      (1-1, 1-0)
                    </div>
        </div>
        <div class="col-4"><div class="h2 font-weight-bold">IF Malmö Redhawks</div></div>
      </div></div></div></div>
    </div>
    <div class="row d-flex d-sm-none">
      <div class="col-12">
        <div class="tdNormal row p-1 TodaysGamesGame">
          <div class="col-5 p-1 text-right"><div class="h2 font-weight-bold">Leksands IF</div></div>
          <div class="col-2 p-1 text-center Result">
            <div class="col-12 p-0 m-0 text-center">17:00</div>
            <div class="col-12 p-0 m-0 text-center">Clas Ohlson Foundation Arena</div>
          </div>
          <div class="col-5 p-1 text-left"><div class="h2 font-weight-bold">Djurgårdens IF</div></div>
        </div>
        <div class="tdNormal row pt-0 mt-0 TodaysGamesGame">
          <div class="col-12 m-0 text-center"></div>
        </div>
      </div>
    </div>
    <div class="tdNormal p-1 row d-none d-sm-flex">
      <div class="col-12 p-0"><div class="row p-0"><div class="col-5"><div class="row">
        <div class="col-4 text-right"><div class="h2 font-weight-bold">Leksands IF</div></div>
        <div class="col-4 text-center Result">
          <div class="col-12 p-0 m-0 text-center">17:00</div>
          <div class="col-12 p-0 m-0 text-center">Clas Ohlson Foundation Arena</div>
        </div>
        <div class="col-4"><div class="h2 font-weight-bold">Djurgårdens IF</div></div>
      </div></div></div></div>
    </div>
    <div class="row d-flex d-sm-none">
      <div class="col-12">
        <div class="tdOdd row p-1 TodaysGamesGame">
          <div class="col-5 p-1 text-right"><div class="h2 font-weight-bold">Linköping HC</div></div>
          <div class="col-2 p-1 text-center Result">
            <div class="col-12 p-0 m-0 text-center"><a class="m-0 p-0" href="
      javascript:openonlinewindow('/Game/Events/1113768','')
    ">18:00</a></div>
          </div>
          <div class="col-5 p-1 text-left"><div class="h2 font-weight-bold">HV 71</div></div>
        </div>
        <div class="tdOdd row pt-0 mt-0 TodaysGamesGame">
          <div class="col-12 m-0 text-center">Waiting for 1st period</div>
        </div>
      </div>
    </div>
  </div>
</div>
</body>
</html>
"""

LIVE_PAGE_EMPTY_HTML = """
<html>
<body>
<div class="row bgContainer">
  <div class="col-12 p-0"><div class="tdSubTitle pageSubTitle">Upcoming / In Progress</div></div>
  <div class="col-12"></div>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParseLiveGamesHtml:
    def test_parses_three_games_from_duplicate_responsive_html(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert len(entries) == 3

    def test_extracts_home_team(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].home_team == "Rögle BK"
        assert entries[1].home_team == "Leksands IF"
        assert entries[2].home_team == "Linköping HC"

    def test_extracts_away_team(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].away_team == "IF Malmö Redhawks"
        assert entries[1].away_team == "Djurgårdens IF"
        assert entries[2].away_team == "HV 71"

    def test_extracts_time_for_upcoming(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[1].time == "17:00"

    def test_extracts_venue_for_upcoming(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[1].venue == "Clas Ohlson Foundation Arena"

    def test_date_is_today(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        today_str = date.today().isoformat()
        assert entries[0].date == today_str
        assert entries[1].date == today_str

    def test_game_result_empty_for_upcoming(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[1].game_result == ""

    def test_extracts_score_for_in_progress_game(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].game_result == "2 - 1"

    def test_extracts_periods_for_in_progress_game(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].periods == "(1-1, 1-0)"

    def test_extracts_game_url_from_score_link(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].game_url == "https://stats.swehockey.se/Game/Events/1113947"

    def test_extracts_game_url_for_waiting_game(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[2].game_url == "https://stats.swehockey.se/Game/Events/1113768"

    def test_no_game_url_for_upcoming_without_link(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[1].game_url == ""

    def test_extracts_status_for_in_progress_game(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].status == "2nd period (15:30)"

    def test_extracts_game_clock_from_status(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].game_clock == "15:30"
        assert entries[1].game_clock == ""
        assert entries[2].game_clock == ""

    def test_extracts_current_period_from_status(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].current_period == "2nd period"
        assert entries[1].current_period == ""
        assert entries[2].current_period == "1st period"

    def test_extracts_status_for_waiting_game(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[2].status == "Waiting for 1st period"

    def test_status_empty_for_upcoming_game(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[1].status == ""

    def test_empty_page_returns_empty_list(self):
        entries, _ = parse_live_games_html(LIVE_PAGE_EMPTY_HTML)
        assert entries == []

    def test_deduplicates_mobile_and_desktop_views(self):
        """Games appear twice (mobile + desktop layout). Should only get one per matchup."""
        entries, _ = parse_live_games_html(LIVE_PAGE_HTML)
        # Check no duplicates
        keys = [(e.home_team, e.away_team) for e in entries]
        assert len(keys) == len(set(keys))

    def test_extracts_page_last_update_timestamp(self):
        _, page_last_update = parse_live_games_html(LIVE_PAGE_HTML)
        assert page_last_update == "2026-08-07 17:45:48"

    def test_returns_none_when_no_last_update(self):
        _, page_last_update = parse_live_games_html(LIVE_PAGE_EMPTY_HTML)
        assert page_last_update is None


# ---------------------------------------------------------------------------
# Store tests
# ---------------------------------------------------------------------------
# Live points tests
# ---------------------------------------------------------------------------


class TestGetLivePoints:
    def test_regulation_win_gives_3_0(self, tmp_path):
        from src.shl.schedule import get_live_points
        from src.shl.store import save_live_games

        entries = [
            ScheduleEntry(
                date="2026-08-07", time="", home_team="Team A", away_team="Team B",
                game_result="3 - 1", periods="(2-0, 1-1, 0-0)", spectators="", venue="",
                game_url="", round="", status="Final Score",
            ),
        ]
        save_live_games(tmp_path, 21139, entries)

        points = get_live_points(21139, tmp_path)
        assert points["Team A"] == 3
        assert points["Team B"] == 0

    def test_ot_win_gives_2_1(self, tmp_path):
        from src.shl.schedule import get_live_points
        from src.shl.store import save_live_games

        entries = [
            ScheduleEntry(
                date="2026-08-07", time="", home_team="Team A", away_team="Team B",
                game_result="2 - 3", periods="(1-1, 1-1, 0-0, 0-1)", spectators="", venue="",
                game_url="", round="", status="Final Score",
            ),
        ]
        save_live_games(tmp_path, 21139, entries)

        points = get_live_points(21139, tmp_path)
        assert points["Team B"] == 2
        assert points["Team A"] == 1

    def test_so_win_gives_2_1(self, tmp_path):
        from src.shl.schedule import get_live_points
        from src.shl.store import save_live_games

        entries = [
            ScheduleEntry(
                date="2026-08-07", time="", home_team="Team A", away_team="Team B",
                game_result="3 - 2", periods="(1-1, 0-1, 1-0, 0-0, 1-0)", spectators="", venue="",
                game_url="", round="", status="Final Score",
            ),
        ]
        save_live_games(tmp_path, 21139, entries)

        points = get_live_points(21139, tmp_path)
        assert points["Team A"] == 2
        assert points["Team B"] == 1

    def test_tied_in_regulation_gives_0_0(self, tmp_path):
        from src.shl.schedule import get_live_points
        from src.shl.store import save_live_games

        entries = [
            ScheduleEntry(
                date="2026-08-07", time="", home_team="Team A", away_team="Team B",
                game_result="1 - 1", periods="(1-1, 0-0)", spectators="", venue="",
                game_url="", round="", status="2nd period (05:00)",
            ),
        ]
        save_live_games(tmp_path, 21139, entries)

        points = get_live_points(21139, tmp_path)
        assert points["Team A"] == 0
        assert points["Team B"] == 0

    def test_tied_in_ot_gives_1_1(self, tmp_path):
        from src.shl.schedule import get_live_points
        from src.shl.store import save_live_games

        entries = [
            ScheduleEntry(
                date="2026-08-07", time="", home_team="Team A", away_team="Team B",
                game_result="2 - 2", periods="(1-1, 1-1, 0-0, 0-0)", spectators="", venue="",
                game_url="", round="", status="OT",
            ),
        ]
        save_live_games(tmp_path, 21139, entries)

        points = get_live_points(21139, tmp_path)
        assert points["Team A"] == 1
        assert points["Team B"] == 1

    def test_no_live_games_returns_empty(self, tmp_path):
        from src.shl.schedule import get_live_points

        points = get_live_points(21139, tmp_path)
        assert points == {}

    def test_upcoming_game_not_counted(self, tmp_path):
        from src.shl.schedule import get_live_points
        from src.shl.store import save_live_games

        entries = [
            ScheduleEntry(
                date="2026-08-07", time="18:00", home_team="Team A", away_team="Team B",
                game_result="", periods="", spectators="", venue="Arena",
                game_url="", round="", status="",
            ),
        ]
        save_live_games(tmp_path, 21139, entries)

        points = get_live_points(21139, tmp_path)
        assert points == {}


class TestGetLiveStandings:
    def test_merges_live_points_and_reranks(self, tmp_path):
        from src.shl.schedule import get_live_standings
        from src.shl.store import save_live_games, save_schedule, save_standings
        from src.shl.models import StandingsRow

        # Set up schedule with teams
        schedule = [
            ScheduleEntry(date="2026-08-06", time="18:00", home_team="Team A", away_team="Team B",
                          game_result="3 - 1", periods="(1-0, 1-1, 1-0)", spectators="", venue="",
                          game_url="", round=""),
            ScheduleEntry(date="2026-08-07", time="18:00", home_team="Team B", away_team="Team A",
                          game_result="", periods="", spectators="", venue="",
                          game_url="", round=""),
        ]
        save_schedule(tmp_path, 21139, schedule)

        # Save standings snapshot (Team A rank 1, Team B rank 2)
        prev_standings = [
            StandingsRow(rank=1, team="Team A", games_played=1, w=1, t=0, l=0,
                         goals_for=3, goals_against=1, goal_difference=2, tp=3,
                         otw=0, otl=0, gwsw=0, gwsl=0),
            StandingsRow(rank=2, team="Team B", games_played=1, w=0, t=0, l=1,
                         goals_for=1, goals_against=3, goal_difference=-2, tp=0,
                         otw=0, otl=0, gwsw=0, gwsl=0),
        ]
        save_standings(tmp_path, 21139, prev_standings)

        # Live game: Team B winning 4-0 (regulation = 3 pts)
        live = [
            ScheduleEntry(date="2026-08-07", time="", home_team="Team B", away_team="Team A",
                          game_result="4 - 0", periods="(2-0, 2-0)", spectators="", venue="",
                          game_url="", round="", status="2nd period"),
        ]
        save_live_games(tmp_path, 21139, live)

        result = get_live_standings(21139, tmp_path)
        assert len(result) == 2
        # Team A: 3 base + 0 live = 3, Team B: 0 base + 3 live = 3
        # Tied on points, Team A has better GD (+2 vs -2), so Team A stays rank 1
        assert result[0].team == "Team A"
        assert result[0].tp == 3
        assert result[0].rank == 1
        assert result[1].team == "Team B"
        assert result[1].tp == 3
        assert result[1].rank == 2

    def test_movement_calculated_from_base_rank(self, tmp_path):
        from src.shl.schedule import get_live_standings
        from src.shl.store import save_live_games, save_schedule, save_standings
        from src.shl.models import StandingsRow

        schedule = [
            ScheduleEntry(date="2026-08-06", time="18:00", home_team="Team A", away_team="Team B",
                          game_result="1 - 0", periods="(1-0, 0-0, 0-0)", spectators="", venue="",
                          game_url="", round=""),
            ScheduleEntry(date="2026-08-06", time="18:00", home_team="Team C", away_team="Team A",
                          game_result="2 - 0", periods="(1-0, 1-0, 0-0)", spectators="", venue="",
                          game_url="", round=""),
        ]
        save_schedule(tmp_path, 21139, schedule)

        prev_standings = [
            StandingsRow(rank=1, team="Team C", games_played=1, w=1, t=0, l=0,
                         goals_for=2, goals_against=0, goal_difference=2, tp=3,
                         otw=0, otl=0, gwsw=0, gwsl=0),
            StandingsRow(rank=2, team="Team A", games_played=2, w=1, t=0, l=1,
                         goals_for=1, goals_against=2, goal_difference=-1, tp=3,
                         otw=0, otl=0, gwsw=0, gwsl=0),
            StandingsRow(rank=3, team="Team B", games_played=1, w=0, t=0, l=1,
                         goals_for=0, goals_against=1, goal_difference=-1, tp=0,
                         otw=0, otl=0, gwsw=0, gwsl=0),
        ]
        save_standings(tmp_path, 21139, prev_standings)

        # Live: Team B gets 3 points, jumps above Team A
        live = [
            ScheduleEntry(date="2026-08-07", time="", home_team="Team B", away_team="Team C",
                          game_result="5 - 0", periods="(2-0, 2-0, 1-0)", spectators="", venue="",
                          game_url="", round="", status="Final Score"),
        ]
        save_live_games(tmp_path, 21139, live)

        result = get_live_standings(21139, tmp_path)
        # Team C: 3+0=3 (GD +2), Team A: 3+0=3 (GD -1), Team B: 0+3=3 (GD -1)
        # All have 3 pts. Sort by GD: C(+2), then A(-1) vs B(-1) by GF: A(1) vs B(0) → A first
        assert result[0].team == "Team C"
        assert result[0].movement == 0  # rank 1 → 1
        assert result[1].team == "Team A"
        assert result[1].movement == 0  # rank 2 → 2
        assert result[2].team == "Team B"
        assert result[2].movement == 0  # rank 3 → 3


class TestCompareLiveStandings:
    def test_detects_position_changes(self):
        from src.shl.schedule import compare_live_standings
        from src.shl.models import StandingsRow

        prev = [
            StandingsRow(rank=1, team="A", games_played=0, w=0, t=0, l=0,
                         goals_for=0, goals_against=0, goal_difference=0, tp=6,
                         otw=0, otl=0, gwsw=0, gwsl=0),
            StandingsRow(rank=2, team="B", games_played=0, w=0, t=0, l=0,
                         goals_for=0, goals_against=0, goal_difference=0, tp=3,
                         otw=0, otl=0, gwsw=0, gwsl=0),
        ]
        current = [
            StandingsRow(rank=1, team="B", games_played=0, w=0, t=0, l=0,
                         goals_for=0, goals_against=0, goal_difference=0, tp=6,
                         otw=0, otl=0, gwsw=0, gwsl=0),
            StandingsRow(rank=2, team="A", games_played=0, w=0, t=0, l=0,
                         goals_for=0, goals_against=0, goal_difference=0, tp=6,
                         otw=0, otl=0, gwsw=0, gwsl=0),
        ]

        changes = compare_live_standings(prev, current)
        assert len(changes) == 2
        b_change = next(c for c in changes if c["team"] == "B")
        a_change = next(c for c in changes if c["team"] == "A")
        assert b_change == {"team": "B", "prev_rank": 2, "new_rank": 1, "movement": -1}
        assert a_change == {"team": "A", "prev_rank": 1, "new_rank": 2, "movement": 1}

    def test_no_changes_returns_empty(self):
        from src.shl.schedule import compare_live_standings
        from src.shl.models import StandingsRow

        standings = [
            StandingsRow(rank=1, team="A", games_played=0, w=0, t=0, l=0,
                         goals_for=0, goals_against=0, goal_difference=0, tp=3,
                         otw=0, otl=0, gwsw=0, gwsl=0),
        ]
        changes = compare_live_standings(standings, standings)
        assert changes == []


# ---------------------------------------------------------------------------


class TestStoreLiveGames:
    def test_save_and_load_live_games(self, tmp_path):
        store = Store(tmp_path)
        games = [
            ScheduleEntry(
                date="2026-08-07",
                time="16:00",
                home_team="Rögle BK",
                away_team="IF Malmö Redhawks",
                game_result="",
                periods="",
                spectators="",
                venue="Catena Arena",
                game_url="",
                round="",
                status="",
            ),
        ]
        store.save_live_games(21139, games)
        loaded = store.load_live_games(21139)
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0].home_team == "Rögle BK"
        assert loaded[0].venue == "Catena Arena"

    def test_load_returns_none_when_not_saved(self, tmp_path):
        store = Store(tmp_path)
        assert store.load_live_games(99999) is None

    def test_get_fetched_at_returns_timestamp(self, tmp_path):
        store = Store(tmp_path)
        games = [
            ScheduleEntry(
                date="2026-08-07",
                time="16:00",
                home_team="Rögle BK",
                away_team="IF Malmö Redhawks",
                game_result="",
                periods="",
                spectators="",
                venue="Catena Arena",
                game_url="",
                round="",
                status="",
            ),
        ]
        store.save_live_games(21139, games)
        fetched_at = store.get_live_games_fetched_at(21139)
        assert fetched_at is not None

    def test_save_replaces_previous_data(self, tmp_path):
        store = Store(tmp_path)
        games_v1 = [
            ScheduleEntry(
                date="2026-08-07", time="16:00", home_team="Team A", away_team="Team B",
                game_result="", periods="", spectators="", venue="Arena1", game_url="", round="", status="",
            ),
        ]
        games_v2 = [
            ScheduleEntry(
                date="2026-08-07", time="17:00", home_team="Team C", away_team="Team D",
                game_result="", periods="", spectators="", venue="Arena2", game_url="", round="", status="",
            ),
            ScheduleEntry(
                date="2026-08-07", time="18:00", home_team="Team E", away_team="Team F",
                game_result="", periods="", spectators="", venue="Arena3", game_url="", round="", status="",
            ),
        ]
        store.save_live_games(21139, games_v1)
        store.save_live_games(21139, games_v2)
        loaded = store.load_live_games(21139)
        assert len(loaded) == 2
        assert loaded[0].home_team == "Team C"

    def test_save_and_get_page_last_update(self, tmp_path):
        store = Store(tmp_path)
        games = [
            ScheduleEntry(
                date="2026-08-07", time="16:00", home_team="Rögle BK", away_team="IF Malmö Redhawks",
                game_result="", periods="", spectators="", venue="Catena Arena", game_url="", round="", status="",
            ),
        ]
        store.save_live_games(21139, games, page_last_update="2026-08-07 15:55:00")
        assert store.get_live_games_page_last_update(21139) == "2026-08-07 15:55:00"

    def test_page_last_update_none_when_not_provided(self, tmp_path):
        store = Store(tmp_path)
        games = [
            ScheduleEntry(
                date="2026-08-07", time="16:00", home_team="Rögle BK", away_team="IF Malmö Redhawks",
                game_result="", periods="", spectators="", venue="Catena Arena", game_url="", round="", status="",
            ),
        ]
        store.save_live_games(21139, games)
        assert store.get_live_games_page_last_update(21139) is None

    def test_page_last_update_none_when_not_saved(self, tmp_path):
        store = Store(tmp_path)
        assert store.get_live_games_page_last_update(99999) is None


# ---------------------------------------------------------------------------
# Schedule module tests (fetch_live_games / get_live_games)
# ---------------------------------------------------------------------------


class TestFetchLiveGames:
    def test_fetch_live_games_scrapes_and_saves(self, monkeypatch, tmp_path):
        fake_games = [
            ScheduleEntry(
                date="2026-08-07", time="16:00", home_team="Rögle BK", away_team="IF Malmö Redhawks",
                game_result="", periods="", spectators="", venue="Catena Arena", game_url="", round="", status="",
            ),
        ]
        monkeypatch.setattr("src.shl.schedule.extract_live_games", lambda season_id: (fake_games, "2026-08-07 16:00:00", None))

        result, page_last_update, age_seconds = fetch_live_games(21139, tmp_path)
        assert len(result) == 1
        assert result[0].home_team == "Rögle BK"
        assert page_last_update == "2026-08-07 16:00:00"

        # Verify it was persisted
        cached = get_live_games(21139, tmp_path)
        assert cached is not None
        assert len(cached) == 1

    def test_fetch_live_games_raises_on_error(self, monkeypatch, tmp_path):
        def raise_error(season_id):
            raise RuntimeError("network error")

        monkeypatch.setattr("src.shl.schedule.extract_live_games", raise_error)

        with pytest.raises(FetchLiveGamesError, match="fetch_live_games failed"):
            fetch_live_games(21139, tmp_path)

    def test_get_live_games_returns_none_when_not_fetched(self, tmp_path):
        result = get_live_games(21139, tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# REST API endpoint tests
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi")
pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient
from src.shl.rest_api import create_app


class TestLiveGamesEndpoint:
    def test_returns_cached_live_games(self, monkeypatch, tmp_path):
        games = [
            ScheduleEntry(
                date="2026-08-07", time="16:00", home_team="Rögle BK", away_team="IF Malmö Redhawks",
                game_result="", periods="", spectators="", venue="Catena Arena", game_url="", round="", status="",
            ),
        ]
        monkeypatch.setattr("src.shl.rest_api.get_live_games", lambda season_id, cache_dir: games)
        monkeypatch.setattr("src.shl.rest_api.get_live_games_fetched_at", lambda cache_dir, season_id: "2026-08-07T10:00:00")
        monkeypatch.setattr("src.shl.rest_api.get_live_games_page_last_update", lambda cache_dir, season_id: "2026-08-07 09:55:00")

        client = TestClient(create_app(tmp_path))
        response = client.get("/seasons/21139/games/live")
        assert response.status_code == 200
        payload = response.json()
        assert payload["meta"]["count"] == 1
        assert payload["data"][0]["home_team"] == "Rögle BK"
        assert payload["meta"]["source_fetched_at"] == "2026-08-07T10:00:00"
        assert payload["meta"]["page_last_update"] == "2026-08-07 09:55:00"

    def test_fetches_on_demand_when_not_cached(self, monkeypatch, tmp_path):
        games = [
            ScheduleEntry(
                date="2026-08-07", time="17:00", home_team="Leksands IF", away_team="Djurgårdens IF",
                game_result="", periods="", spectators="", venue="Tegera Arena", game_url="", round="", status="",
            ),
        ]
        monkeypatch.setattr("src.shl.rest_api.get_live_games", lambda season_id, cache_dir: None)
        monkeypatch.setattr("src.shl.rest_api.fetch_live_games", lambda season_id, cache_dir: (games, "2026-08-07 11:00:00", None))
        monkeypatch.setattr("src.shl.rest_api.get_live_games_fetched_at", lambda cache_dir, season_id: "2026-08-07T11:00:00")
        monkeypatch.setattr("src.shl.rest_api.get_live_games_page_last_update", lambda cache_dir, season_id: "2026-08-07 11:00:00")

        client = TestClient(create_app(tmp_path))
        response = client.get("/seasons/21139/games/live")
        assert response.status_code == 200
        payload = response.json()
        assert payload["meta"]["count"] == 1
        assert payload["data"][0]["home_team"] == "Leksands IF"

    def test_returns_502_when_fetch_fails(self, monkeypatch, tmp_path):
        monkeypatch.setattr("src.shl.rest_api.get_live_games", lambda season_id, cache_dir: None)

        def raise_error(season_id, cache_dir):
            raise RuntimeError("upstream down")

        monkeypatch.setattr("src.shl.rest_api.fetch_live_games", raise_error)

        client = TestClient(create_app(tmp_path))
        response = client.get("/seasons/21139/games/live")
        assert response.status_code == 502
        assert "Failed to fetch live games" in response.json()["error"]

    def test_returns_empty_list_when_no_games_today(self, monkeypatch, tmp_path):
        monkeypatch.setattr("src.shl.rest_api.get_live_games", lambda season_id, cache_dir: [])
        monkeypatch.setattr("src.shl.rest_api.get_live_games_fetched_at", lambda cache_dir, season_id: "2026-08-07T10:00:00")
        monkeypatch.setattr("src.shl.rest_api.get_live_games_page_last_update", lambda cache_dir, season_id: None)

        client = TestClient(create_app(tmp_path))
        response = client.get("/seasons/21139/games/live")
        assert response.status_code == 200
        payload = response.json()
        assert payload["data"] == []
        assert payload["meta"]["count"] == 0
        assert payload["meta"]["page_last_update"] is None


# ---------------------------------------------------------------------------
# Poller target tests
# ---------------------------------------------------------------------------


class TestPollerLiveGamesTarget:
    def test_seed_includes_live_games_target(self, tmp_path):
        from src.shl.poller import seed_season_targets

        result = seed_season_targets(tmp_path, season_id=18263)
        assert result["live_games_target"] == 1
        assert result["total_targets"] == 7

    def test_live_games_poll_target_created(self, tmp_path):
        from src.shl.poller import seed_season_targets
        from src.shl.store import list_poll_targets

        seed_season_targets(tmp_path, season_id=18263)
        targets = list_poll_targets(tmp_path)
        target_types = [t.target_type for t in targets]
        assert "live_games" in target_types

    def test_run_target_calls_fetch_live_games(self, monkeypatch, tmp_path):
        from datetime import datetime, timedelta, timezone

        from src.shl.poller import run_poller_tick
        from src.shl.store import upsert_poll_target

        now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)
        upsert_poll_target(
            tmp_path,
            target_type="live_games",
            target_key="18263",
            enabled=True,
            next_poll_at=(now - timedelta(seconds=1)).isoformat(),
        )

        calls = {"fetch_live_games": 0}

        def fake_fetch_live_games(season_id, db_dir):
            calls["fetch_live_games"] += 1
            assert season_id == 18263
            assert db_dir == tmp_path
            return [], None, None

        monkeypatch.setattr("src.shl.poller.fetch_live_games", fake_fetch_live_games)

        results = run_poller_tick(tmp_path, now=now)

        assert len(results) == 1
        assert results[0]["status"] == "ok"
        assert calls["fetch_live_games"] == 1

    def test_run_target_handles_fetch_error(self, monkeypatch, tmp_path):
        from datetime import datetime, timedelta, timezone

        from src.shl.poller import run_poller_tick
        from src.shl.store import upsert_poll_target

        now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)
        upsert_poll_target(
            tmp_path,
            target_type="live_games",
            target_key="18263",
            enabled=True,
            next_poll_at=(now - timedelta(seconds=1)).isoformat(),
        )

        def fake_fetch_live_games(season_id, db_dir):
            raise RuntimeError("upstream down")

        monkeypatch.setattr("src.shl.poller.fetch_live_games", fake_fetch_live_games)

        results = run_poller_tick(tmp_path, now=now)

        assert len(results) == 1
        assert results[0]["status"] == "error"

    def test_success_interval_is_25_seconds(self):
        from src.shl.poller import DEFAULT_SUCCESS_INTERVAL_SECONDS

        assert DEFAULT_SUCCESS_INTERVAL_SECONDS["live_games"] == 25
