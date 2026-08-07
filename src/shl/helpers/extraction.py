import dataclasses
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.shl.models import Game, ScheduleEntry
from .parsing import parse_actions, parse_top_stats


class GameScrapeError(RuntimeError):
    pass


class FetchHtmlError(GameScrapeError):
    pass


class ExtractGameUrlsFromListingHtmlError(GameScrapeError):
    pass


class ExtractGameError(GameScrapeError):
    pass


class ExtractGamesFromListingError(GameScrapeError):
    pass


class ExtractGamesFromListingWithProgressError(GameScrapeError):
    pass


class ExtractGameUrlsFromListingHtmlByDateError(GameScrapeError):
    pass


class ExtractGamesFromListingByDateError(GameScrapeError):
    pass


class ExtractScheduleGamesFromListingHtmlError(GameScrapeError):
    pass


class ExtractScheduleGamesError(GameScrapeError):
    pass


class ExtractLiveGamesError(GameScrapeError):
    pass



def fetch_html(url: str, timeout: int = 20) -> str:
    try:
        candidate_urls = [url]
        if "/OverviewAndResults/Overview/" in url:
            candidate_urls.append(url.replace("/OverviewAndResults/Overview/", "/ScheduleAndResults/Overview/", 1))

        last_error: Optional[Exception] = None

        for candidate_index, candidate_url in enumerate(candidate_urls):
            for attempt in range(1, 4):
                try:
                    response = requests.get(candidate_url, timeout=timeout)
                    response.raise_for_status()
                    response.encoding = "utf-8"
                    return response.text
                except requests.exceptions.HTTPError as exc:
                    last_error = exc
                    status_code = exc.response.status_code if exc.response is not None else None
                    if status_code in {429} or (status_code is not None and status_code >= 500):
                        if attempt < 3:
                            time.sleep(0.4 * attempt)
                            continue
                    if status_code == 404 and candidate_index < len(candidate_urls) - 1:
                        break
                    raise
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                    last_error = exc
                    if attempt < 3:
                        time.sleep(0.4 * attempt)
                        continue
                    raise

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"No fetch candidates available for URL: {url}")
    except FetchHtmlError:
        raise
    except Exception as exc:
        raise FetchHtmlError(f"fetch_html failed for '{url}': {exc}") from exc



def extract_game_urls_from_listing_html(html: str, base_url: str) -> List[str]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        urls: List[str] = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            match = re.search(r"/Game/Events/\d+", href)
            if not match:
                continue

            canonical = urljoin(base_url, match.group(0))
            if canonical in seen:
                continue

            seen.add(canonical)
            urls.append(canonical)

        return urls
    except Exception as exc:
        raise ExtractGameUrlsFromListingHtmlError(
            f"extract_game_urls_from_listing_html failed for base_url '{base_url}': {exc}"
        ) from exc



def extract_game_urls_from_listing_html_by_date(html: str, base_url: str, game_date: str) -> List[str]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        urls: List[str] = []
        seen = set()
        current_date: Optional[str] = None

        for row in soup.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if not cells:
                continue

            date_text = re.sub(r"\s+", " ", cells[0].get_text(" ", strip=True)).strip()
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
            if date_match is not None:
                current_date = date_match.group(0)

            if current_date != game_date:
                continue

            for link in row.find_all("a", href=True):
                href = link["href"].strip()
                match = re.search(r"/Game/Events/\d+", href)
                if not match:
                    continue

                canonical = urljoin(base_url, match.group(0))
                if canonical in seen:
                    continue

                seen.add(canonical)
                urls.append(canonical)

        return urls
    except Exception as exc:
        raise ExtractGameUrlsFromListingHtmlByDateError(
            f"extract_game_urls_from_listing_html_by_date failed for date '{game_date}' and base_url '{base_url}': {exc}"
        ) from exc


