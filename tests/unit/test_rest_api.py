import pytest

pytest.importorskip("fastapi")
pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient

from src.shl.models import Game, ScheduleEntry, StandingsRow
from src.shl.rest_api import create_app


def test_root_endpoint_lists_endpoints(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "SHL Data API"
    assert body["version"] == "0.1.0"
    assert isinstance(body["endpoints"], list)
    assert len(body["endpoints"]) > 0
    # Each entry has path, method, description
    for ep in body["endpoints"]:
        assert "path" in ep
        assert "method" in ep
        assert "description" in ep


def test_health_endpoint(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_schedule_endpoint_returns_404_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("src.shl.routers.schedule.get_schedule", lambda season_id, cache_dir: None)
    client = TestClient(create_app(tmp_path))

    response = client.get("/seasons/18263/schedule")
    assert response.status_code == 404
    assert "No schedule stored" in response.json()["detail"]


def test_schedule_endpoint_returns_data(monkeypatch, tmp_path):
    schedule = [
        ScheduleEntry(
                    date="2025-09-16",
                    time="19:00",
                    home_team="Team A",
                    away_team="Team B",
                    game_result="2-1",
                    periods="",
                    spectators="5000",
                    venue="Arena",
                    game_url="https://stats.swehockey.se/Game/Events/1004308",
                    round="1",
                )
    ]
    monkeypatch.setattr("src.shl.routers.schedule.get_schedule", lambda season_id, cache_dir: schedule)
    monkeypatch.setattr("src.shl.routers.schedule.get_schedule_fetched_at", lambda cache_dir, season_id: "2026-08-01T10:00:00")
    client = TestClient(create_app(tmp_path))

    response = client.get("/seasons/18263/schedule")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["date"] == "2025-09-16"
    assert payload["meta"]["season_id"] == "18263"
    assert payload["meta"]["source_fetched_at"] == "2026-08-01T10:00:00"


def test_games_by_date_endpoint_uses_date_query(monkeypatch, tmp_path):
    captured = {}

    def fake_get_games_for_date(season_id, game_date, cache_dir):
        captured["season_id"] = season_id
        captured["date"] = game_date
        return []

    monkeypatch.setattr("src.shl.routers.schedule.get_games_for_date", fake_get_games_for_date)
    monkeypatch.setattr("src.shl.routers.schedule.get_schedule_fetched_at", lambda cache_dir, season_id: "2026-08-01T10:00:00")
    client = TestClient(create_app(tmp_path))

    response = client.get("/seasons/18263/games", params={"date": "2025-09-16"})
    assert response.status_code == 200
    assert captured == {"season_id": 18263, "date": "2025-09-16"}
    payload = response.json()
    assert payload["meta"]["source_schedule_fetched_at"] == "2026-08-01T10:00:00"


def test_games_endpoint_returns_all_games_without_date(monkeypatch, tmp_path):
    schedule = [
        ScheduleEntry(
            date="2025-09-16", time="19:00", home_team="Team A", away_team="Team B",
            game_result="2-1", periods="", spectators="", venue="Arena",
            game_url="", round="1",
        ),
        ScheduleEntry(
            date="2025-09-17", time="18:00", home_team="Team C", away_team="Team D",
            game_result="", periods="", spectators="", venue="Arena 2",
            game_url="", round="2",
        ),
    ]
    monkeypatch.setattr("src.shl.routers.schedule.get_schedule", lambda season_id, cache_dir: schedule)
    monkeypatch.setattr("src.shl.routers.schedule.get_schedule_fetched_at", lambda cache_dir, season_id: "2026-08-01T10:00:00")
    client = TestClient(create_app(tmp_path))

    response = client.get("/seasons/18263/games")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["data"]) == 2
    assert payload["meta"]["count"] == 2
    assert payload["meta"]["source_schedule_fetched_at"] == "2026-08-01T10:00:00"


def test_games_endpoint_returns_404_when_not_fetched(monkeypatch, tmp_path):
    monkeypatch.setattr("src.shl.routers.schedule.get_schedule", lambda season_id, cache_dir: None)
    monkeypatch.setattr("src.shl.routers.schedule.get_schedule_fetched_at", lambda cache_dir, season_id: None)
    client = TestClient(create_app(tmp_path))

    response = client.get("/seasons/18263/games")
    assert response.status_code == 404
    assert "not yet fetched" in response.json()["error"]


def test_played_games_endpoint_returns_list(monkeypatch, tmp_path):
    entries = [
        ScheduleEntry(
                    date="2025-09-16",
                    time="19:00",
                    home_team="Team A",
                    away_team="Team B",
                    game_result="2-1",
                    periods="",
                    spectators="5000",
                    venue="Arena",
                    game_url="https://stats.swehockey.se/Game/Events/1004308",
                    round="1",
                )
    ]
    monkeypatch.setattr("src.shl.routers.schedule.get_all_played_games", lambda season_id, cache_dir: entries)
    monkeypatch.setattr("src.shl.routers.schedule.get_schedule_fetched_at", lambda cache_dir, season_id: "2026-08-01T10:00:00")
    client = TestClient(create_app(tmp_path))

    response = client.get("/seasons/18263/games/played")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["data"]) == 1
    assert payload["meta"]["source_schedule_fetched_at"] == "2026-08-01T10:00:00"


