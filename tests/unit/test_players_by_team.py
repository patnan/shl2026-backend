"""Tests for PlayersByTeam feature: parsing, store, and merged endpoint integration."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.shl.helpers.stats_parsing import parse_players_by_team
from src.shl.models import RosterEntry, TeamPlayerStat


# ---------------------------------------------------------------------------
# Sample HTML mimicking SweHockey PlayersByTeam page structure
# ---------------------------------------------------------------------------

SAMPLE_HTML = """
<html>
<body>
<table class="tblContent">
  <tr><td colspan="21"><b>Brynäs IF</b></td></tr>
  <tr><td>Rk</td><td>No</td><td>Name</td><td>Pos</td><td>GP</td><td>G</td><td>A</td><td>TP</td><td>PIM</td><td>+</td><td>-</td><td>+/-</td><td>GWG</td><td>PPG</td><td>SHG</td><td>SOG</td><td>SG%</td><td>FO+</td><td>FO-</td><td>FO</td><td>FO%</td></tr>
  <tr><td>1</td><td>10</td><td><b>Lundqvist, Joel</b></td><td>C</td><td>52</td><td>15</td><td>20</td><td>35</td><td>24</td><td>30</td><td>22</td><td>8</td><td>3</td><td>5</td><td>1</td><td>120</td><td>12. 50</td><td>350</td><td>280</td><td>630</td><td>55. 56</td></tr>
  <tr><td>2</td><td>3</td><td><b>Djoos, Christian</b></td><td>RD</td><td>48</td><td>8</td><td>25</td><td>33</td><td>16</td><td>25</td><td>18</td><td>7</td><td>2</td><td>3</td><td>0</td><td>95</td><td>8. 42</td><td>0</td><td>0</td><td>0</td><td>N/A</td></tr>
</table>
<table class="tblContent">
  <tr><td colspan="21"><b>Skellefteå AIK</b></td></tr>
  <tr><td>Rk</td><td>No</td><td>Name</td><td>Pos</td><td>GP</td><td>G</td><td>A</td><td>TP</td><td>PIM</td><td>+</td><td>-</td><td>+/-</td><td>GWG</td><td>PPG</td><td>SHG</td><td>SOG</td><td>SG%</td><td>FO+</td><td>FO-</td><td>FO</td><td>FO%</td></tr>
  <tr><td>1</td><td>24</td><td><b>Lindström, Oscar</b></td><td>LW</td><td>50</td><td>22</td><td>18</td><td>40</td><td>10</td><td>35</td><td>20</td><td>15</td><td>5</td><td>7</td><td>2</td><td>150</td><td>14. 67</td><td>50</td><td>45</td><td>95</td><td>52. 63</td></tr>
</table>
<table class="tblContent">
  <tr><td colspan="21"><b>Brynäs IF</b></td></tr>
  <tr><td colspan="21">Goalkeeping Statistics</td></tr>
  <tr><td>Rk</td><td>No</td><td>Name</td><td>Team</td><td>GP</td><td>GPI</td><td>MIP</td><td>SOG</td><td>GA</td><td>GAA</td><td>SVS</td><td>SVS%</td><td>SO</td><td>W</td><td>L</td><td>W%</td></tr>
  <tr><td>1</td><td>35</td><td>Goalie, Sam</td><td>BIF</td><td>40</td><td>38</td><td>2280:00</td><td>1100</td><td>95</td><td>2.50</td><td>1005</td><td>91.36</td><td>3</td><td>20</td><td>15</td><td>57.14</td></tr>
</table>
</body>
</html>
"""

SAMPLE_HTML_SPACES_IN_PCT = """
<html>
<body>
<table class="tblContent">
  <tr><td colspan="21"><b>Test Team</b></td></tr>
  <tr><td>Rk</td><td>No</td><td>Name</td><td>Pos</td><td>GP</td><td>G</td><td>A</td><td>TP</td><td>PIM</td><td>+</td><td>-</td><td>+/-</td><td>GWG</td><td>PPG</td><td>SHG</td><td>SOG</td><td>SG%</td><td>FO+</td><td>FO-</td><td>FO</td><td>FO%</td></tr>
  <tr><td>1</td><td>7</td><td>Player, Zero</td><td>RW</td><td>10</td><td>0</td><td>5</td><td>5</td><td>2</td><td>3</td><td>4</td><td>-1</td><td>0</td><td>0</td><td>0</td><td>20</td><td>0. 00</td><td>0</td><td>0</td><td>0</td><td>N/A</td></tr>