def extract_schedule_games_from_listing_html(html: str, base_url: str) -> List[ScheduleEntry]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        schedule_games: List[ScheduleEntry] = []
        seen_game_urls = set()
        current_round: Optional[int] = None
        current_date: Optional[str] = None

        # Detect column layout by checking data rows.
        # Format A (8 cols): date | date+time | time | teams | result | periods | spectators | venue
        # Format B (7 cols): game# | date+time | teams | result | periods | spectators | venue
        # Detect by checking if first data row's cells[0] contains a date.
        layout_detected = False
        col_date = 0
        col_time = 1
        col_teams = 3
        col_result = 4
        col_periods = 5
        col_spectators = 6
        col_venue = 7

        for row in soup.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if not cells:
                continue

            row_text = re.sub(r"\s+", " ", row.get_text(" ", strip=True)).strip()
            round_match = re.search(r"(?:Round|Omg\.?|Omgång)\s*(\d+)", row_text, flags=re.IGNORECASE)
            if round_match is not None and len(cells) <= 2:
                current_round = int(round_match.group(1))
                continue

            if len(cells) < 3:
                continue

            # Detect layout once from the first data row with enough cells.
            if not layout_detected and len(cells) >= 7:
                first_cell_text = re.sub(r"\s+", " ", cells[0].get_text(" ", strip=True)).strip()
                if not re.search(r"\d{4}-\d{2}-\d{2}", first_cell_text):
                    # Format B: game number prefix, date+time in cells[1], teams in cells[2]
                    col_date = 1
                    col_time = 1
                    col_teams = 2
                    col_result = 3
                    col_periods = 4
                    col_spectators = 5
                    col_venue = 6
                layout_detected = True

            date_text = re.sub(r"\s+", " ", cells[col_date].get_text(" ", strip=True)).strip() if len(cells) > col_date else ""
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
            if date_match is not None:
                current_date = date_match.group(0)

            if current_date is None:
                continue

            time_text = re.sub(r"\s+", " ", cells[col_time].get_text(" ", strip=True)).strip() if len(cells) > col_time else ""
            time_match = re.search(r"\b\d{1,2}:\d{2}\b", time_text)
            if not time_match and len(cells) > col_time + 1:
                time_text = re.sub(r"\s+", " ", cells[col_time + 1].get_text(" ", strip=True)).strip()
                time_match = re.search(r"\b\d{1,2}:\d{2}\b", time_text)

            game_link = row.find("a", href=re.compile(r"/Game/Events/\d+"))

            game_url = ""
            if game_link is not None:
                href = game_link.get("href", "").strip()
                game_match = re.search(r"/Game/Events/\d+", href)
                if game_match is not None:
                    game_url = urljoin(base_url, game_match.group(0))
                    if game_url in seen_game_urls:
                        continue
                    seen_game_urls.add(game_url)

            # Require either a game link or a teams cell with " - " separator.
            teams_cell = ""
            if len(cells) > col_teams:
                teams_cell = re.sub(r"\s+", " ", cells[col_teams].get_text(" ", strip=True)).strip()
            if not game_url and not re.search(r"\S\s*-\s*\S", teams_cell):
                continue

            game_result = ""
            if len(cells) > col_result:
                result_text = re.sub(r"\s+", " ", cells[col_result].get_text(" ", strip=True)).strip()
                if re.search(r"^\d{1,2}\s*-\s*\d{1,2}", result_text):
                    game_result = result_text
            if not game_result:
                # Look for score pattern in row text but exclude date patterns.
                result_match = re.search(r"(?<!\d{4}-)\b(\d{1,2})\s*-\s*(\d{1,2})(?:\s*\([^)]*\))?", row_text)
                if result_match and not re.match(r"\d{4}", result_match.group(0)):
                    game_result = result_match.group(0).replace(" ", "")

            spectators = ""
            if len(cells) > col_spectators:
                spec_text = re.sub(r"\s+", " ", cells[col_spectators].get_text(" ", strip=True)).strip()
                if re.search(r"\d+", spec_text):
                    spectators = spec_text

            periods = ""
            if len(cells) > col_periods:
                periods_text = re.sub(r"\s+", " ", cells[col_periods].get_text(" ", strip=True)).strip()
                if re.search(r"\(\d+-\d+", periods_text):
                    periods = periods_text

            venue = ""
            if len(cells) > col_venue:
                venue = re.sub(r"\s+", " ", cells[col_venue].get_text(" ", strip=True)).strip()
            elif len(cells) > col_periods and not periods:
                venue = re.sub(r"\s+", " ", cells[col_periods].get_text(" ", strip=True)).strip()

            # Extract teams from the teams cell.
            home_team = ""
            away_team = ""
            if teams_cell:
                team_match = re.match(r"(.+?)\s*-\s*(.+)", teams_cell)
                if team_match:
                    home_team = team_match.group(1).strip()
                    away_team = team_match.group(2).strip()

            schedule_games.append(ScheduleEntry(
                date=current_date,
                time=time_match.group(0) if time_match else "",
                home_team=home_team,
                away_team=away_team,
                game_result=game_result,
                periods=periods,
                spectators=spectators,
                venue=venue,
                game_url=game_url,
                round=str(current_round) if current_round is not None else "",
            ))

        return schedule_games
    except Exception as exc:
        raise ExtractScheduleGamesFromListingHtmlError(
            f"extract_schedule_games_from_listing_html failed for base_url '{base_url}': {exc}"
        ) from exc


