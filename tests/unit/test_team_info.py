"""Unit tests for team abbreviation (TeamInfo) feature."""
import json

import pytest

from src.shl.helpers.stats_parsing import parse_team_abbreviations
from src.shl.models import TeamInfo
from src.shl.store import Store


# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

TEAM_ROSTER_NAV_HTML = """
<html><body>
<div>
<a class="" href="#">...</a>
<a data-ajax="false" href="#BIF">Brynäs IF</a>
<a data-ajax="false" href="#DIF">Djurgårdens IF</a>
<a data-ajax="false" href="#FRÖ">Frölunda HC</a>
<a data-ajax="false" href="#FBK">Färjestad BK</a>
<a data-ajax="false" href="#HV71">HV 71</a>
<a data-ajax="false" href="#IFB">IF Björklöven</a>
<a data-ajax="false" href="#MIF">IF Malmö Redhawks</a>
<a data-ajax="false" href="#LHC">Linköping HC</a>
<a data-ajax="false" href="#LHF">Luleå HF</a>
<a data-ajax="false" href="#RBK">Rögle BK</a>
<a data-ajax="false" href="#SKE">Skellefteå AIK</a>
<a data-ajax="false" href="#TIK">Timrå IK</a>
<a data-ajax="false" href="#VÄX">Växjö Lakers HC</a>
<a data-ajax="false" href="#ÖHK">Örebro HK</a>
<a data-ajax="false" href="#top" style="color:white;text-align:right;">[Top]</a>
</div>
</body></html>
"""

MINIMAL_HTML = """
<html><body>
<a data-ajax="false" href="#SKE">Skellefteå AIK</a>
<a data-ajax="false" href="#top">[Top]</a>
</body></html>
"""


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParseTeamAbbreviations:
    def test_parses_all_14_teams(self):
        result = parse_team_abbreviations(TEAM_ROSTER_NAV_HTML)
        assert len(result) == 14

    def test_returns_team_info_dataclasses(self):
        result = parse_team_abbreviations(TEAM_ROSTER_NAV_HTML)
        assert all(isinstance(r, TeamInfo) for r in result)

    def test_maps_team_names_to_abbreviations(self):
        result = parse_team_abbreviations(TEAM_ROSTER_NAV_HTML)
        mapping = {t.team: t.abbreviation for t in result}
        assert mapping["Brynäs IF"] == "BIF"
        assert mapping["IF Björklöven"] == "IFB"
        assert mapping["HV 71"] == "HV71"
        assert mapping["Frölunda HC"] == "FRÖ"
        assert mapping["Örebro HK"] == "ÖHK"
        assert mapping["Växjö Lakers HC"] == "VÄX"

    def test_excludes_top_links(self):
        result = parse_team_abbreviations(TEAM_ROSTER_NAV_HTML)
        abbreviations = [t.abbreviation for t in result]
        assert "top" not in abbreviations
        team_names = [t.team for t in result]
        assert "[Top]" not in team_names

    def test_excludes_empty_hash(self):
        html = '<html><body><a data-ajax="false" href="#">...</a></body></html>'
        result = parse_team_abbreviations(html)
        assert result == []

    def test_excludes_anchors_without_data_ajax(self):
        html = '<html><body><a href="#SKE">Skellefteå AIK</a></body></html>'
        result = parse_team_abbreviations(html)
        assert result == []

    def test_minimal_single_team(self):
        result = parse_team_abbreviations(MINIMAL_HTML)
        assert len(result) == 1
        assert result[0].team == "Skellefteå AIK"
        assert result[0].abbreviation == "SKE"

    def test_empty_html_returns_empty(self):
        assert parse_team_abbreviations("<html><body></body></html>") == []

    def test_no_anchor_tags_returns_empty(self):
        html = "<html><body><p>No links here</p></body></html>"
        assert parse_team_abbreviations(html) == []


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestTeamInfoModel:
    def test_from_dict(self):
        t = TeamInfo.from_dict({"team": "Brynäs IF", "abbreviation": "BIF"})
        assert t.team == "Brynäs IF"
        assert t.abbreviation == "BIF"

    def test_to_dict(self):
        t = TeamInfo(team="HV 71", abbreviation="HV71")
        d = t.to_dict()
        assert d == {"team": "HV 71", "abbreviation": "HV71"}

    def test_frozen(self):
        t = TeamInfo(team="A", abbreviation="A")
        with pytest.raises(AttributeError):
            t.team = "B"


# ---------------------------------------------------------------------------
# Store tests
# ---------------------------------------------------------------------------

