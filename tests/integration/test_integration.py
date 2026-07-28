import pytest

from src.shl.api import extract_game_by_id, extract_games_from_listing, extract_games_from_listing_with_progress


SEASON_SCHEDULE_URL = "https://stats.swehockey.se/ScheduleAndResults/Schedule/18263"

GAME_ID = 1004357

@pytest.mark.integration
def test_scrape_game_id_real_network():
    result = extract_game_by_id(GAME_ID)

    assert result["game"]["home_team"]
    assert result["game"]["away_team"]
    assert result["score"]["current"]
    assert isinstance(result["actions"], list)


@pytest.mark.integration
def test_extract_all_games_from_season_18263():
    def on_progress(index, total, url):
        print(f"\r[{index}/{total}] {url}", end="", flush=True)

    games = extract_games_from_listing_with_progress(SEASON_SCHEDULE_URL, progress_callback=on_progress)
    print()

    assert len(games) > 0

    for i, game in enumerate(games):
        assert "game" in game, f"game {i} missing 'game' key"
        assert "score" in game, f"game {i} missing 'score' key"
        assert "actions" in game, f"game {i} missing 'actions' key"

        g = game["game"]
        assert g.get("home_team"), f"game {i} missing home_team"
        assert g.get("away_team"), f"game {i} missing away_team"

        s = game["score"]
        assert s.get("current"), f"game {i} missing score current"
        assert isinstance(s.get("home_score"), int), f"game {i} home_score is not int"
        assert isinstance(s.get("away_score"), int), f"game {i} away_score is not int"
        assert isinstance(s.get("periods"), list), f"game {i} periods is not list"
        assert len(s["periods"]) >= 3, f"game {i} has fewer than 3 periods"

        assert isinstance(game["actions"], list), f"game {i} actions is not list"
