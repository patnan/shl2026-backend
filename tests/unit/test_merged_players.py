"""Tests for merged player endpoints (SweHockey roster + shl.se data)."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from unittest.mock import patch

import pytest

from src.shl.models import RosterEntry


@pytest.fixture
def sample_roster():
    return [
        RosterEntry(
            team="Brynäs IF",
            jersey=3,
            name="Djoos, Christian",
            birthdate="1994-08-06",
            position="RD",
            handedness="L",
            height=181,
            weight=82,
            nationality="SWE",
            youth_club="Brynäs IF",
        ),
        RosterEntry(
            team="Brynäs IF",
            jersey=10,
            name="Lundqvist, Joel",
            birthdate="1982-03-02",
            position="C",
            handedness="L",
            height=183,
            weight=89,
            nationality="SWE",
            youth_club="Frölunda HC",
        ),
        RosterEntry(
            team="Skellefteå AIK",
            jersey=24,
            name="Lindström, Oscar",
            birthdate="1995-01-15",
            position="LW",
            handedness="L",
            height=180,
            weight=85,
            nationality="SWE",
            youth_club="Skellefteå AIK",
        ),
    ]


@pytest.fixture
def sample_shl_se_player():
    return {
        "first_name": "Christian",
        "last_name": "Djoos",
        "full_name": "Christian Djoos",
        "jersey_number": 3,
        "nationality": "SE",
        "position": "Backar",
        "position_code": "D",
        "portrait_url": "/portraits/BIF_3.png",
        "team_code": "BIF",
        "shl_se_uuid": "qQ9-0473YO4F2",
    }


@pytest.fixture
def sample_shl_se_team_players():
    return [
        {
            "first_name": "Christian",
            "last_name": "Djoos",
            "full_name": "Christian Djoos",
            "jersey_number": 3,
            "nationality": "SE",
            "position": "Backar",
            "position_code": "D",
            "portrait_url": "/portraits/BIF_3.png",
            "team_code": "BIF",
            "shl_se_uuid": "qQ9-0473YO4F2",
        },
        {
            "first_name": "Joel",
            "last_name": "Lundqvist",
            "full_name": "Joel Lundqvist",
            "jersey_number": 10,
            "nationality": "SE",
            "position": "Forwards",
            "position_code": "C",
            "portrait_url": "/portraits/BIF_10.png",
            "team_code": "BIF",
            "shl_se_uuid": "abc-12345",
        },
    ]


class TestMergedPlayerDetail:
    @pytest.fixture
    def client(self, tmp_path):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.shl.rest_api import create_app
        return TestClient(create_app(tmp_path))

    def test_returns_merged_data(self, monkeypatch, client, sample_roster, sample_shl_se_player):
        monkeypatch.setattr("src.shl.routers.players.get_rosters", lambda season_id, cache_dir: sample_roster)
        monkeypatch.setattr("src.shl.routers.players.get_shl_se_player", lambda season_id, team, jersey, cache_dir: sample_shl_se_player)
        monkeypatch.setattr("src.shl.routers.players.get_rosters_fetched_at", lambda cache_dir, season_id: "2026-08-06T10:00:00")

        response = client.get("/seasons/20961/players/Brynäs IF/3")
        assert response.status_code == 200
        data = response.json()["data"]

        # SweHockey fields
        assert data["name"] == "Djoos, Christian"
        assert data["birthdate"] == "1994-08-06"
        assert data["position"] == "RD"
        assert data["handedness"] == "L"
        assert data["height"] == 181
        assert data["weight"] == 82
        assert data["nationality"] == "SWE"
        assert data["youth_club"] == "Brynäs IF"

        # shl.se fields
        assert data["first_name"] == "Christian"
        assert data["last_name"] == "Djoos"
        assert data["portrait_url"] == "/portraits/BIF_3.png"
        assert data["team_code"] == "BIF"
        assert data["shl_se_uuid"] == "qQ9-0473YO4F2"

    def test_returns_data_without_shl_se(self, monkeypatch, client, sample_roster):
        monkeypatch.setattr("src.shl.routers.players.get_rosters", lambda season_id, cache_dir: sample_roster)
        monkeypatch.setattr("src.shl.routers.players.get_shl_se_player", lambda season_id, team, jersey, cache_dir: None)
        monkeypatch.setattr("src.shl.routers.players.fetch_shl_se_player", lambda season_id, team, jersey, cache_dir: None)
        monkeypatch.setattr("src.shl.routers.players.get_rosters_fetched_at", lambda cache_dir, season_id: "2026-08-06T10:00:00")

        response = client.get("/seasons/20961/players/Brynäs IF/3")
        assert response.status_code == 200
        data = response.json()["data"]

        # SweHockey fields present
        assert data["name"] == "Djoos, Christian"
        assert data["birthdate"] == "1994-08-06"

        # shl.se fields empty
        assert data["portrait_url"] == ""
        assert data["shl_se_uuid"] == ""

    def test_404_when_player_not_in_roster(self, monkeypatch, client, sample_roster):
        monkeypatch.setattr("src.shl.routers.players.get_rosters", lambda season_id, cache_dir: sample_roster)

        response = client.get("/seasons/20961/players/Brynäs IF/99")
        assert response.status_code == 404

    def test_lazy_loads_roster(self, monkeypatch, client, sample_roster, sample_shl_se_player):
        monkeypatch.setattr("src.shl.routers.players.get_rosters", lambda season_id, cache_dir: None)
        monkeypatch.setattr("src.shl.routers.players.fetch_rosters", lambda season_id, cache_dir: sample_roster)
        monkeypatch.setattr("src.shl.routers.players.get_shl_se_player", lambda season_id, team, jersey, cache_dir: sample_shl_se_player)
        monkeypatch.setattr("src.shl.routers.players.get_rosters_fetched_at", lambda cache_dir, season_id: "2026-08-06T10:00:00")

        response = client.get("/seasons/20961/players/Brynäs IF/3")
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Djoos, Christian"

    def test_502_when_roster_fetch_fails(self, monkeypatch, client):
        monkeypatch.setattr("src.shl.routers.players.get_rosters", lambda season_id, cache_dir: None)
        monkeypatch.setattr("src.shl.routers.players.fetch_rosters", lambda season_id, cache_dir: (_ for _ in ()).throw(RuntimeError("upstream")))

        response = client.get("/seasons/20961/players/Brynäs IF/3")
        assert response.status_code == 502


class TestMergedTeamPlayers:
    @pytest.fixture
    def client(self, tmp_path):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.shl.rest_api import create_app
        return TestClient(create_app(tmp_path))

    def test_returns_all_team_players_merged(self, monkeypatch, client, sample_roster, sample_shl_se_team_players):
        monkeypatch.setattr("src.shl.routers.players.get_rosters", lambda season_id, cache_dir: sample_roster)
        monkeypatch.setattr("src.shl.routers.players.get_shl_se_team_players", lambda season_id, team, cache_dir: sample_shl_se_team_players)
        monkeypatch.setattr("src.shl.routers.players.fetch_shl_se_team_players", lambda season_id, team, cache_dir, force_refresh: sample_shl_se_team_players)
        monkeypatch.setattr("src.shl.routers.players.get_rosters_fetched_at", lambda cache_dir, season_id: "2026-08-06T10:00:00")

        response = client.get("/seasons/20961/players/Brynäs IF")
        assert response.status_code == 200
        payload = response.json()
        assert payload["meta"]["count"] == 2

        # First player
        p1 = payload["data"][0]
        assert p1["jersey"] == 3
        assert p1["name"] == "Djoos, Christian"
        assert p1["portrait_url"] == "/portraits/BIF_3.png"
        assert p1["shl_se_uuid"] == "qQ9-0473YO4F2"

        # Second player
        p2 = payload["data"][1]
        assert p2["jersey"] == 10
        assert p2["name"] == "Lundqvist, Joel"
        assert p2["portrait_url"] == "/portraits/BIF_10.png"

    def test_empty_shl_se_for_team(self, monkeypatch, client, sample_roster):
        monkeypatch.setattr("src.shl.routers.players.get_rosters", lambda season_id, cache_dir: sample_roster)
        monkeypatch.setattr("src.shl.routers.players.get_shl_se_team_players", lambda season_id, team, cache_dir: None)
        monkeypatch.setattr("src.shl.routers.players.fetch_shl_se_team_players", lambda season_id, team, cache_dir, force_refresh: [])
        monkeypatch.setattr("src.shl.routers.players.get_rosters_fetched_at", lambda cache_dir, season_id: "2026-08-06T10:00:00")

        response = client.get("/seasons/20961/players/Brynäs IF")
        assert response.status_code == 200
        payload = response.json()
        assert payload["meta"]["count"] == 2
        # shl.se fields empty but SweHockey data present
        assert payload["data"][0]["portrait_url"] == ""
        assert payload["data"][0]["name"] == "Djoos, Christian"

    def test_404_when_team_not_in_roster(self, monkeypatch, client, sample_roster):
        monkeypatch.setattr("src.shl.routers.players.get_rosters", lambda season_id, cache_dir: sample_roster)

        response = client.get("/seasons/20961/players/NonExistent Team")
        assert response.status_code == 404

    def test_lazy_loads_roster_for_team(self, monkeypatch, client, sample_roster, sample_shl_se_team_players):
        monkeypatch.setattr("src.shl.routers.players.get_rosters", lambda season_id, cache_dir: None)
        monkeypatch.setattr("src.shl.routers.players.fetch_rosters", lambda season_id, cache_dir: sample_roster)
        monkeypatch.setattr("src.shl.routers.players.get_shl_se_team_players", lambda season_id, team, cache_dir: sample_shl_se_team_players)
        monkeypatch.setattr("src.shl.routers.players.get_rosters_fetched_at", lambda cache_dir, season_id: "2026-08-06T10:00:00")

        response = client.get("/seasons/20961/players/Brynäs IF")
        assert response.status_code == 200
        assert response.json()["meta"]["count"] == 2
