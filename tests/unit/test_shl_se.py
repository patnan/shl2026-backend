"""Unit tests for shl_se module (SweHockey ↔ shl.se mapping)."""
import pytest

from src.shl.shl_se import (
    PlayerMapper,
    ShlSePlayer,
    ShlSeTeam,
    TeamMapper,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TEAMS = [
    ShlSeTeam(uuid="1ab8-1ab8bfj7N", team_code="BIF", instance_id="bif1_bif",
              name_short="Brynäs", name_long="Brynäs IF", name_full="Brynäs Idrottsförening",
              logo_url="https://sportality.cdn.s8y.se/team-logos/bif1_bif.svg"),
    ShlSeTeam(uuid="087a-087aTQv9u", team_code="FHC", instance_id="fhc1_fhc",
              name_short="Frölunda", name_long="Frölunda HC", name_full="Frölunda Hockey Club",
              logo_url="https://sportality.cdn.s8y.se/team-logos/fhc1_fhc.svg"),
    ShlSeTeam(uuid="3db0-3db09jXTE", team_code="HV71", instance_id="hv711_hv71",
              name_short="HV71", name_long="HV71", name_full="HV71",
              logo_url="https://sportality.cdn.s8y.se/team-logos/hv711_hv71.svg"),
    ShlSeTeam(uuid="4519-4519Rdei6", team_code="IFB", instance_id="ifb1_ifb",
              name_short="Björklöven", name_long="Björklöven", name_full="Idrottsföreningen Björklöven",
              logo_url="https://sportality.cdn.s8y.se/team-logos/ifb1_ifb.svg"),
    ShlSeTeam(uuid="50e6-50e6DYeWM", team_code="SAIK", instance_id="ske1_ske",
              name_short="Skellefteå", name_long="Skellefteå AIK", name_full="Skellefteå AIK Hockey",
              logo_url="https://sportality.cdn.s8y.se/team-logos/ske1_ske.svg"),
    ShlSeTeam(uuid="8e6f-8e6fUXJvi", team_code="MIF", instance_id="mif1_mif",
              name_short="Malmö", name_long="Malmö Redhawks", name_full="Malmö Redhawks",
              logo_url="https://sportality.cdn.s8y.se/team-logos/mif1_mif.svg"),
    ShlSeTeam(uuid="fe02-fe02mf1FN", team_code="VLH", instance_id="vlh1_vlh",
              name_short="Växjö", name_long="Växjö Lakers", name_full="Växjö Lakers",
              logo_url="https://sportality.cdn.s8y.se/team-logos/vlh1_vlh.svg"),
    ShlSeTeam(uuid="82eb-82ebmgaJ8", team_code="OHK", instance_id="ohk1_ohk",
              name_short="Örebro", name_long="Örebro Hockey", name_full="Örebro Hockey",
              logo_url="https://sportality.cdn.s8y.se/team-logos/ohk1_ohk.svg"),
]

SWH_TEAM_NAMES = [
    "Brynäs IF", "Frölunda HC", "HV 71", "IF Björklöven",
    "Skellefteå AIK", "IF Malmö Redhawks", "Växjö Lakers HC", "Örebro HK",
]


@pytest.fixture
def team_mapper():
    return TeamMapper(SAMPLE_TEAMS)


# ---------------------------------------------------------------------------
# TeamMapper tests
# ---------------------------------------------------------------------------

class TestTeamMapper:
    def test_swehockey_to_shl_se_exact_short(self, team_mapper):
        """Short name is substring of SweHockey name."""
        result = team_mapper.swehockey_to_shl_se("Brynäs IF")
        assert result is not None
        assert result.team_code == "BIF"
        assert result.uuid == "1ab8-1ab8bfj7N"

    def test_swehockey_to_shl_se_frolunda(self, team_mapper):
        """'Frölunda' is in 'Frölunda HC'."""
        result = team_mapper.swehockey_to_shl_se("Frölunda HC")
        assert result is not None
        assert result.team_code == "FHC"

    def test_swehockey_to_shl_se_skelleftea(self, team_mapper):
        """'Skellefteå' is in 'Skellefteå AIK'."""
        result = team_mapper.swehockey_to_shl_se("Skellefteå AIK")
        assert result is not None
        assert result.team_code == "SAIK"

    def test_swehockey_to_shl_se_vaxjo(self, team_mapper):
        """'Växjö' is in 'Växjö Lakers HC'."""
        result = team_mapper.swehockey_to_shl_se("Växjö Lakers HC")
        assert result is not None
        assert result.team_code == "VLH"

    def test_swehockey_to_shl_se_orebro(self, team_mapper):
        """'Örebro' is in 'Örebro HK'."""
        result = team_mapper.swehockey_to_shl_se("Örebro HK")
        assert result is not None
        assert result.team_code == "OHK"

    def test_swehockey_to_shl_se_hv71_space(self, team_mapper):
        """'HV 71' vs 'HV71' — fallback normalized matching."""
        result = team_mapper.swehockey_to_shl_se("HV 71")
        assert result is not None
        assert result.team_code == "HV71"

    def test_swehockey_to_shl_se_bjorkloven(self, team_mapper):
        """'Björklöven' is in 'IF Björklöven'."""
        result = team_mapper.swehockey_to_shl_se("IF Björklöven")
        assert result is not None
        assert result.team_code == "IFB"

    def test_swehockey_to_shl_se_malmo(self, team_mapper):
        """'Malmö' is in 'IF Malmö Redhawks'."""
        result = team_mapper.swehockey_to_shl_se("IF Malmö Redhawks")
        assert result is not None
        assert result.team_code == "MIF"

    def test_swehockey_to_shl_se_unknown_returns_none(self, team_mapper):
        result = team_mapper.swehockey_to_shl_se("Nonexistent Team FC")
        assert result is None

    def test_shl_se_to_swehockey(self, team_mapper):
        """Reverse mapping: shl.se team → SweHockey name."""
        fhc = team_mapper.get_team_by_code("FHC")
        result = team_mapper.shl_se_to_swehockey(fhc, SWH_TEAM_NAMES)
        assert result == "Frölunda HC"

    def test_shl_se_to_swehockey_hv71(self, team_mapper):
        hv = team_mapper.get_team_by_code("HV71")
        result = team_mapper.shl_se_to_swehockey(hv, SWH_TEAM_NAMES)
        assert result == "HV 71"

    def test_shl_se_to_swehockey_unknown_returns_none(self, team_mapper):
        fake = ShlSeTeam(uuid="x", team_code="X", instance_id="x",
                         name_short="Nonexistent", name_long="Nonexistent", name_full="",
                         logo_url="")
        result = team_mapper.shl_se_to_swehockey(fake, SWH_TEAM_NAMES)
        assert result is None

    def test_get_team_by_code(self, team_mapper):
        result = team_mapper.get_team_by_code("SAIK")
        assert result is not None
        assert result.name_short == "Skellefteå"

    def test_get_team_by_code_not_found(self, team_mapper):
        assert team_mapper.get_team_by_code("XXX") is None

    def test_get_team_by_uuid(self, team_mapper):
        result = team_mapper.get_team_by_uuid("4519-4519Rdei6")
        assert result is not None
        assert result.team_code == "IFB"

    def test_teams_property(self, team_mapper):
        assert len(team_mapper.teams) == len(SAMPLE_TEAMS)

    def test_all_swehockey_teams_match(self, team_mapper):
        """All SweHockey team names should find a match."""
        for swh_name in SWH_TEAM_NAMES:
            result = team_mapper.swehockey_to_shl_se(swh_name)
            assert result is not None, f"No match for '{swh_name}'"


# ---------------------------------------------------------------------------
# PlayerMapper tests
# ---------------------------------------------------------------------------

class TestPlayerMapper:
    @pytest.fixture
    def player_mapper(self, team_mapper, monkeypatch):
        """PlayerMapper with a mocked roster for Björklöven."""
        mapper = PlayerMapper(team_mapper)

        # Mock the roster fetch
        mock_roster = [
            ShlSePlayer(uuid="p1", first_name="Oscar", last_name="Lindberg",
                        full_name="Oscar Lindberg", jersey_number=24,
                        nationality="SE", position="Forwards", position_code="F",
                        portrait_url="https://example.com/lindberg.png"),
            ShlSePlayer(uuid="p2", first_name="Lassi", last_name="Lehtinen",
                        full_name="Lassi Lehtinen", jersey_number=30,
                        nationality="FI", position="Målvakter", position_code="GK",
                        portrait_url="https://example.com/lehtinen.png"),
            ShlSePlayer(uuid="p3", first_name="Topi", last_name="Niemelä",
                        full_name="Topi Niemelä", jersey_number=7,
                        nationality="FI", position="Backar", position_code="D",
                        portrait_url=""),
        ]
        monkeypatch.setattr("src.shl.shl_se.fetch_shl_se_roster", lambda uuid, timeout=10: mock_roster)
        return mapper

    def test_load_team(self, player_mapper):
        assert player_mapper.load_team("IF Björklöven") is True
        assert player_mapper.is_loaded("IF Björklöven")

    def test_load_team_unknown(self, player_mapper):
        assert player_mapper.load_team("Unknown FC") is False

    def test_find_player_by_jersey(self, player_mapper):
        player_mapper.load_team("IF Björklöven")
        player = player_mapper.find("IF Björklöven", 24)
        assert player is not None
        assert player.full_name == "Oscar Lindberg"
        assert player.uuid == "p1"

    def test_find_goalie(self, player_mapper):
        player_mapper.load_team("IF Björklöven")
        player = player_mapper.find("IF Björklöven", 30)
        assert player is not None
        assert player.full_name == "Lassi Lehtinen"
        assert player.position_code == "GK"

    def test_find_nonexistent_jersey(self, player_mapper):
        player_mapper.load_team("IF Björklöven")
        assert player_mapper.find("IF Björklöven", 99) is None

    def test_find_unloaded_team(self, player_mapper):
        assert player_mapper.find("Brynäs IF", 24) is None

    def test_get_portrait_url(self, player_mapper):
        player_mapper.load_team("IF Björklöven")
        url = player_mapper.get_portrait_url("IF Björklöven", 24)
        assert url == "https://example.com/lindberg.png"

    def test_get_portrait_url_empty(self, player_mapper):
        player_mapper.load_team("IF Björklöven")
        url = player_mapper.get_portrait_url("IF Björklöven", 7)
        assert url == ""

    def test_get_portrait_url_not_found(self, player_mapper):
        player_mapper.load_team("IF Björklöven")
        assert player_mapper.get_portrait_url("IF Björklöven", 99) is None

    def test_get_team_logo_url(self, player_mapper):
        url = player_mapper.get_team_logo_url("IF Björklöven")
        assert url == "https://sportality.cdn.s8y.se/team-logos/ifb1_ifb.svg"

    def test_get_team_logo_url_unknown(self, player_mapper):
        assert player_mapper.get_team_logo_url("Unknown FC") is None

    def test_loaded_teams(self, player_mapper):
        assert player_mapper.loaded_teams == []
        player_mapper.load_team("IF Björklöven")
        assert player_mapper.loaded_teams == ["IF Björklöven"]

    def test_load_all_teams(self, player_mapper):
        count = player_mapper.load_all_teams(["IF Björklöven", "Brynäs IF", "Unknown FC"])
        # Björklöven and Brynäs should match, Unknown won't
        assert count == 2
        assert player_mapper.is_loaded("IF Björklöven")
        assert player_mapper.is_loaded("Brynäs IF")
        assert not player_mapper.is_loaded("Unknown FC")


# ---------------------------------------------------------------------------
# ShlSeTeam.from_api tests
# ---------------------------------------------------------------------------

class TestShlSeTeamFromApi:
    def test_from_api(self):
        raw = {
            "uuid": "abc-123",
            "teamCode": "TST",
            "ownerInstanceId": "tst1_tst",
            "teamNames": {"short": "Test", "long": "Test Team", "full": "Test Team Hockey"},
            "logo": "https://example.com/logo.svg",
        }
        team = ShlSeTeam.from_api(raw)
        assert team.uuid == "abc-123"
        assert team.team_code == "TST"
        assert team.instance_id == "tst1_tst"
        assert team.name_short == "Test"
        assert team.name_long == "Test Team"
        assert team.name_full == "Test Team Hockey"
        assert team.logo_url == "https://example.com/logo.svg"

    def test_from_api_uses_icon_fallback(self):
        raw = {
            "uuid": "x",
            "teamCode": "X",
            "instanceId": "x1_x",
            "teamNames": {"short": "X", "long": "X", "full": "X"},
            "logo": "",
            "icon": "https://example.com/icon.svg",
        }
        team = ShlSeTeam.from_api(raw)
        assert team.logo_url == "https://example.com/icon.svg"


# ---------------------------------------------------------------------------
# Store: shl_se_players table tests
# ---------------------------------------------------------------------------

class TestStoreShlSePlayers:
    def test_save_and_load_player(self, tmp_path):
        from src.shl.store import Store
        store = Store(tmp_path)
        data = {"first_name": "Oscar", "last_name": "Lindberg", "jersey_number": 24}
        store.save_shl_se_player(20961, "Skellefteå AIK", 24, data, "portraits/SAIK_24.png")

        result = store.load_shl_se_player(20961, "Skellefteå AIK", 24)
        assert result is not None
        assert result["data"] == data
        assert result["portrait_path"] == "portraits/SAIK_24.png"
        assert result["team"] == "Skellefteå AIK"
        assert result["jersey"] == 24

    def test_load_player_not_found(self, tmp_path):
        from src.shl.store import Store
        store = Store(tmp_path)
        assert store.load_shl_se_player(20961, "Unknown", 99) is None

    def test_load_team_players(self, tmp_path):
        from src.shl.store import Store
        store = Store(tmp_path)
        store.save_shl_se_player(20961, "Brynäs IF", 3, {"name": "A"}, "portraits/BIF_3.png")
        store.save_shl_se_player(20961, "Brynäs IF", 5, {"name": "B"}, "portraits/BIF_5.png")
        store.save_shl_se_player(20961, "Frölunda HC", 30, {"name": "C"}, None)

        result = store.load_shl_se_team_players(20961, "Brynäs IF")
        assert len(result) == 2
        assert result[0]["jersey"] == 3
        assert result[1]["jersey"] == 5

    def test_load_team_players_empty(self, tmp_path):
        from src.shl.store import Store
        store = Store(tmp_path)
        assert store.load_shl_se_team_players(20961, "Unknown") == []

    def test_get_fetched_at(self, tmp_path):
        from src.shl.store import Store
        store = Store(tmp_path)
        store.save_shl_se_player(20961, "HV 71", 10, {"name": "X"}, None)
        fetched = store.get_shl_se_player_fetched_at(20961, "HV 71", 10)
        assert fetched is not None
        assert "202" in fetched

    def test_save_overwrites(self, tmp_path):
        from src.shl.store import Store
        store = Store(tmp_path)
        store.save_shl_se_player(20961, "HV 71", 10, {"v": 1}, None)
        store.save_shl_se_player(20961, "HV 71", 10, {"v": 2}, "portraits/HV71_10.png")
        result = store.load_shl_se_player(20961, "HV 71", 10)
        assert result["data"] == {"v": 2}
        assert result["portrait_path"] == "portraits/HV71_10.png"


# ---------------------------------------------------------------------------
# download_portrait tests
# ---------------------------------------------------------------------------

class TestDownloadPortrait:
    def test_empty_url_returns_none(self, tmp_path):
        from src.shl.shl_se import download_portrait
        assert download_portrait("", tmp_path, "BIF", 3) is None

    def test_successful_download(self, tmp_path, monkeypatch):
        from src.shl.shl_se import download_portrait
        import httpx

        class FakeResponse:
            status_code = 200
            content = b"\x89PNG\r\n\x1a\n fake image data"
            def raise_for_status(self): pass

        monkeypatch.setattr(httpx, "get", lambda *a, **kw: FakeResponse())

        result = download_portrait("https://example.com/img.png", tmp_path, "SAIK", 24)
        assert result == "portraits/SAIK_24.png"
        assert (tmp_path / "portraits" / "SAIK_24.png").exists()

    def test_failed_download_returns_none(self, tmp_path, monkeypatch):
        from src.shl.shl_se import download_portrait
        import httpx

        def failing_get(*a, **kw):
            raise httpx.HTTPError("timeout")

        monkeypatch.setattr(httpx, "get", failing_get)

        result = download_portrait("https://example.com/img.png", tmp_path, "BIF", 3)
        assert result is None


# ---------------------------------------------------------------------------
# fetch/get function tests
# ---------------------------------------------------------------------------

class TestFetchGetShlSePlayers:
    def test_get_shl_se_player_returns_none_when_empty(self, tmp_path):
        from src.shl.shl_se import get_shl_se_player
        assert get_shl_se_player(20961, "Brynäs IF", 3, tmp_path) is None

    def test_get_shl_se_player_returns_persisted(self, tmp_path):
        from src.shl.store import Store
        from src.shl.shl_se import get_shl_se_player
        store = Store(tmp_path)
        data = {"first_name": "Test", "jersey_number": 3}
        store.save_shl_se_player(20961, "Brynäs IF", 3, data, None)

        result = get_shl_se_player(20961, "Brynäs IF", 3, tmp_path)
        assert result == data

    def test_get_shl_se_team_players_returns_none_when_empty(self, tmp_path):
        from src.shl.shl_se import get_shl_se_team_players
        assert get_shl_se_team_players(20961, "Unknown", tmp_path) is None

    def test_get_shl_se_team_players_returns_list(self, tmp_path):
        from src.shl.store import Store
        from src.shl.shl_se import get_shl_se_team_players
        store = Store(tmp_path)
        store.save_shl_se_player(20961, "Brynäs IF", 3, {"name": "A"}, None)
        store.save_shl_se_player(20961, "Brynäs IF", 5, {"name": "B"}, None)

        result = get_shl_se_team_players(20961, "Brynäs IF", tmp_path)
        assert result is not None
        assert len(result) == 2


# ---------------------------------------------------------------------------
# REST API endpoint tests
# ---------------------------------------------------------------------------

class TestShlSeEndpoints:
    @pytest.fixture
    def client(self, tmp_path):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from src.shl.rest_api import create_app
        return TestClient(create_app(tmp_path))

    def test_player_endpoint_404_when_not_found(self, monkeypatch, client):
        monkeypatch.setattr("src.shl.rest_api.get_shl_se_player", lambda *a, **kw: None)
        monkeypatch.setattr("src.shl.rest_api.fetch_shl_se_player", lambda *a, **kw: None)
        response = client.get("/seasons/20961/shl-se/players/Unknown%20FC/99")
        assert response.status_code == 404

    def test_player_endpoint_returns_data(self, monkeypatch, client):
        data = {"first_name": "Oscar", "last_name": "Lindberg", "jersey_number": 24,
                "portrait_url": "/portraits/SAIK_24.png", "team_code": "SAIK"}
        monkeypatch.setattr("src.shl.rest_api.get_shl_se_player", lambda *a, **kw: data)
        monkeypatch.setattr("src.shl.rest_api.get_shl_se_player_fetched_at", lambda *a: "2026-08-05T12:00:00")

        response = client.get("/seasons/20961/shl-se/players/Skellefte%C3%A5%20AIK/24")
        assert response.status_code == 200
        payload = response.json()
        assert payload["data"]["first_name"] == "Oscar"
        assert payload["data"]["portrait_url"] == "/portraits/SAIK_24.png"
        assert payload["meta"]["season_id"] == "20961"

    def test_team_endpoint_404_when_not_found(self, monkeypatch, client):
        monkeypatch.setattr("src.shl.rest_api.get_shl_se_team_players", lambda *a, **kw: None)
        monkeypatch.setattr("src.shl.rest_api.fetch_shl_se_team_players", lambda *a, **kw: [])
        monkeypatch.setattr("src.shl.rest_api.load_shl_se_team_players", lambda *a: [])
        response = client.get("/seasons/20961/shl-se/players/Unknown%20FC")
        assert response.status_code == 404

    def test_team_endpoint_returns_data(self, monkeypatch, client):
        data = [
            {"first_name": "Oscar", "jersey_number": 24},
            {"first_name": "Lassi", "jersey_number": 30},
        ]
        monkeypatch.setattr("src.shl.rest_api.get_shl_se_team_players", lambda *a, **kw: data)
        monkeypatch.setattr("src.shl.rest_api.load_shl_se_team_players", lambda *a: [
            {"fetched_at": "2026-08-05T12:00:00"}
        ])

        response = client.get("/seasons/20961/shl-se/players/Skellefte%C3%A5%20AIK")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["data"]) == 2
        assert payload["meta"]["count"] == 2
