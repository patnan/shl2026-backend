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
  <div class="col-12 p-0"><div class="tdSubTitle pageSubTitle">Upcoming / In Progress</div></div>
  <div class="col-12">
    <div class="row d-flex d-sm-none">
      <div class="col-12">
        <div class="tdOdd row p-1 TodaysGamesGame">
          <div class="col-5 p-1 text-right"><div class="h2 font-weight-bold">Rögle BK</div></div>
          <div class="col-2 p-1 text-center Result">
            <div class="col-12 p-0 m-0 text-center">16:00</div>
            <div class="col-12 p-0 m-0 text-center">Catena Arena</div>
          </div>
          <div class="col-5 p-1 text-left"><div class="h2 font-weight-bold">IF Malmö Redhawks</div></div>
        </div>
      </div>
    </div>
    <div class="tdOdd p-1 row d-none d-sm-flex">
      <div class="col-12 p-0"><div class="row p-0"><div class="col-5"><div class="row">
        <div class="col-4 text-right"><div class="h2 font-weight-bold">Rögle BK</div></div>
        <div class="col-4 text-center Result">
          <div class="col-12 p-0 m-0 text-center">16:00</div>
          <div class="col-12 p-0 m-0 text-center">Catena Arena</div>
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
    def test_parses_two_games_from_duplicate_responsive_html(self):
        entries = parse_live_games_html(LIVE_PAGE_HTML)
        assert len(entries) == 2

    def test_extracts_home_team(self):
        entries = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].home_team == "Rögle BK"
        assert entries[1].home_team == "Leksands IF"

    def test_extracts_away_team(self):
        entries = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].away_team == "IF Malmö Redhawks"
        assert entries[1].away_team == "Djurgårdens IF"

    def test_extracts_time(self):
        entries = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].time == "16:00"
        assert entries[1].time == "17:00"

    def test_extracts_venue(self):
        entries = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].venue == "Catena Arena"
        assert entries[1].venue == "Clas Ohlson Foundation Arena"

    def test_date_is_today(self):
        entries = parse_live_games_html(LIVE_PAGE_HTML)
        today_str = date.today().isoformat()
        assert entries[0].date == today_str
        assert entries[1].date == today_str

    def test_game_result_empty_for_upcoming(self):
        entries = parse_live_games_html(LIVE_PAGE_HTML)
        assert entries[0].game_result == ""
        assert entries[1].game_result == ""

    def test_empty_page_returns_empty_list(self):
        entries = parse_live_games_html(LIVE_PAGE_EMPTY_HTML)
        assert entries == []

    def test_deduplicates_mobile_and_desktop_views(self):
        """Games appear twice (mobile + desktop layout). Should only get one per matchup."""
        entries = parse_live_games_html(LIVE_PAGE_HTML)
        # Check no duplicates
        keys = [(e.home_team, e.away_team) for e in entries]
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Store tests
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
        monkeypatch.setattr("src.shl.schedule.extract_live_games", lambda season_id: fake_games)

        result = fetch_live_games(21139, tmp_path)
        assert len(result) == 1
        assert result[0].home_team == "Rögle BK"

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

        client = TestClient(create_app(tmp_path))
        response = client.get("/seasons/21139/games/live")
        assert response.status_code == 200
        payload = response.json()
        assert payload["meta"]["count"] == 1
        assert payload["data"][0]["home_team"] == "Rögle BK"
        assert payload["meta"]["source_fetched_at"] == "2026-08-07T10:00:00"

    def test_fetches_on_demand_when_not_cached(self, monkeypatch, tmp_path):
        games = [
            ScheduleEntry(
                date="2026-08-07", time="17:00", home_team="Leksands IF", away_team="Djurgårdens IF",
                game_result="", periods="", spectators="", venue="Tegera Arena", game_url="", round="", status="",
            ),
        ]
        monkeypatch.setattr("src.shl.rest_api.get_live_games", lambda season_id, cache_dir: None)
        monkeypatch.setattr("src.shl.rest_api.fetch_live_games", lambda season_id, cache_dir: games)
        monkeypatch.setattr("src.shl.rest_api.get_live_games_fetched_at", lambda cache_dir, season_id: "2026-08-07T11:00:00")

        client = TestClient(create_app(tmp_path))
        response = client.get("/seasons/21139/games/live")
        assert response.status_code == 200
        payload = response.json()
        assert payload["meta"]["count"] == 1
        assert payload["data"][0]["home_team"] == "Leksands IF"

    def test_returns_502_when_fetch_fails(self, monkeypatch, tmp_path):
        monkeypatch.setattr("src.shl.rest_api.get_live_games", lambda season_id, cache_dir: None)
        monkeypatch.setattr("src.shl.rest_api.fetch_live_games", lambda season_id, cache_dir: (_ for _ in ()).throw(RuntimeError("upstream down")))

        client = TestClient(create_app(tmp_path))
        response = client.get("/seasons/21139/games/live")
        assert response.status_code == 502
        assert "Failed to fetch live games" in response.json()["error"]

    def test_returns_empty_list_when_no_games_today(self, monkeypatch, tmp_path):
        monkeypatch.setattr("src.shl.rest_api.get_live_games", lambda season_id, cache_dir: [])
        monkeypatch.setattr("src.shl.rest_api.get_live_games_fetched_at", lambda cache_dir, season_id: "2026-08-07T10:00:00")

        client = TestClient(create_app(tmp_path))
        response = client.get("/seasons/21139/games/live")
        assert response.status_code == 200
        payload = response.json()
        assert payload["data"] == []
        assert payload["meta"]["count"] == 0


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
            return []

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

    def test_success_interval_is_30_seconds(self):
        from src.shl.poller import DEFAULT_SUCCESS_INTERVAL_SECONDS

        assert DEFAULT_SUCCESS_INTERVAL_SECONDS["live_games"] == 30