def extract_schedule_games(listing_url: str) -> List[ScheduleEntry]:
    try:
        listing_html = fetch_html(listing_url)
        return extract_schedule_games_from_listing_html(listing_html, base_url=listing_url)
    except ExtractScheduleGamesError:
        raise
    except Exception as exc:
        raise ExtractScheduleGamesError(
            f"extract_schedule_games failed for '{listing_url}': {exc}"
        ) from exc


def extract_game(url: str) -> Game:
    try:
        html = fetch_html(url)
        game = parse_top_stats(html)
        actions = parse_actions(html, score_period_count=len(game.score.periods))
        return Game(game=game.game, score=game.score, teams=game.teams, actions=actions)
    except ExtractGameError:
        raise
    except Exception as exc:
        raise ExtractGameError(f"extract_game failed for '{url}': {exc}") from exc


def extract_game_by_id(game_id: int) -> Game:
    """Scrape and parse a single game page by its SweHockey event ID.

    Args:
        game_id: Positive integer SweHockey game event ID.

    Returns:
        Parsed Game dataclass.

    Raises:
        ExtractGameError: If the ID is invalid or scraping fails.
    """
    try:
        normalized_id = int(game_id)
        if normalized_id <= 0:
            raise ValueError("game_id must be a positive integer")
        return extract_game(f"https://stats.swehockey.se/Game/Events/{normalized_id}")
    except ExtractGameError:
        raise
    except Exception as exc:
        raise ExtractGameError(f"extract_game_by_id failed for '{game_id}': {exc}") from exc


def extract_games_from_listing(listing_url: str) -> List[Game]:
    try:
        return extract_games_from_listing_with_progress(listing_url)
    except ExtractGamesFromListingError:
        raise
    except Exception as exc:
        raise ExtractGamesFromListingError(
            f"extract_games_from_listing failed for '{listing_url}': {exc}"
        ) from exc