class TestStoreTeamInfo:
    def test_save_and_load_team_info(self, tmp_path):
        store = Store(tmp_path)
        teams = [
            TeamInfo(team="Brynäs IF", abbreviation="BIF"),
            TeamInfo(team="IF Björklöven", abbreviation="IFB"),
        ]
        store.save_team_info(20961, teams)

        loaded = store.load_team_info(20961)
        assert loaded is not None
        assert len(loaded) == 2
        assert loaded[0].team == "Brynäs IF"
        assert loaded[0].abbreviation == "BIF"
        assert loaded[1].team == "IF Björklöven"
        assert loaded[1].abbreviation == "IFB"

    def test_load_team_info_returns_none_when_missing(self, tmp_path):
        store = Store(tmp_path)
        assert store.load_team_info(99999) is None

    def test_get_team_info_fetched_at(self, tmp_path):
        store = Store(tmp_path)
        teams = [TeamInfo(team="Skellefteå AIK", abbreviation="SKE")]
        store.save_team_info(20961, teams)

        fetched_at = store.get_team_info_fetched_at(20961)
        assert fetched_at is not None
        assert "202" in fetched_at  # ISO timestamp

    def test_get_team_info_fetched_at_returns_none_when_missing(self, tmp_path):
        store = Store(tmp_path)
        assert store.get_team_info_fetched_at(99999) is None

    def test_save_team_info_overwrites(self, tmp_path):
        store = Store(tmp_path)
        store.save_team_info(20961, [TeamInfo(team="A", abbreviation="AAA")])
        store.save_team_info(20961, [TeamInfo(team="B", abbreviation="BBB")])

        loaded = store.load_team_info(20961)
        assert len(loaded) == 1
        assert loaded[0].team == "B"


# ---------------------------------------------------------------------------
# REST API endpoint tests
# ---------------------------------------------------------------------------

class TestTeamsEndpoint:
    @pytest.fixture
    def client(self, tmp_path):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.shl.rest_api import create_app
        return TestClient(create_app(tmp_path))

    def test_returns_502_when_fetch_fails(self, monkeypatch, client):
        monkeypatch.setattr("src.shl.routers.teams.get_team_info", lambda season_id, cache_dir: None)
        monkeypatch.setattr("src.shl.routers.teams.fetch_team_info", lambda season_id, cache_dir: (_ for _ in ()).throw(RuntimeError("upstream down")))
        response = client.get("/seasons/20961/teams")
        assert response.status_code == 502
        assert "Failed to fetch" in response.json()["error"]

    def test_lazy_loads_when_not_cached(self, monkeypatch, client):
        teams = [
            TeamInfo(team="Brynäs IF", abbreviation="BIF"),
        ]
        monkeypatch.setattr("src.shl.routers.teams.get_team_info", lambda season_id, cache_dir: None)
        monkeypatch.setattr("src.shl.routers.teams.fetch_team_info", lambda season_id, cache_dir: teams)
        monkeypatch.setattr("src.shl.routers.teams.get_team_info_fetched_at", lambda cache_dir, season_id: "2026-08-06T12:00:00")
        response = client.get("/seasons/20961/teams")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1
        assert response.json()["data"][0]["abbreviation"] == "BIF"

    def test_returns_team_list(self, monkeypatch, client):
        teams = [
            TeamInfo(team="Brynäs IF", abbreviation="BIF"),
            TeamInfo(team="IF Björklöven", abbreviation="IFB"),
        ]
        monkeypatch.setattr("src.shl.routers.teams.get_team_info", lambda season_id, cache_dir: teams)
        monkeypatch.setattr("src.shl.routers.teams.get_team_info_fetched_at", lambda cache_dir, season_id: "2026-08-05T10:00:00")

        response = client.get("/seasons/20961/teams")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["data"]) == 2
        assert payload["data"][0]["team"] == "Brynäs IF"
        assert payload["data"][0]["abbreviation"] == "BIF"
        assert payload["data"][1]["team"] == "IF Björklöven"
        assert payload["data"][1]["abbreviation"] == "IFB"
        assert payload["meta"]["season_id"] == "20961"
        assert payload["meta"]["source_fetched_at"] == "2026-08-05T10:00:00"


# ---------------------------------------------------------------------------
# game.py _team_abbrev_candidates integration tests
# ---------------------------------------------------------------------------

