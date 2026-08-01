import os
from pathlib import Path

import pytest

from src.shl.api import (
    fetch_game,
    fetch_schedule,
    fetch_table,
    get_all_played_games,
    get_games_for_date,
    get_schedule,
    get_standings,
)
from src.shl.helpers.extraction import fetch_html
from src.shl.store import load_game, load_standings
from tests.helpers import compare_standings, parse_overview_standings_html


SEASON_ID = 18263

SEASON_SCHEDULE_URL = f"https://stats.swehockey.se/ScheduleAndResults/Schedule/{SEASON_ID}"

SEASON_OVERVIEW_URL = f"https://stats.swehockey.se/ScheduleAndResults/Overview/{SEASON_ID}"

GAME_ID = 1004357

ROUND_DATE = "2025-09-16"


@pytest.fixture(autouse=True)
def _print_integration_test_name(request):
    print(f"\n=== {request.node.name} ===")


@pytest.fixture(scope="module")
def integration_db_dir():
    configured = os.environ.get("SHL_INTEGRATION_DB_DIR")
    if configured:
        db_dir = Path(configured)
    else:
        db_dir = Path("cache") / "integration_db"

    db_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nintegration_db_dir: {db_dir}")
    return db_dir


@pytest.fixture(scope="module")
def persisted_schedule(integration_db_dir):
    # This fixture is intentionally the first persistence step for schedule data.
    return fetch_schedule(SEASON_ID, integration_db_dir)


@pytest.fixture(scope="module")
def persisted_played_games(persisted_schedule, integration_db_dir):
    played_entries = get_all_played_games(SEASON_ID, integration_db_dir)
    game_ids = []
    total = len(played_entries)
    print(f"\npersisted_played_games: ensuring {total} played games exist in DB")
    for index, entry in enumerate(played_entries, start=1):
        game_id = int(entry.game_url.rstrip("/").split("/")[-1])
        print(
            f"\rpersisted_played_games[{index}/{total}]: fetch_game({game_id})",
            end="",
            flush=True,
        )
        fetch_game(game_id, integration_db_dir)
        game_ids.append(game_id)
    print("\npersisted_played_games: fetch phase complete", flush=True)
    return game_ids

@pytest.mark.integration
def test_fetch_game_from_network_and_store_in_db(integration_db_dir):
    result = fetch_game(GAME_ID, integration_db_dir)

    assert result.game.home_team
    assert result.game.away_team
    assert result.score.current
    assert isinstance(result.actions, list)

    persisted = load_game(integration_db_dir, GAME_ID)
    assert persisted is not None
    assert persisted.game.home_team == result.game.home_team
    assert persisted.game.away_team == result.game.away_team


@pytest.mark.integration
def test_fetch_schedule_from_network_and_store_in_db(persisted_schedule, integration_db_dir):
    assert len(persisted_schedule) > 0

    db_file = integration_db_dir / "cache.db"
    assert db_file.exists(), "Expected cache.db to be created after fetch_schedule"


@pytest.mark.integration
def test_fetch_table_from_network_and_store_in_db(integration_db_dir):
    standings = fetch_table(SEASON_ID, integration_db_dir)

    assert len(standings) > 0
    assert standings[0].team

    persisted = load_standings(integration_db_dir, SEASON_ID)
    assert persisted is not None
    assert len(persisted) == len(standings)


@pytest.mark.integration
def test_get_schedule_reads_data_from_db_after_fetch(persisted_schedule, integration_db_dir):
    loaded = get_schedule(SEASON_ID, integration_db_dir)

    assert loaded is not None
    assert len(loaded) == len(persisted_schedule)
    assert loaded[0].game_url == persisted_schedule[0].game_url
    assert loaded[0].date == persisted_schedule[0].date


@pytest.mark.integration
def test_get_games_for_date_uses_persisted_schedule(persisted_schedule, integration_db_dir):
    games = get_games_for_date(SEASON_ID, ROUND_DATE, integration_db_dir)

    assert isinstance(games, list)
    assert len(games) > 0
    assert all(entry.date.startswith(ROUND_DATE) for entry in games)


@pytest.mark.integration
def test_get_all_played_games_uses_persisted_schedule(persisted_schedule, integration_db_dir):
    played = get_all_played_games(SEASON_ID, integration_db_dir)

    assert isinstance(played, list)
    assert len(played) > 0
    previous_line_length = 0
    for index, entry in enumerate(played, start=1):
        game_id = entry.game_url.rstrip("/").split("/")[-1] if entry.game_url else "unknown"
        line = f"played[{index}/{len(played)}]: game_id={game_id} url={entry.game_url} result={entry.game_result}"
        clear_tail = " " * max(0, previous_line_length - len(line))
        print(
            f"\r{line}{clear_tail}",
            end="",
            flush=True,
        )
        previous_line_length = len(line)
        assert entry.game_result
    print()


@pytest.mark.integration
def test_calculated_standings_match_overview(persisted_played_games, integration_db_dir):
    print("test_calculated_standings_match_overview: calculating standings from persisted DB games")
    overview_html = fetch_html(SEASON_OVERVIEW_URL)

    calculated = get_standings(SEASON_ID, integration_db_dir)
    overview = parse_overview_standings_html(overview_html)
    mismatches = compare_standings(calculated, overview)

    assert mismatches == [], f"Standings mismatches found:\n" + "\n".join(str(m) for m in mismatches)
