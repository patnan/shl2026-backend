import json
import pytest
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
    from src.shl.extraction import ExtractGameError
    monkeypatch.setattr("src.cli.extract_game_by_id", lambda game_id: (_ for _ in ()).throw(ExtractGameError("positive integer")))

    with patch("sys.argv", ["cli", "scrape", "--game-id", "1004357"]):
        with pytest.raises(ExtractGameError, match="positive integer"):
            main()

