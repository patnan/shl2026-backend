import pytest

from src.shl.helpers.extraction import (
    ExtractGameError,
    ExtractGamesFromListingByDateError,
  ExtractScheduleGamesError,
    GameScrapeError,
    extract_game,
    extract_game_by_id,
    extract_game_urls_from_listing_html,
    extract_game_urls_from_listing_html_by_date,
    extract_games_from_listing,
    extract_games_from_listing_by_date,
    extract_games_from_listing_with_progress,
  extract_schedule_games,
  extract_schedule_games_from_listing_html,
)


def test_extract_games_from_listing_scrapes_each_game(monkeypatch):
  listing_url = "https://stats.swehockey.se/Tournaments/SHL"

  def fake_extract_schedule_games(url):
    assert url == listing_url
    return [
      {"date": "2025-09-13", "game_url": "https://stats.swehockey.se/Game/Events/1004840"},
      {"date": "2025-09-13", "game_url": "https://stats.swehockey.se/Game/Events/1004841"},
    ]

  def fake_extract_game(url):
    return {"url": url}

  monkeypatch.setattr("src.shl.helpers.extraction.extract_schedule_games", fake_extract_schedule_games)
  monkeypatch.setattr("src.shl.helpers.extraction.extract_game", fake_extract_game)

  results = extract_games_from_listing(listing_url)
  assert results == [
    {"url": "https://stats.swehockey.se/Game/Events/1004840"},
    {"url": "https://stats.swehockey.se/Game/Events/1004841"},
  ]


def test_extract_games_from_listing_raises_descriptive_error_on_game_failure(monkeypatch):
  listing_url = "https://stats.swehockey.se/Tournaments/SHL"
  bad_url = "https://stats.swehockey.se/Game/Events/1004841"

  def fake_extract_schedule_games(url):
    assert url == listing_url
    return [
      {"date": "2025-09-13", "game_url": "https://stats.swehockey.se/Game/Events/1004840"},
      {"date": "2025-09-13", "game_url": bad_url},
    ]

  def fake_extract_game(url):
    if url == bad_url:
      raise ValueError("missing top stats")
    return {"url": url}

  monkeypatch.setattr("src.shl.helpers.extraction.extract_schedule_games", fake_extract_schedule_games)
  monkeypatch.setattr("src.shl.helpers.extraction.extract_game", fake_extract_game)

  with pytest.raises(GameScrapeError, match="Failed to scrape game") as exc:
    extract_games_from_listing(listing_url)

  message = str(exc.value)
  assert bad_url in message
  assert listing_url in message
  assert "missing top stats" in message


def test_extract_games_from_listing_raises_when_no_event_links(monkeypatch):
  listing_url = "https://stats.swehockey.se/Tournaments/SHL"

  def fake_extract_schedule_games(url):
    assert url == listing_url
    return []

  monkeypatch.setattr("src.shl.helpers.extraction.extract_schedule_games", fake_extract_schedule_games)

  with pytest.raises(GameScrapeError, match="No game event links were found"):
    extract_games_from_listing(listing_url)


def test_extract_games_from_listing_progress_callback(monkeypatch):
  listing_url = "https://stats.swehockey.se/Tournaments/SHL"

  progress_events = []

  def fake_extract_schedule_games(url):
    assert url == listing_url
    return [
      {"date": "2025-09-13", "game_url": "https://stats.swehockey.se/Game/Events/1004840"},
      {"date": "2025-09-13", "game_url": "https://stats.swehockey.se/Game/Events/1004841"},
    ]

  def fake_extract_game(url):
    return {"url": url}

  def progress_callback(index, total, url):
    progress_events.append((index, total, url))

  monkeypatch.setattr("src.shl.helpers.extraction.extract_schedule_games", fake_extract_schedule_games)
  monkeypatch.setattr("src.shl.helpers.extraction.extract_game", fake_extract_game)

  results = extract_games_from_listing_with_progress(listing_url, progress_callback=progress_callback)

  assert len(results) == 2
  assert progress_events == [
    (1, 2, "https://stats.swehockey.se/Game/Events/1004840"),
    (2, 2, "https://stats.swehockey.se/Game/Events/1004841"),
  ]

