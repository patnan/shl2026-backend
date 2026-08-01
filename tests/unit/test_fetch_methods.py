import pytest

from src.shl.game import FetchGameError, fetch_game
from src.shl.models import Game, GameInfo, ScheduleEntry, Score, StandingsRow
from src.shl.schedule import FetchScheduleError, fetch_schedule
from src.shl.standings import FetchTableError, fetch_table


def make_game(date_time: str) -> Game:
    return Game(
        game=GameInfo(
            home_team="A",
            away_team="B",
            is_overtime=False,
            is_shootout=False,
            date_time=date_time,
            league=None,
            arena=None,
        ),
        score=Score(current="1-0", home_score=1, away_score=0, periods=["1-0", "0-0", "0-0"], current_period=3, state="Final Score"),
        teams={},
        actions=[],
    )


def make_schedule_entry(game_id: int) -> ScheduleEntry:
    return ScheduleEntry(
        date="2025-09-16",
        time="19:00",
        game_result="2-1",
        spectators="1234",
        venue="Arena",
        game_url=f"https://stats.swehockey.se/Game/Events/{game_id}",
        round="1",
    )


def make_standings_row() -> StandingsRow:
    return StandingsRow(
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


def test_fetch_game_uses_cached_past_game_by_default(monkeypatch, tmp_path):
    cached = make_game("2000-01-01 19:00")

    monkeypatch.setattr("src.shl.game.load_game", lambda db_dir, game_id: cached)
    monkeypatch.setattr("src.shl.game.extract_game_by_id", lambda game_id: pytest.fail("extract_game_by_id should not be called"))
    monkeypatch.setattr("src.shl.game.save_game", lambda db_dir, game_id, game: pytest.fail("save_game should not be called"))

    result = fetch_game(1004357, tmp_path)
    assert result is cached


def test_fetch_game_force_reparse_bypasses_cache(monkeypatch, tmp_path):
    fresh = make_game("2000-01-01 19:00")
    calls = {"extract": 0, "save": 0}

    monkeypatch.setattr("src.shl.game.load_game", lambda db_dir, game_id: make_game("2000-01-01 19:00"))

    def fake_extract(game_id):
        calls["extract"] += 1
        return fresh

    def fake_save(db_dir, game_id, game):
        calls["save"] += 1

    monkeypatch.setattr("src.shl.game.extract_game_by_id", fake_extract)
    monkeypatch.setattr("src.shl.game.save_game", fake_save)

    result = fetch_game(1004357, tmp_path, force_reparse=True)
    assert result is fresh
    assert calls == {"extract": 1, "save": 1}


def test_fetch_game_cache_miss_fetches_and_saves(monkeypatch, tmp_path):
    fresh = make_game("2000-01-01 19:00")
    calls = {"extract": 0, "save": 0}

    monkeypatch.setattr("src.shl.game.load_game", lambda db_dir, game_id: None)

    def fake_extract(game_id):
        calls["extract"] += 1
        return fresh

    def fake_save(db_dir, game_id, game):
        calls["save"] += 1

    monkeypatch.setattr("src.shl.game.extract_game_by_id", fake_extract)
    monkeypatch.setattr("src.shl.game.save_game", fake_save)

    result = fetch_game(1004357, tmp_path)
    assert result is fresh
    assert calls == {"extract": 1, "save": 1}


def test_fetch_game_cached_today_reparses(monkeypatch, tmp_path):
    # Date equal to today is not considered a past game, so fetch should run.
    today_str = __import__("datetime").date.today().isoformat() + " 19:00"
    fresh = make_game(today_str)
    calls = {"extract": 0, "save": 0}

    monkeypatch.setattr("src.shl.game.load_game", lambda db_dir, game_id: make_game(today_str))

    def fake_extract(game_id):
        calls["extract"] += 1
        return fresh

    def fake_save(db_dir, game_id, game):
        calls["save"] += 1

    monkeypatch.setattr("src.shl.game.extract_game_by_id", fake_extract)
    monkeypatch.setattr("src.shl.game.save_game", fake_save)

    result = fetch_game(1004357, tmp_path)
    assert result is fresh
    assert calls == {"extract": 1, "save": 1}


def test_fetch_game_cached_invalid_date_reparses(monkeypatch, tmp_path):
    fresh = make_game("invalid-date")
    calls = {"extract": 0, "save": 0}

    monkeypatch.setattr("src.shl.game.load_game", lambda db_dir, game_id: make_game("invalid-date"))

    def fake_extract(game_id):
        calls["extract"] += 1
        return fresh

    def fake_save(db_dir, game_id, game):
        calls["save"] += 1

    monkeypatch.setattr("src.shl.game.extract_game_by_id", fake_extract)
    monkeypatch.setattr("src.shl.game.save_game", fake_save)

    result = fetch_game(1004357, tmp_path)
    assert result is fresh
    assert calls == {"extract": 1, "save": 1}


def test_fetch_game_wraps_underlying_error(monkeypatch, tmp_path):
    monkeypatch.setattr("src.shl.game.load_game", lambda db_dir, game_id: None)
    monkeypatch.setattr("src.shl.game.extract_game_by_id", lambda game_id: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(FetchGameError, match="fetch_game failed"):
        fetch_game(1004357, tmp_path)


def test_fetch_schedule_uses_cached_data_by_default(monkeypatch, tmp_path):
    cached = [make_schedule_entry(1004308)]

    monkeypatch.setattr("src.shl.schedule.load_schedule", lambda db_dir, season_id: cached)
    monkeypatch.setattr("src.shl.schedule.extract_schedule_games", lambda url: pytest.fail("extract_schedule_games should not be called"))
    monkeypatch.setattr("src.shl.schedule.save_schedule", lambda db_dir, season_id, schedule: pytest.fail("save_schedule should not be called"))

    result = fetch_schedule(18263, tmp_path)
    assert result is cached


def test_fetch_schedule_force_reparse_bypasses_cache(monkeypatch, tmp_path):
    fresh = [make_schedule_entry(1004309)]
    calls = {"extract": 0, "save": 0}

    monkeypatch.setattr("src.shl.schedule.load_schedule", lambda db_dir, season_id: [make_schedule_entry(1004308)])

    def fake_extract(url):
        calls["extract"] += 1
        return fresh

    def fake_save(db_dir, season_id, schedule):
        calls["save"] += 1

    monkeypatch.setattr("src.shl.schedule.extract_schedule_games", fake_extract)
    monkeypatch.setattr("src.shl.schedule.save_schedule", fake_save)

    result = fetch_schedule(18263, tmp_path, force_reparse=True)
    assert result is fresh
    assert calls == {"extract": 1, "save": 1}


def test_fetch_schedule_cache_miss_fetches_and_saves(monkeypatch, tmp_path):
    fresh = [make_schedule_entry(1004310)]
    calls = {"extract": 0, "save": 0}

    monkeypatch.setattr("src.shl.schedule.load_schedule", lambda db_dir, season_id: None)

    def fake_extract(url):
        calls["extract"] += 1
        return fresh

    def fake_save(db_dir, season_id, schedule):
        calls["save"] += 1

    monkeypatch.setattr("src.shl.schedule.extract_schedule_games", fake_extract)
    monkeypatch.setattr("src.shl.schedule.save_schedule", fake_save)

    result = fetch_schedule(18263, tmp_path)
    assert result is fresh
    assert calls == {"extract": 1, "save": 1}


def test_fetch_schedule_wraps_underlying_error(monkeypatch, tmp_path):
    monkeypatch.setattr("src.shl.schedule.load_schedule", lambda db_dir, season_id: None)
    monkeypatch.setattr("src.shl.schedule.extract_schedule_games", lambda url: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(FetchScheduleError, match="fetch_schedule failed"):
        fetch_schedule(18263, tmp_path)


def test_fetch_table_uses_cached_data_by_default(monkeypatch, tmp_path):
    cached = [make_standings_row()]

    monkeypatch.setattr("src.shl.standings.load_standings", lambda db_dir, season_id: cached)
    monkeypatch.setattr("src.shl.standings.fetch_html", lambda url: pytest.fail("fetch_html should not be called"))
    monkeypatch.setattr("src.shl.standings.parse_overview_standings_html", lambda html: pytest.fail("parse_overview_standings_html should not be called"))
    monkeypatch.setattr("src.shl.standings.save_standings", lambda db_dir, season_id, standings: pytest.fail("save_standings should not be called"))

    result = fetch_table(18263, tmp_path)
    assert result is cached


def test_fetch_table_force_reparse_bypasses_cache(monkeypatch, tmp_path):
    fresh = [make_standings_row()]
    calls = {"fetch_html": 0, "parse": 0, "save": 0}

    monkeypatch.setattr("src.shl.standings.load_standings", lambda db_dir, season_id: [make_standings_row()])

    def fake_fetch_html(url):
        calls["fetch_html"] += 1
        return "<html></html>"

    def fake_parse(html):
        calls["parse"] += 1
        return fresh

    def fake_save(db_dir, season_id, standings):
        calls["save"] += 1

    monkeypatch.setattr("src.shl.standings.fetch_html", fake_fetch_html)
    monkeypatch.setattr("src.shl.standings.parse_overview_standings_html", fake_parse)
    monkeypatch.setattr("src.shl.standings.save_standings", fake_save)

    result = fetch_table(18263, tmp_path, force_reparse=True)
    assert result is fresh
    assert calls == {"fetch_html": 1, "parse": 1, "save": 1}


def test_fetch_table_cache_miss_fetches_and_saves(monkeypatch, tmp_path):
    fresh = [make_standings_row()]
    calls = {"fetch_html": 0, "parse": 0, "save": 0}

    monkeypatch.setattr("src.shl.standings.load_standings", lambda db_dir, season_id: None)

    def fake_fetch_html(url):
        calls["fetch_html"] += 1
        return "<html></html>"

    def fake_parse(html):
        calls["parse"] += 1
        return fresh

    def fake_save(db_dir, season_id, standings):
        calls["save"] += 1

    monkeypatch.setattr("src.shl.standings.fetch_html", fake_fetch_html)
    monkeypatch.setattr("src.shl.standings.parse_overview_standings_html", fake_parse)
    monkeypatch.setattr("src.shl.standings.save_standings", fake_save)

    result = fetch_table(18263, tmp_path)
    assert result is fresh
    assert calls == {"fetch_html": 1, "parse": 1, "save": 1}


def test_fetch_table_wraps_underlying_error(monkeypatch, tmp_path):
    monkeypatch.setattr("src.shl.standings.load_standings", lambda db_dir, season_id: None)
    monkeypatch.setattr("src.shl.standings.fetch_html", lambda url: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(FetchTableError, match="fetch_table failed"):
        fetch_table(18263, tmp_path)
