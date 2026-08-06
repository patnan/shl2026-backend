"""Tests for shl_se fetch functions (fetch_shl_se_player, fetch_shl_se_team_players, download_portrait).

These test the high-level functions with mocked HTTP/DB calls.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.shl.shl_se import (
    ShlSePlayer,
    ShlSeTeam,
    TeamMapper,
    _player_to_dict,
    download_portrait,
    fetch_shl_se_player,
    fetch_shl_se_team_players,
    get_shl_se_player,
    get_shl_se_team_players,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TEAM = ShlSeTeam(
    uuid="1ab8-1ab8bfj7N", team_code="BIF", instance_id="bif1_bif",
    name_short="Brynäs", name_long="Brynäs IF", name_full="Brynäs Idrottsförening",
    logo_url="https://example.com/logo.svg",
)

SAMPLE_PLAYER = ShlSePlayer(
    uuid="qQ9-player1", first_name="Christian", last_name="Djoos",
    full_name="Christian Djoos", jersey_number=3,
    nationality="SE", position="Backar", position_code="D",
    portrait_url="https://example.com/djoos.png",
)

SAMPLE_PLAYER_NO_PORTRAIT = ShlSePlayer(
    uuid="qQ9-player2", first_name="Erik", last_name="Källgren",
    full_name="Erik Källgren", jersey_number=31,
    nationality="SE", position="Målvakter", position_code="GK",
    portrait_url="",
)


@pytest.fixture
def mock_team_mapper():
    mapper = TeamMapper([SAMPLE_TEAM])
    return mapper


@pytest.fixture(autouse=True)
def reset_mapper_singleton():
    """Reset the module-level singleton before each test."""
    import src.shl.shl_se as shl_se_mod
    shl_se_mod._team_mapper_instance = None
    yield
    shl_se_mod._team_mapper_instance = None


# ---------------------------------------------------------------------------
# _player_to_dict
# ---------------------------------------------------------------------------

class TestPlayerToDict:
    def test_with_portrait(self):
        result = _player_to_dict(SAMPLE_PLAYER, "BIF", "portraits/BIF_3.png")
        assert result["first_name"] == "Christian"
        assert result["last_name"] == "Djoos"
        assert result["full_name"] == "Christian Djoos"
        assert result["jersey_number"] == 3
        assert result["nationality"] == "SE"
        assert result["position"] == "Backar"
        assert result["position_code"] == "D"
        assert result["portrait_url"] == "/portraits/BIF_3.png"
        assert result["team_code"] == "BIF"
        assert result["shl_se_uuid"] == "qQ9-player1"

    def test_without_portrait(self):
        result = _player_to_dict(SAMPLE_PLAYER_NO_PORTRAIT, "BIF", None)
        assert result["portrait_url"] == ""
        assert result["jersey_number"] == 31


# ---------------------------------------------------------------------------
# download_portrait
# ---------------------------------------------------------------------------

class TestDownloadPortrait:
    def test_empty_url_returns_none(self, tmp_path):
        assert download_portrait("", tmp_path, "BIF", 3) is None

    def test_successful_download(self, tmp_path):
        mock_response = MagicMock()
        mock_response.content = b"\x89PNG fake image data"
        mock_response.raise_for_status = MagicMock()

        with patch("src.shl.shl_se.httpx.get", return_value=mock_response):
            result = download_portrait("https://example.com/photo.png", tmp_path, "BIF", 3)

        assert result == "portraits/BIF_3.png"
        assert (tmp_path / "portraits" / "BIF_3.png").exists()
        assert (tmp_path / "portraits" / "BIF_3.png").read_bytes() == b"\x89PNG fake image data"

    def test_network_error_returns_none(self, tmp_path):
        with patch("src.shl.shl_se.httpx.get", side_effect=Exception("Connection refused")):
            result = download_portrait("https://example.com/photo.png", tmp_path, "BIF", 3)

        assert result is None
        assert not (tmp_path / "portraits" / "BIF_3.png").exists()


# ---------------------------------------------------------------------------
# fetch_shl_se_player
# ---------------------------------------------------------------------------

class TestFetchShlSePlayer:
    def test_returns_cached_data(self, tmp_path):
        cached = {
            "data": {"full_name": "Cached Player", "jersey_number": 3},
            "portrait_path": "portraits/BIF_3.png",
            "fetched_at": "2026-01-01T00:00:00Z",
        }
        with patch("src.shl.shl_se.load_shl_se_player", return_value=cached):
            result = fetch_shl_se_player(20961, "Brynäs IF", 3, tmp_path)

        assert result == {"full_name": "Cached Player", "jersey_number": 3}

    def test_fetches_from_api_on_cache_miss(self, tmp_path):
        with patch("src.shl.shl_se.load_shl_se_player", return_value=None), \
             patch("src.shl.shl_se._get_team_mapper", return_value=TeamMapper([SAMPLE_TEAM])), \
             patch("src.shl.shl_se.fetch_shl_se_roster", return_value=[SAMPLE_PLAYER, SAMPLE_PLAYER_NO_PORTRAIT]), \
             patch("src.shl.shl_se.download_portrait", return_value="portraits/BIF_3.png"), \
             patch("src.shl.shl_se.save_shl_se_player") as mock_save:
            result = fetch_shl_se_player(20961, "Brynäs IF", 3, tmp_path)

        assert result is not None
        assert result["full_name"] == "Christian Djoos"
        assert result["team_code"] == "BIF"
        assert result["portrait_url"] == "/portraits/BIF_3.png"
        mock_save.assert_called_once()

    def test_returns_none_for_unknown_team(self, tmp_path):
        with patch("src.shl.shl_se.load_shl_se_player", return_value=None), \
             patch("src.shl.shl_se._get_team_mapper", return_value=TeamMapper([SAMPLE_TEAM])):
            result = fetch_shl_se_player(20961, "Unknown FC", 3, tmp_path)

        assert result is None

    def test_returns_none_for_unknown_jersey(self, tmp_path):
        with patch("src.shl.shl_se.load_shl_se_player", return_value=None), \
             patch("src.shl.shl_se._get_team_mapper", return_value=TeamMapper([SAMPLE_TEAM])), \
             patch("src.shl.shl_se.fetch_shl_se_roster", return_value=[SAMPLE_PLAYER]):
            result = fetch_shl_se_player(20961, "Brynäs IF", 99, tmp_path)

        assert result is None

    def test_returns_none_when_roster_fetch_fails(self, tmp_path):
        with patch("src.shl.shl_se.load_shl_se_player", return_value=None), \
             patch("src.shl.shl_se._get_team_mapper", return_value=TeamMapper([SAMPLE_TEAM])), \
             patch("src.shl.shl_se.fetch_shl_se_roster", side_effect=Exception("API timeout")):
            result = fetch_shl_se_player(20961, "Brynäs IF", 3, tmp_path)

        assert result is None

    def test_returns_none_when_team_mapper_fails(self, tmp_path):
        """Bug fix: _get_team_mapper() network error should not crash."""
        with patch("src.shl.shl_se.load_shl_se_player", return_value=None), \
             patch("src.shl.shl_se._get_team_mapper", side_effect=Exception("Connection refused")):
            result = fetch_shl_se_player(20961, "Brynäs IF", 3, tmp_path)

        assert result is None

    def test_force_refresh_skips_cache(self, tmp_path):
        with patch("src.shl.shl_se.load_shl_se_player", return_value=None) as mock_load, \
             patch("src.shl.shl_se._get_team_mapper", return_value=TeamMapper([SAMPLE_TEAM])), \
             patch("src.shl.shl_se.fetch_shl_se_roster", return_value=[SAMPLE_PLAYER]), \
             patch("src.shl.shl_se.download_portrait", return_value="portraits/BIF_3.png"), \
             patch("src.shl.shl_se.save_shl_se_player"):
            result = fetch_shl_se_player(20961, "Brynäs IF", 3, tmp_path, force_refresh=True)

        # load_shl_se_player should not have been called
        mock_load.assert_not_called()
        assert result is not None


# ---------------------------------------------------------------------------
# fetch_shl_se_team_players
# ---------------------------------------------------------------------------

class TestFetchShlSeTeamPlayers:
    def test_returns_cached_data(self, tmp_path):
        cached = [
            {"data": {"full_name": "Player A", "jersey_number": 3}, "fetched_at": "2026-01-01"},
            {"data": {"full_name": "Player B", "jersey_number": 31}, "fetched_at": "2026-01-01"},
            {"data": {"full_name": "Player C", "jersey_number": 10}, "fetched_at": "2026-01-01"},
            {"data": {"full_name": "Player D", "jersey_number": 14}, "fetched_at": "2026-01-01"},
            {"data": {"full_name": "Player E", "jersey_number": 21}, "fetched_at": "2026-01-01"},
        ]
        with patch("src.shl.shl_se.load_shl_se_team_players", return_value=cached):
            result = fetch_shl_se_team_players(20961, "Brynäs IF", tmp_path)

        assert len(result) == 5
        assert result[0]["full_name"] == "Player A"

    def test_fetches_from_api_on_cache_miss(self, tmp_path):
        with patch("src.shl.shl_se.load_shl_se_team_players", return_value=[]), \
             patch("src.shl.shl_se._get_team_mapper", return_value=TeamMapper([SAMPLE_TEAM])), \
             patch("src.shl.shl_se.fetch_shl_se_roster", return_value=[SAMPLE_PLAYER, SAMPLE_PLAYER_NO_PORTRAIT]), \
             patch("src.shl.shl_se.download_portrait", return_value=None), \
             patch("src.shl.shl_se.save_shl_se_player") as mock_save:
            result = fetch_shl_se_team_players(20961, "Brynäs IF", tmp_path)

        assert len(result) == 2
        assert result[0]["full_name"] == "Christian Djoos"
        assert result[1]["full_name"] == "Erik Källgren"
        assert mock_save.call_count == 2

    def test_returns_empty_for_unknown_team(self, tmp_path):
        with patch("src.shl.shl_se.load_shl_se_team_players", return_value=[]), \
             patch("src.shl.shl_se._get_team_mapper", return_value=TeamMapper([SAMPLE_TEAM])):
            result = fetch_shl_se_team_players(20961, "Unknown FC", tmp_path)

        assert result == []

    def test_returns_empty_when_roster_fetch_fails(self, tmp_path):
        with patch("src.shl.shl_se.load_shl_se_team_players", return_value=[]), \
             patch("src.shl.shl_se._get_team_mapper", return_value=TeamMapper([SAMPLE_TEAM])), \
             patch("src.shl.shl_se.fetch_shl_se_roster", side_effect=Exception("API timeout")):
            result = fetch_shl_se_team_players(20961, "Brynäs IF", tmp_path)

        assert result == []

    def test_returns_empty_when_team_mapper_fails(self, tmp_path):
        """Bug fix: _get_team_mapper() network error should not crash."""
        with patch("src.shl.shl_se.load_shl_se_team_players", return_value=[]), \
             patch("src.shl.shl_se._get_team_mapper", side_effect=Exception("Connection refused")):
            result = fetch_shl_se_team_players(20961, "Brynäs IF", tmp_path)

        assert result == []

    def test_skips_players_with_zero_jersey(self, tmp_path):
        """Players with jersey_number <= 0 should be skipped."""
        zero_jersey = ShlSePlayer(
            uuid="p0", first_name="No", last_name="Jersey",
            full_name="No Jersey", jersey_number=0,
            nationality="SE", position="Forwards", position_code="F",
            portrait_url="",
        )
        with patch("src.shl.shl_se.load_shl_se_team_players", return_value=[]), \
             patch("src.shl.shl_se._get_team_mapper", return_value=TeamMapper([SAMPLE_TEAM])), \
             patch("src.shl.shl_se.fetch_shl_se_roster", return_value=[SAMPLE_PLAYER, zero_jersey]), \
             patch("src.shl.shl_se.download_portrait", return_value=None), \
             patch("src.shl.shl_se.save_shl_se_player"):
            result = fetch_shl_se_team_players(20961, "Brynäs IF", tmp_path)

        assert len(result) == 1
        assert result[0]["full_name"] == "Christian Djoos"


# ---------------------------------------------------------------------------
# get_shl_se_player / get_shl_se_team_players (read-only from DB)
# ---------------------------------------------------------------------------

class TestGetShlSePlayer:
    def test_returns_data_when_cached(self, tmp_path):
        cached = {
            "data": {"full_name": "Christian Djoos", "jersey_number": 3},
            "portrait_path": "portraits/BIF_3.png",
            "fetched_at": "2026-01-01T00:00:00Z",
        }
        with patch("src.shl.shl_se.load_shl_se_player", return_value=cached):
            result = get_shl_se_player(20961, "Brynäs IF", 3, tmp_path)

        assert result == {"full_name": "Christian Djoos", "jersey_number": 3}

    def test_returns_none_when_not_cached(self, tmp_path):
        with patch("src.shl.shl_se.load_shl_se_player", return_value=None):
            result = get_shl_se_player(20961, "Brynäs IF", 3, tmp_path)

        assert result is None


class TestGetShlSeTeamPlayers:
    def test_returns_data_when_cached(self, tmp_path):
        rows = [
            {"data": {"full_name": "Player A"}, "fetched_at": "2026-01-01"},
        ]
        with patch("src.shl.shl_se.load_shl_se_team_players", return_value=rows):
            result = get_shl_se_team_players(20961, "Brynäs IF", tmp_path)

        assert result == [{"full_name": "Player A"}]

    def test_returns_none_when_not_cached(self, tmp_path):
        with patch("src.shl.shl_se.load_shl_se_team_players", return_value=[]):
            result = get_shl_se_team_players(20961, "Brynäs IF", tmp_path)

        assert result is None