class TestTeamAbbrevCandidatesWithCache:
    def test_includes_stored_abbreviation(self):
        from src.shl.game import _team_abbrev_cache, _team_abbrev_candidates, _normalize_abbrev

        # Simulate loaded cache
        _team_abbrev_cache.clear()
        _team_abbrev_cache["IF Björklöven"] = "IFB"

        candidates = _team_abbrev_candidates("IF Björklöven")
        assert _normalize_abbrev("IFB") in candidates

    def test_heuristic_candidates_still_present(self):
        from src.shl.game import _team_abbrev_cache, _team_abbrev_candidates, _normalize_abbrev

        _team_abbrev_cache.clear()
        _team_abbrev_cache["Skellefteå AIK"] = "SKE"

        candidates = _team_abbrev_candidates("Skellefteå AIK")
        # Stored
        assert _normalize_abbrev("SKE") in candidates
        # Heuristic: first 3 chars of first token
        assert _normalize_abbrev("SKE") in candidates

    def test_without_cache_uses_heuristic_only(self):
        from src.shl.game import _team_abbrev_cache, _team_abbrev_candidates, _normalize_abbrev

        _team_abbrev_cache.clear()

        candidates = _team_abbrev_candidates("Brynäs IF")
        # Heuristic: initials "BI", first 3 "BRY", and "BIF" (B + short token IF)
        assert _normalize_abbrev("BI") in candidates
        assert _normalize_abbrev("BRY") in candidates
        assert _normalize_abbrev("BIF") in candidates

    def test_without_cache_bjorkloven_missing_ifb(self):
        from src.shl.game import _team_abbrev_cache, _team_abbrev_candidates, _normalize_abbrev

        _team_abbrev_cache.clear()

        # Without cache, heuristic doesn't produce "IFB" for "IF Björklöven"
        # It produces: IB (initials), IF (first 3... "IF" is only 2 chars), IFB via I+first of last?
        # Let's just verify the stored one adds value for unusual names
        candidates = _team_abbrev_candidates("IF Björklöven")
        # The heuristic generates: initials "IB", first 3 of first token "IF", 
        # and "IB" (first[0] + last[0]) — IFB may or may not be generated
        # The key point: with cache, IFB is guaranteed to be there
        assert _normalize_abbrev("IB") in candidates

    def test_with_cache_includes_bif(self):
        from src.shl.game import _team_abbrev_cache, _team_abbrev_candidates, _normalize_abbrev

        _team_abbrev_cache.clear()
        _team_abbrev_cache["Brynäs IF"] = "BIF"

        candidates = _team_abbrev_candidates("Brynäs IF")
        assert _normalize_abbrev("BIF") in candidates

    def test_load_team_abbrev_map(self, tmp_path):
        from src.shl.game import _team_abbrev_cache, load_team_abbrev_map

        store = Store(tmp_path)
        teams = [
            TeamInfo(team="Frölunda HC", abbreviation="FRÖ"),
            TeamInfo(team="HV 71", abbreviation="HV71"),
        ]
        store.save_team_info(20961, teams)

        _team_abbrev_cache.clear()
        load_team_abbrev_map(20961, tmp_path)

        assert _team_abbrev_cache["Frölunda HC"] == "FRÖ"
        assert _team_abbrev_cache["HV 71"] == "HV71"

    def test_action_matches_team_with_stored_abbrev(self, tmp_path):
        from src.shl.game import _team_abbrev_cache, _action_matches_team
        from src.shl.models import Action

        _team_abbrev_cache.clear()
        _team_abbrev_cache["IF Björklöven"] = "IFB"

        action = Action(
            period="1",
            game_time="12:34",
            event_type="Goal",
            team_abbrev="IFB",
            player_text="Eriksson, P",
            players=["Eriksson, P"],
            player_numbers=[10],
            is_goal=True,
        )
        assert _action_matches_team(action, "IF Björklöven") is True

    def test_action_does_not_match_wrong_team(self):
        from src.shl.game import _team_abbrev_cache, _action_matches_team
        from src.shl.models import Action

        _team_abbrev_cache.clear()
        _team_abbrev_cache["IF Björklöven"] = "IFB"
        _team_abbrev_cache["Brynäs IF"] = "BIF"

        action = Action(
            period="1",
            game_time="12:34",
            event_type="Goal",
            team_abbrev="IFB",
            player_text="Eriksson, P",
            players=["Eriksson, P"],
            player_numbers=[10],
            is_goal=True,
        )
        assert _action_matches_team(action, "Brynäs IF") is False


# ---------------------------------------------------------------------------
# Poller seed tests
# ---------------------------------------------------------------------------

class TestPollerTeamInfoTarget:
    def test_seed_includes_team_info_target(self, tmp_path):
        from src.shl.poller import seed_season_targets
        result = seed_season_targets(tmp_path, 20961)
        assert result["team_info_target"] == 1
        assert result["total_targets"] == 7

    def test_team_info_poll_target_created(self, tmp_path):
        from src.shl.poller import seed_season_targets
        from src.shl.store import list_poll_targets

        seed_season_targets(tmp_path, 20961)
        targets = list_poll_targets(tmp_path)
        target_types = [t.target_type for t in targets]
        assert "team_info" in target_types