def test_extract_game_entrypoint_orchestrates_pipeline(monkeypatch):
  called = {"fetch": False, "top": False, "actions": False}

  def fake_fetch_html(url):
    called["fetch"] = True
    assert url == "https://example.test/game/1"
    return "<html>dummy</html>"

  def fake_parse_top_stats(html):
    called["top"] = True
    assert html == "<html>dummy</html>"
    return {
      "game": {"home_team": "A", "away_team": "B"},
      "score": {"periods": ["1-0", "0-1", "1-0"]},
      "teams": {},
    }

  def fake_parse_actions(html, score_period_count=None):
    called["actions"] = True
    assert html == "<html>dummy</html>"
    assert score_period_count == 3
    return [{"game_time": "00:00"}]

  monkeypatch.setattr("src.shl.helpers.extraction.fetch_html", fake_fetch_html)
  monkeypatch.setattr("src.shl.helpers.extraction.parse_top_stats", fake_parse_top_stats)
  monkeypatch.setattr("src.shl.helpers.extraction.parse_actions", fake_parse_actions)

  result = extract_game("https://example.test/game/1")
  assert called == {"fetch": True, "top": True, "actions": True}
  assert result["actions"] == [{"game_time": "00:00"}]


def test_extract_game_by_id_builds_url_and_delegates(monkeypatch):
  captured = {"url": None}

  def fake_extract_game(url):
    captured["url"] = url
    return {"game": {"home_team": "A", "away_team": "B"}, "score": {"current": "0-0"}, "actions": []}

  monkeypatch.setattr("src.shl.helpers.extraction.extract_game", fake_extract_game)

  result = extract_game_by_id(1004357)
  assert captured["url"] == "https://stats.swehockey.se/Game/Events/1004357"
  assert result["score"]["current"] == "0-0"


def test_extract_game_by_id_raises_for_non_positive_value():
  with pytest.raises(ExtractGameError, match="positive integer"):
    extract_game_by_id(0)


def test_extract_game_urls_from_listing_html_collects_unique_event_links():
  html = """
<html><body>
  <table>
  <tr><td>Results</td><td><a href="/Game/Events/1004840">3-2</a></td></tr>
  <tr><td>Results</td><td><a href="https://stats.swehockey.se/Game/Events/1004841">1-3</a></td></tr>
  <tr><td>Results</td><td><a href="/Game/Events/1004840">duplicate</a></td></tr>
  <tr><td>Other</td><td><a href="/Game/LineUps/1004840">lineup</a></td></tr>
  </table>
</body></html>
"""
  urls = extract_game_urls_from_listing_html(html, base_url="https://stats.swehockey.se/Tournaments/1")
  assert urls == [
    "https://stats.swehockey.se/Game/Events/1004840",
    "https://stats.swehockey.se/Game/Events/1004841",
  ]


def test_extract_game_urls_from_listing_html_by_date_filters_specific_date():
  html = """
<html><body>
  <table>
    <tr>
      <td><span>2025-09-16</span></td>
      <td><a href="javascript:openonlinewindow('/Game/Events/1004308','')">2-1</a></td>
    </tr>
    <tr>
      <td><span>2025-09-16</span></td>
      <td><a href="/Game/Events/1004309">3-2</a></td>
    </tr>
    <tr>
      <td><span>2025-09-16</span></td>
      <td><a href="/Game/Events/1004309">duplicate</a></td>
    </tr>
    <tr>
      <td><span>2025-09-18</span></td>
      <td><a href="/Game/Events/1004310">other date</a></td>
    </tr>
  </table>
</body></html>
"""

  urls = extract_game_urls_from_listing_html_by_date(
    html,
    base_url="https://stats.swehockey.se/ScheduleAndResults/Schedule/18263",
    game_date="2025-09-16",
  )

  assert urls == [
    "https://stats.swehockey.se/Game/Events/1004308",
    "https://stats.swehockey.se/Game/Events/1004309",
  ]


def test_extract_game_urls_from_listing_html_by_date_handles_grouped_rows_without_repeated_date():
  html = """
<html><body>
  <table>
    <tr>
      <td><span>2025-09-16</span></td>
      <td>Brynäs IF - Luleå HF</td>
      <td><a href="/Game/Events/1004308">5-7</a></td>
    </tr>
    <tr>
      <td></td>
      <td>Färjestad BK - IF Malmö Redhawks</td>
      <td><a href="/Game/Events/1004309">6-2</a></td>
    </tr>
    <tr>
      <td></td>
      <td>Leksands IF - Örebro HK</td>
      <td><a href="/Game/Events/1004310">4-2</a></td>
    </tr>
    <tr>
      <td><span>2025-09-18</span></td>
      <td>Other date</td>
      <td><a href="/Game/Events/1004311">1-0</a></td>
    </tr>
  </table>
</body></html>
"""

  urls = extract_game_urls_from_listing_html_by_date(
    html,
    base_url="https://stats.swehockey.se/ScheduleAndResults/Schedule/18263",
    game_date="2025-09-16",
  )

  assert urls == [
    "https://stats.swehockey.se/Game/Events/1004308",
    "https://stats.swehockey.se/Game/Events/1004309",
    "https://stats.swehockey.se/Game/Events/1004310",
  ]