</table>
</body>
</html>
"""


class TestParsePlayersByTeam:
    def test_parses_multiple_teams(self):
        result = parse_players_by_team(SAMPLE_HTML)
        assert len(result) == 3  # 2 from Brynäs + 1 from Skellefteå (goalie table skipped)

    def test_first_player_fields(self):
        result = parse_players_by_team(SAMPLE_HTML)
        p = result[0]
        assert p.team == "Brynäs IF"
        assert p.rank == 1
        assert p.jersey == 10
        assert p.name == "Lundqvist, Joel"
        assert p.position == "C"
        assert p.games_played == 52
        assert p.goals == 15
        assert p.assists == 20
        assert p.total_points == 35
        assert p.penalty_minutes == 24
        assert p.plus == 30
        assert p.minus == 22
        assert p.plus_minus == 8
        assert p.gwg == 3
        assert p.ppg == 5
        assert p.shg == 1
        assert p.sog == 120
        assert p.sg_pct == pytest.approx(12.50)
        assert p.fo_won == 350
        assert p.fo_lost == 280
        assert p.fo_total == 630
        assert p.fo_pct == pytest.approx(55.56)

    def test_second_player_na_fopct(self):
        result = parse_players_by_team(SAMPLE_HTML)
        p = result[1]
        assert p.team == "Brynäs IF"
        assert p.jersey == 3
        assert p.name == "Djoos, Christian"
        assert p.fo_pct is None  # N/A
        assert p.sg_pct == pytest.approx(8.42)

    def test_skelleftea_player(self):
        result = parse_players_by_team(SAMPLE_HTML)
        p = result[2]
        assert p.team == "Skellefteå AIK"
        assert p.jersey == 24
        assert p.goals == 22
        assert p.sg_pct == pytest.approx(14.67)
        assert p.fo_pct == pytest.approx(52.63)

    def test_skips_goalkeeping_table(self):
        result = parse_players_by_team(SAMPLE_HTML)
        # Goalie "Goalie, Sam" with jersey 35 should NOT be in results
        jerseys = [p.jersey for p in result]
        assert 35 not in jerseys

    def test_handles_zero_pct(self):
        result = parse_players_by_team(SAMPLE_HTML_SPACES_IN_PCT)
        assert len(result) == 1
        p = result[0]
        assert p.sg_pct == pytest.approx(0.0)
        assert p.fo_pct is None  # N/A

    def test_empty_html(self):
        result = parse_players_by_team("<html><body></body></html>")
        assert result == []

    def test_to_dict_from_dict_roundtrip(self):
        result = parse_players_by_team(SAMPLE_HTML)
        p = result[0]
        d = p.to_dict()
        restored = TeamPlayerStat.from_dict(d)
        assert restored == p

    def test_from_dict_with_none_pct(self):
        d = {
            "team": "Test",
            "rank": 1,
            "jersey": 5,
            "name": "Tester",
            "position": "C",
            "games_played": 10,
            "goals": 5,
            "assists": 3,
            "total_points": 8,
            "penalty_minutes": 4,
            "plus": 6,
            "minus": 4,
            "plus_minus": 2,
            "gwg": 1,
            "ppg": 2,
            "shg": 0,
            "sog": 30,
            "sg_pct": None,
            "fo_won": 0,
            "fo_lost": 0,
            "fo_total": 0,
            "fo_pct": None,
        }
        stat = TeamPlayerStat.from_dict(d)
        assert stat.sg_pct is None
        assert stat.fo_pct is None


class TestMergedEndpointWithStats:
    """Test that the merged player endpoints include team player stat fields."""

    @pytest.fixture
    def sample_roster(self):
        return [
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
        ]

    @pytest.fixture
    def sample_team_player_stats(self):
        return [
            TeamPlayerStat(
                team="Brynäs IF",
                rank=1,
                jersey=10,
                name="Lundqvist, Joel",
                position="C",
                games_played=52,
                goals=15,
                assists=20,
                total_points=35,
                penalty_minutes=24,
                plus=30,
                minus=22,
                plus_minus=8,
                gwg=3,
                ppg=5,
                shg=1,
                sog=120,
                sg_pct=12.50,
                fo_won=350,
                fo_lost=280,
                fo_total=630,
                fo_pct=55.56,
            ),
        ]

    @pytest.fixture
    def client(self, tmp_path):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.shl.rest_api import create_app
        return TestClient(create_app(tmp_path))

    def test_stats_detail_endpoint(self, monkeypatch, client, sample_team_player_stats):
        monkeypatch.setattr("src.shl.rest_api.fetch_team_player_stats", lambda season_id, cache_dir: sample_team_player_stats)
        monkeypatch.setattr("src.shl.rest_api.get_team_player_stats_fetched_at", lambda cache_dir, season_id: "2026-08-06T10:00:00")

        response = client.get("/seasons/20961/players/Brynäs IF/10/stats")
        assert response.status_code == 200
        data = response.json()["data"]

        assert data["games_played"] == 52
        assert data["goals"] == 15
        assert data["assists"] == 20
        assert data["total_points"] == 35
        assert data["penalty_minutes"] == 24
        assert data["plus"] == 30
        assert data["minus"] == 22
        assert data["plus_minus"] == 8
        assert data["gwg"] == 3
        assert data["ppg"] == 5
        assert data["shg"] == 1
        assert data["sog"] == 120
        assert data["sg_pct"] == pytest.approx(12.50)
        assert data["fo_won"] == 350
        assert data["fo_lost"] == 280
        assert data["fo_total"] == 630
        assert data["fo_pct"] == pytest.approx(55.56)

    def test_stats_detail_404_when_not_found(self, monkeypatch, client, sample_team_player_stats):
        monkeypatch.setattr("src.shl.rest_api.fetch_team_player_stats", lambda season_id, cache_dir: sample_team_player_stats)
        monkeypatch.setattr("src.shl.rest_api.get_team_player_stats_fetched_at", lambda cache_dir, season_id: "2026-08-06T10:00:00")

        response = client.get("/seasons/20961/players/Brynäs IF/99/stats")
        assert response.status_code == 404

    def test_stats_team_endpoint(self, monkeypatch, client, sample_team_player_stats):
        monkeypatch.setattr("src.shl.rest_api.fetch_team_player_stats", lambda season_id, cache_dir: sample_team_player_stats)
        monkeypatch.setattr("src.shl.rest_api.get_team_player_stats_fetched_at", lambda cache_dir, season_id: "2026-08-06T10:00:00")

        response = client.get("/seasons/20961/players/Brynäs IF/10/stats")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["goals"] == 15
        assert data["fo_pct"] == pytest.approx(55.56)
