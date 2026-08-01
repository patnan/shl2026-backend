import json
import pytest
from pathlib import Path
from unittest.mock import patch

from src.cli import main


FAKE_GAME = {
    "game": {"home_team": "Brynäs IF", "away_team": "Luleå HF", "is_overtime": False, "is_shootout": False},
    "score": {"current": "3-2", "home_score": 3, "away_score": 2, "periods": ["1-0", "1-1", "1-1"], "current_period": 3, "state": "Final Score"},
    "actions": [],
}


def test_scrape_game_id_prints_json(capsys, monkeypatch):
    monkeypatch.setattr("src.cli.extract_game_by_id", lambda game_id: FAKE_GAME)

    with patch("sys.argv", ["cli", "scrape", "--game-id", "1004357"]):
        main()

    out = json.loads(capsys.readouterr().out)
    assert out["game"]["home_team"] == "Brynäs IF"
    assert out["score"]["current"] == "3-2"


def test_scrape_game_id_raises_for_invalid_id(monkeypatch):
    from src.shl.helpers.extraction import ExtractGameError
    monkeypatch.setattr("src.cli.extract_game_by_id", lambda game_id: (_ for _ in ()).throw(ExtractGameError("positive integer")))

    with patch("sys.argv", ["cli", "scrape", "--game-id", "1004357"]):
        with pytest.raises(ExtractGameError, match="positive integer"):
            main()


def test_cmd_compare_prints_result(tmp_path, capsys):
    prev = tmp_path / "prev.json"
    curr = tmp_path / "curr.json"
    prev.write_text(json.dumps({"game": {"home_team": "A", "away_team": "B"}, "score": {"current": "0-0"}}), encoding="utf-8")
    curr.write_text(json.dumps({"game": {"home_team": "A", "away_team": "B"}, "score": {"current": "1-0"}}), encoding="utf-8")

    with patch("sys.argv", ["cli", "compare", str(prev), str(curr)]):
        main()

    result = json.loads(capsys.readouterr().out)
    assert result["scored"] is True
    assert result["teams_scored"][0]["team"] == "A"


def test_cmd_poller_seed_prints_result(capsys, monkeypatch):
    captured = {}

    def fake_seed(cache_dir, season_id, include_games, force_reparse_schedule):
        captured["season_id"] = season_id
        captured["include_games"] = include_games
        captured["force_reparse_schedule"] = force_reparse_schedule
        return {"season_id": season_id, "total_targets": 4}

    monkeypatch.setattr("src.cli.seed_season_targets", fake_seed)

    with patch("sys.argv", ["cli", "poller-seed", "18263", "--force-reparse-schedule"]):
        main()

    out = json.loads(capsys.readouterr().out)
    assert out["season_id"] == 18263
    assert out["total_targets"] == 4
    assert captured == {
        "season_id": 18263,
        "include_games": True,
        "force_reparse_schedule": True,
    }


def test_cmd_poller_run_prints_result(capsys, monkeypatch):
    captured = {}

    def fake_run(cache_dir, tick_interval_seconds, max_ticks):
        captured["tick_interval_seconds"] = tick_interval_seconds
        captured["max_ticks"] = max_ticks
        return {"ticks": 2, "ok_results": 1, "error_results": 0}

    monkeypatch.setattr("src.cli.run_poller_worker", fake_run)

    with patch("sys.argv", ["cli", "poller-run", "--tick-interval", "0.25", "--max-ticks", "2"]):
        main()

    out = json.loads(capsys.readouterr().out)
    assert out == {"ticks": 2, "ok_results": 1, "error_results": 0}
    assert captured == {"tick_interval_seconds": 0.25, "max_ticks": 2}