def test_extract_games_from_listing_by_date_scrapes_only_matching_games(monkeypatch):
  def fake_extract_schedule_games(url):
    assert url == "https://stats.swehockey.se/ScheduleAndResults/Schedule/18263"
    return [
      {"date": "2025-09-16", "game_url": "https://stats.swehockey.se/Game/Events/1004308"},
      {"date": "2025-09-16", "game_url": "https://stats.swehockey.se/Game/Events/1004309"},
      {"date": "2025-09-18", "game_url": "https://stats.swehockey.se/Game/Events/1004310"},
    ]

  def fake_extract_game(url):
    return {"game": {"url": url}}

  monkeypatch.setattr("src.shl.helpers.extraction.extract_schedule_games", fake_extract_schedule_games)
  monkeypatch.setattr("src.shl.helpers.extraction.extract_game", fake_extract_game)

  results = extract_games_from_listing_by_date(
    "https://stats.swehockey.se/ScheduleAndResults/Schedule/18263",
    "2025-09-16",
  )

  assert results == [
    {"game": {"url": "https://stats.swehockey.se/Game/Events/1004308"}},
    {"game": {"url": "https://stats.swehockey.se/Game/Events/1004309"}},
  ]


def test_extract_games_from_listing_by_date_returns_empty_for_missing_date(monkeypatch):
  def fake_extract_schedule_games(url):
    assert url == "https://stats.swehockey.se/ScheduleAndResults/Schedule/18263"
    return [{"date": "2025-09-18", "game_url": "https://stats.swehockey.se/Game/Events/1004310"}]

  monkeypatch.setattr("src.shl.helpers.extraction.extract_schedule_games", fake_extract_schedule_games)

  results = extract_games_from_listing_by_date(
    "https://stats.swehockey.se/ScheduleAndResults/Schedule/18263",
    "2025-09-16",
  )
  assert results == []


def test_extract_games_from_listing_by_date_raises_on_game_scrape_failure(monkeypatch):
  def fake_extract_schedule_games(url):
    assert url == "https://stats.swehockey.se/ScheduleAndResults/Schedule/18263"
    return [{"date": "2025-09-16", "game_url": "https://stats.swehockey.se/Game/Events/1004308"}]

  def fake_extract_game(url):
    raise RuntimeError("boom")

  monkeypatch.setattr("src.shl.helpers.extraction.extract_schedule_games", fake_extract_schedule_games)
  monkeypatch.setattr("src.shl.helpers.extraction.extract_game", fake_extract_game)

  with pytest.raises(ExtractGamesFromListingByDateError, match="Failed to scrape game"):
    extract_games_from_listing_by_date(
      "https://stats.swehockey.se/ScheduleAndResults/Schedule/18263",
      "2025-09-16",
    )


def test_extract_schedule_games_from_listing_html_parses_expected_fields():
  html = """
<html><body>
  <table>
    <tr><td colspan="8">Round 1</td></tr>
    <tr>
      <td>2025-09-13</td>
      <td>15:15</td>
      <td>Brynäs IF - Växjö Lakers HC</td>
      <td>4 - 7 (2-2, 2-3, 0-2)</td>
      <td>7909</td>
      <td>Monitor ERP Arena</td>
      <td><a href="/Game/Events/1004308">Match</a></td>
    </tr>
  </table>
</body></html>
"""

  games = extract_schedule_games_from_listing_html(
    html,
    base_url="https://stats.swehockey.se/ScheduleAndResults/Schedule/18263",
  )

  assert len(games) == 1
  assert games[0] == {
    "date": "2025-09-13",
    "time": "15:15",
    "game_result": "4 - 7 (2-2, 2-3, 0-2)",
    "spectators": 7909,
    "venue": "Monitor ERP Arena",
    "game_url": "https://stats.swehockey.se/Game/Events/1004308",
    "round": 1,
  }


