import dataclasses
import json
import re
import time
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

        for row in soup.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if not cells:
                continue

            row_text = re.sub(r"\s+", " ", row.get_text(" ", strip=True)).strip()
            round_match = re.search(r"(?:Round|Omg\.?|Omgång)\s*(\d+)", row_text, flags=re.IGNORECASE)
            if round_match is not None and len(cells) <= 2:
                current_round = int(round_match.group(1))
                continue

            date_text = re.sub(r"\s+", " ", cells[0].get_text(" ", strip=True)).strip()
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
            if date_match is not None:
                current_date = date_match.group(0)

            if current_date is None:
                continue

            time_text = re.sub(r"\s+", " ", cells[1].get_text(" ", strip=True)).strip() if len(cells) > 1 else ""
            time_match = re.search(r"\b\d{1,2}:\d{2}\b", time_text)
            if not time_match and len(cells) > 2:
                time_text = re.sub(r"\s+", " ", cells[2].get_text(" ", strip=True)).strip()
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
            if len(cells) > 3:
                teams_cell = re.sub(r"\s+", " ", cells[3].get_text(" ", strip=True)).strip()
            if not game_url and not re.search(r"\S\s*-\s*\S", teams_cell):
                continue

            game_result = ""
            if len(cells) > 4:
                result_text = re.sub(r"\s+", " ", cells[4].get_text(" ", strip=True)).strip()
                if re.search(r"^\d{1,2}\s*-\s*\d{1,2}", result_text):
                    game_result = result_text
            if not game_result:
                # Look for score pattern in row text but exclude date patterns.
                result_match = re.search(r"(?<!\d{4}-)\b(\d{1,2})\s*-\s*(\d{1,2})(?:\s*\([^)]*\))?", row_text)
                if result_match and not re.match(r"\d{4}", result_match.group(0)):
                    game_result = result_match.group(0).replace(" ", "")

            spectators = ""
            if len(cells) > 6:
                spec_text = re.sub(r"\s+", " ", cells[6].get_text(" ", strip=True)).strip()
                if re.search(r"\d+", spec_text):
                    spectators = spec_text

            venue = ""
            if len(cells) > 7:
                venue = re.sub(r"\s+", " ", cells[7].get_text(" ", strip=True)).strip()
            elif len(cells) > 5:
                venue = re.sub(r"\s+", " ", cells[5].get_text(" ", strip=True)).strip()

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