def test_standings_endpoint_returns_data(monkeypatch, tmp_path):
    rows = [
        StandingsRow(
            rank=1,
            team="A",
            games_played=1,
            w=1,
            t=0,
            l=0,
            goals_for=2,
            goals_against=1,
            goal_difference=1,
            tp=3,
            otw=0,
            otl=0,
            gwsw=0,
            gwsl=0,
        )
    ]
    monkeypatch.setattr("src.shl.routers.standings.get_standings", lambda season_id, cache_dir: rows)
    monkeypatch.setattr("src.shl.routers.standings.get_all_played_games", lambda season_id, cache_dir: [
        ScheduleEntry(
                    date="2025-09-16",
                    time="19:00",
                    home_team="Team A",
                    away_team="Team B",
                    game_result="2-1",
                    periods="",
                    spectators="5000",
                    venue="Arena",
                    game_url="https://stats.swehockey.se/Game/Events/1004308",
                    round="1",
                )
    ])
    monkeypatch.setattr("src.shl.routers.standings.get_games_freshness", lambda cache_dir, game_ids: {
        "requested_game_count": 1,
        "cached_game_count": 1,
        "latest_fetched_at": "2026-08-01T10:10:00",
        "oldest_fetched_at": "2026-08-01T10:10:00",
    })
    monkeypatch.setattr("src.shl.routers.standings.get_schedule_fetched_at", lambda cache_dir, season_id: "2026-08-01T10:00:00")
    client = TestClient(create_app(tmp_path))

    response = client.get("/seasons/18263/standings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["team"] == "A"
    assert payload["meta"]["season_id"] == "18263"
    assert payload["meta"]["source_schedule_fetched_at"] == "2026-08-01T10:00:00"
    assert payload["meta"]["source_games_latest_fetched_at"] == "2026-08-01T10:10:00"
    assert payload["meta"]["source_games_cached_count"] == 1
    assert payload["meta"]["source_games_requested_count"] == 1


def test_games_by_date_requires_valid_date(tmp_path):
    client = TestClient(create_app(tmp_path))

    response = client.get("/seasons/18263/games", params={"date": "not-a-date"})
    assert response.status_code == 422


def test_game_details_returns_404_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("src.shl.game.extract_game_by_id", lambda game_id: (_ for _ in ()).throw(RuntimeError("not found")))
    client = TestClient(create_app(tmp_path))

    response = client.get("/games/1004308")
    assert response.status_code == 404
    assert "Game not found" in response.json()["detail"]


def test_game_details_returns_fresh_game(monkeypatch, tmp_path):
    game = Game.from_dict(
        {
            "game": {
                "home_team": "A",
                "away_team": "B",
                "is_overtime": False,
                "is_shootout": False,
                "date_time": "2025-09-16T19:00:00",
                "league": "SHL",
                "arena": "Arena",
            },
            "score": {
                "current": "2 - 1",
                "home_score": 2,
                "away_score": 1,
                "periods": ["1-0", "1-1", "0-0"],
                "current_period": 3,
                "state": "Final",
            },
            "teams": {
                "home": {
                    "shots": {"total": 20, "by_period": [6, 8, 6], "percentage": "10.0"},
                    "saves": {"total": 17, "by_period": [5, 6, 6], "percentage": "94.4"},
                    "pim": {"total": 4, "by_period": [2, 0, 2]},
                    "pp": {"percentage": "0.0", "time": "04:00"},
                },
                "away": {
                    "shots": {"total": 18, "by_period": [5, 7, 6], "percentage": "5.6"},
                    "saves": {"total": 18, "by_period": [5, 8, 5], "percentage": "90.0"},
                    "pim": {"total": 6, "by_period": [2, 2, 2]},
                    "pp": {"percentage": "0.0", "time": "06:00"},
                },
            },
            "actions": [],
        }
    )
    monkeypatch.setattr("src.shl.game.extract_game_by_id", lambda game_id: game)
    monkeypatch.setattr("src.shl.routers.games.get_game_fetched_at", lambda cache_dir, game_id: "2026-08-01T10:10:00")
    client = TestClient(create_app(tmp_path))

    response = client.get("/games/1004308")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["game"]["home_team"] == "A"
    assert payload["data"]["score"]["current"] == "2 - 1"
    assert payload["meta"]["game_id"] == "1004308"
    assert payload["meta"]["source_fetched_at"] == "2026-08-01T10:10:00"