def test_extract_schedule_games_from_listing_html_keeps_grouped_rows_without_repeated_date():
  html = """
<html><body>
  <table>
    <tr><td colspan="8">Round 3</td></tr>
    <tr>
      <td>2025-09-20</td>
      <td>15:15</td>
      <td>Team A - Team B</td>
      <td>2 - 1 (1-1, 1-0, 0-0)</td>
      <td>5000</td>
      <td>Arena A</td>
      <td><a href="/Game/Events/1005001">Match</a></td>
    </tr>
    <tr>
      <td></td>
      <td>18:00</td>
      <td>Team C - Team D</td>
      <td>3 - 2 (0-1, 2-1, 1-0)</td>
      <td>6200</td>
      <td>Arena B</td>
      <td><a href="/Game/Events/1005002">Match</a></td>
    </tr>
  </table>
</body></html>
"""

  games = extract_schedule_games_from_listing_html(
    html,
    base_url="https://stats.swehockey.se/ScheduleAndResults/Schedule/18263",
  )

  assert len(games) == 2
  assert games[0]["date"] == "2025-09-20"
  assert games[1]["date"] == "2025-09-20"
  assert games[1]["game_url"] == "https://stats.swehockey.se/Game/Events/1005002"
  assert games[1]["round"] == 3


def test_extract_schedule_games_from_listing_html_deduplicates_same_game_url():
  html = """
<html><body>
  <table>
    <tr><td colspan="8">Round 4</td></tr>
    <tr>
      <td>2025-09-22</td>
      <td>19:00</td>
      <td>Team A - Team B</td>
      <td>2 - 0 (1-0, 1-0, 0-0)</td>
      <td>5000</td>
      <td>Arena A</td>
      <td><a href="/Game/Events/1005100">Match</a></td>
    </tr>
    <tr>
      <td></td>
      <td></td>
      <td>Duplicate row with same game link</td>
      <td></td>
      <td></td>
      <td></td>
      <td><a href="/Game/Events/1005100">Match</a></td>
    </tr>
  </table>
</body></html>
"""

  games = extract_schedule_games_from_listing_html(
    html,
    base_url="https://stats.swehockey.se/ScheduleAndResults/Schedule/18263",
  )

  assert len(games) == 1
  assert games[0]["game_url"] == "https://stats.swehockey.se/Game/Events/1005100"


def test_extract_schedule_games_fetches_and_parses(monkeypatch):
  listing_url = "https://stats.swehockey.se/ScheduleAndResults/Schedule/18263"
  html = """
<html><body>
  <table>
    <tr><td colspan="8">Round 2</td></tr>
    <tr>
      <td>2025-09-18</td>
      <td>19:00</td>
      <td>Team A - Team B</td>
      <td>3 - 1 (1-0, 1-1, 1-0)</td>
      <td>6123</td>
      <td>Arena A</td>
      <td><a href="/Game/Events/1004310">Match</a></td>
    </tr>
  </table>
</body></html>
"""

  def fake_fetch_html(url):
    assert url == listing_url
    return html

  monkeypatch.setattr("src.shl.helpers.extraction.fetch_html", fake_fetch_html)

  games = extract_schedule_games(listing_url)

  assert games[0]["round"] == 2
  assert games[0]["game_url"] == "https://stats.swehockey.se/Game/Events/1004310"


def test_extract_schedule_games_wraps_fetch_errors(monkeypatch):
  def fake_fetch_html(url):
    raise RuntimeError("network down")

  monkeypatch.setattr("src.shl.helpers.extraction.fetch_html", fake_fetch_html)

  with pytest.raises(ExtractScheduleGamesError, match="network down"):
    extract_schedule_games("https://stats.swehockey.se/ScheduleAndResults/Schedule/18263")


def test_extract_games_from_listing_uses_schedule_games_json(monkeypatch):
  listing_url = "https://stats.swehockey.se/ScheduleAndResults/Schedule/18263"

  def fake_extract_schedule_games(url):
    assert url == listing_url
    return [
      {
        "date": "2025-09-13",
        "time": "15:15",
        "game_result": "4 - 7 (2-2, 2-3, 0-2)",
        "spectators": 7909,
        "venue": "Monitor ERP Arena",
        "game_url": "https://stats.swehockey.se/Game/Events/1004308",
        "round": 1,
      },
      {
        "date": "2025-09-13",
        "time": "18:00",
        "game_result": "3 - 2 (1-1, 1-1, 1-0)",
        "spectators": 7000,
        "venue": "Arena B",
        "game_url": "https://stats.swehockey.se/Game/Events/1004309",
        "round": 1,
      },
    ]

  def fake_extract_game(url):
    return {"url": url}

  monkeypatch.setattr("src.shl.helpers.extraction.extract_schedule_games", fake_extract_schedule_games)
  monkeypatch.setattr("src.shl.helpers.extraction.extract_game", fake_extract_game)

  results = extract_games_from_listing(listing_url)

  assert results == [
    {"url": "https://stats.swehockey.se/Game/Events/1004308"},
    {"url": "https://stats.swehockey.se/Game/Events/1004309"},
  ]