def extract_games_from_listing_with_progress(
    listing_url: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> List[Game]:
    """Scrape all games from a schedule listing page with optional progress reporting.

    Parses the listing page for game URLs, then scrapes each one sequentially.

    Args:
        listing_url: URL of the SweHockey schedule/results page.
        progress_callback: Optional function called with (index, total, game_url)
            before each game is scraped.

    Returns:
        List of parsed Game dataclasses.

    Raises:
        ExtractGamesFromListingWithProgressError: If any game fails to scrape.
    """
    try:
        schedule_games = extract_schedule_games(listing_url)
        game_urls = [entry.game_url for entry in schedule_games if entry.game_url]

        if not game_urls:
            raise ExtractGamesFromListingWithProgressError(
                f"No game event links were found on listing page: {listing_url}"
            )

        results: List[Game] = []
        total = len(game_urls)
        for index, game_url in enumerate(game_urls, start=1):
            if progress_callback is not None:
                progress_callback(index, total, game_url)
            try:
                results.append(extract_game(game_url))
            except Exception as exc:
                raise ExtractGamesFromListingWithProgressError(
                    f"Failed to scrape game '{game_url}' from listing page '{listing_url}': {exc}"
                ) from exc

        return results
    except ExtractGamesFromListingWithProgressError:
        raise
    except Exception as exc:
        raise ExtractGamesFromListingWithProgressError(
            f"extract_games_from_listing_with_progress failed for '{listing_url}': {exc}"
        ) from exc


def extract_games_from_listing_by_date(listing_url: str, game_date: str) -> List[Game]:
    """Scrape games from a listing page filtered to a specific date.

    Args:
        listing_url: URL of the SweHockey schedule/results page.
        game_date: Date string (YYYY-MM-DD) to filter schedule entries by.

    Returns:
        List of parsed Game dataclasses for the given date (empty if none match).

    Raises:
        ExtractGamesFromListingByDateError: If scraping fails.
    """
    try:
        schedule_games = extract_schedule_games(listing_url)
        game_urls = [entry.game_url for entry in schedule_games if entry.date == game_date and entry.game_url]

        if not game_urls:
            return []

        results: List[Game] = []
        for game_url in game_urls:
            try:
                results.append(extract_game(game_url))
            except Exception as exc:
                raise ExtractGamesFromListingByDateError(
                    f"Failed to scrape game '{game_url}' for date '{game_date}' from listing page '{listing_url}': {exc}"
                ) from exc

        return results
    except ExtractGamesFromListingByDateError:
        raise
    except Exception as exc:
        raise ExtractGamesFromListingByDateError(
            f"extract_games_from_listing_by_date failed for listing_url '{listing_url}' and game_date '{game_date}': {exc}"
        ) from exc


def parse_live_games_html(html: str) -> List[ScheduleEntry]:
    """Parse the SweHockey Live page HTML to extract today's games.

    The live page uses Bootstrap responsive divs. Each game appears twice:
    once for mobile (d-flex d-sm-none) and once for desktop (d-none d-sm-flex).
    We parse the mobile view (simpler structure) using TodaysGamesGame class.

    Each game block consists of multiple TodaysGamesGame rows:
    - First row: col-5 (home) + col-2 Result (score/time + venue) + col-5 (away)
    - Second row: col-12 with game status text (e.g. "1st period (19:20)")

    Data extracted per game:
    - Home/away team names
    - Game result (score) if in progress or finished
    - Periods breakdown (e.g. "(1-1, 0-0)")
    - Game URL from the score link (javascript:openonlinewindow('/Game/Events/ID',''))
    - Venue (shown for upcoming games in the Result column)
    - Status text (e.g. "1st period (19:20)", "Waiting for 1st period")
    - Start time for upcoming games

    Args:
        html: Raw HTML string from the Live page.

    Returns:
        List of ScheduleEntry dataclasses for each game found.
    """
    soup = BeautifulSoup(html, "html.parser")
    entries: List[ScheduleEntry] = []
    seen: set = set()

    today_str = date.today().isoformat()

    # Find the mobile-view game containers (inside d-flex d-sm-none).
    mobile_containers = soup.find_all("div", class_=re.compile(r"\bd-flex\b.*\bd-sm-none\b"))

    for container in mobile_containers:
        game_divs = container.find_all("div", class_="TodaysGamesGame")
        if not game_divs:
            continue

        # First TodaysGamesGame div has the teams and score/time.
        # Second TodaysGamesGame div (if present) has the status text.
        main_div = game_divs[0]

        # Find home team (col-5 text-right)
        home_col = main_div.find("div", class_=re.compile(r"col-5.*text-right"))
        if not home_col:
            continue
        home_team = home_col.get_text(strip=True)
        if not home_team:
            continue

        # Find away team (col-5 text-left)
        away_col = main_div.find("div", class_=re.compile(r"col-5.*text-left"))
        if not away_col:
            continue
        away_team = away_col.get_text(strip=True)
        if not away_team:
            continue

        # Deduplication key
        key = (home_team, away_team)
        if key in seen:
            continue
        seen.add(key)

        # Find result/time column (col-2 with class Result)
        result_col = main_div.find("div", class_=re.compile(r"Result"))
        game_time = ""
        venue = ""
        game_result = ""
        periods = ""
        game_url = ""

        if result_col:
            # Extract game URL from score link (javascript:openonlinewindow('/Game/Events/ID',''))
            score_link = result_col.find("a", href=re.compile(r"openonlinewindow"))
            if score_link:
                href = score_link.get("href", "")
                url_match = re.search(r"/Game/Events/(\d+)", href)
                if url_match:
                    game_url = f"https://stats.swehockey.se/Game/Events/{url_match.group(1)}"

            # The Result div contains sub-divs: score/time, periods, venue.
            sub_divs = result_col.find_all("div", recursive=False)
            for sub_div in sub_divs:
                text = sub_div.get_text(strip=True)
                if not text:
                    continue
                # Check if it's a time (HH:MM)
                if re.match(r"^\d{1,2}:\d{2}$", text):
                    game_time = text
                # Check if it's a score (N - N)
                elif re.search(r"^\d+\s*-\s*\d+$", text):
                    game_result = text
                # Check if it's period scores like (1-0, 2-1, 0-0) or (1-1)
                elif re.match(r"^\([\d\s,\-]+\)$", text):
                    periods = text
                # Otherwise it's likely a venue name
                elif not re.match(r"^\d", text):
                    venue = text

            # If the score link text contains a time instead of score
            if score_link and not game_result:
                link_text = score_link.get_text(strip=True)
                if re.match(r"^\d{1,2}:\d{2}$", link_text):
                    game_time = link_text

        # Extract status from the second TodaysGamesGame row
        status = ""
        if len(game_divs) >= 2:
            status_div = game_divs[1].find("div", class_=re.compile(r"col-12"))
            if status_div:
                status = re.sub(r"\s+", " ", status_div.get_text(strip=True)).strip()

        # Parse game_clock and current_period from status text.
        # Examples: "2nd period (01:49)", "1st period (19:20)", "Waiting for 1st period"
        game_clock = ""
        current_period = ""
        clock_match = re.search(r"\((\d{1,2}:\d{2})\)", status)
        if clock_match:
            game_clock = clock_match.group(1)
        period_match = re.search(r"(\d+(?:st|nd|rd|th)\s+period)", status, re.IGNORECASE)
        if period_match:
            current_period = period_match.group(1)

        entries.append(ScheduleEntry(
            date=today_str,
            time=game_time,
            home_team=home_team,
            away_team=away_team,
            game_result=game_result,
            periods=periods,
            spectators="",
            venue=venue,
            game_url=game_url,
            round="",
            status=status,
            game_clock=game_clock,
            current_period=current_period,
        ))

    return entries


def extract_live_games(season_id: int) -> List[ScheduleEntry]:
    """Fetch and parse the SweHockey Live page for a season.

    Args:
        season_id: SweHockey season/tournament ID.

    Returns:
        List of ScheduleEntry dataclasses for today's live/upcoming games.

    Raises:
        ExtractLiveGamesError: If fetching or parsing fails.
    """
    try:
        url = f"https://stats.swehockey.se/ScheduleAndResults/Live/{season_id}"
        html = fetch_html(url)
        return parse_live_games_html(html)
    except ExtractLiveGamesError:
        raise
    except Exception as exc:
        raise ExtractLiveGamesError(
            f"extract_live_games failed for season '{season_id}': {exc}"
        ) from exc
