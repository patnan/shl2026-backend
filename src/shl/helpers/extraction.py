import json
import re
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

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


def extract_schedule_games_from_listing_html(html: str, base_url: str) -> List[Dict[str, object]]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        schedule_games: List[Dict[str, object]] = []
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

            game_link = row.find("a", href=re.compile(r"/Game/Events/\d+"))
            if game_link is None:
                continue

            href = game_link.get("href", "").strip()
            game_match = re.search(r"/Game/Events/\d+", href)
            if game_match is None:
                continue
            game_url = urljoin(base_url, game_match.group(0))
            if game_url in seen_game_urls:
                continue
            seen_game_urls.add(game_url)

            game_result = ""
            if len(cells) > 3:
                game_result = re.sub(r"\s+", " ", cells[3].get_text(" ", strip=True)).strip()
            if not game_result:
                result_match = re.search(r"\d+\s*-\s*\d+(?:\s*\([^)]*\))?", row_text)
                game_result = result_match.group(0).replace(" ", "") if result_match else ""

            spectators: Optional[int] = None
            if len(cells) > 4:
                spectators_text = re.sub(r"\D", "", cells[4].get_text(" ", strip=True))
                if spectators_text:
                    spectators = int(spectators_text)

            venue = ""
            if len(cells) > 5:
                venue = re.sub(r"\s+", " ", cells[5].get_text(" ", strip=True)).strip()

            schedule_games.append(
                {
                    "date": current_date,
                    "time": time_match.group(0) if time_match else "",
                    "game_result": game_result,
                    "spectators": spectators,
                    "venue": venue,
                    "game_url": game_url,
                    "round": current_round,
                }
            )

        return schedule_games
    except Exception as exc:
        raise ExtractScheduleGamesFromListingHtmlError(
            f"extract_schedule_games_from_listing_html failed for base_url '{base_url}': {exc}"
        ) from exc


def extract_schedule_games(listing_url: str) -> List[Dict[str, object]]:
    try:
        listing_html = fetch_html(listing_url)
        return extract_schedule_games_from_listing_html(listing_html, base_url=listing_url)
    except ExtractScheduleGamesError:
        raise
    except Exception as exc:
        raise ExtractScheduleGamesError(
            f"extract_schedule_games failed for '{listing_url}': {exc}"
        ) from exc



def extract_game(url: str) -> Dict[str, object]:
    try:
        html = fetch_html(url)
        stats = parse_top_stats(html)
        stats["actions"] = parse_actions(html, score_period_count=len(stats.get("score", {}).get("periods", [])))
        return stats
    except ExtractGameError:
        raise
    except Exception as exc:
        raise ExtractGameError(f"extract_game failed for '{url}': {exc}") from exc


def extract_game_by_id(game_id: int) -> Dict[str, object]:
    try:
        normalized_id = int(game_id)
        if normalized_id <= 0:
            raise ValueError("game_id must be a positive integer")
        return extract_game(f"https://stats.swehockey.se/Game/Events/{normalized_id}")
    except ExtractGameError:
        raise
    except Exception as exc:
        raise ExtractGameError(f"extract_game_by_id failed for '{game_id}': {exc}") from exc


def extract_games_from_listing(listing_url: str) -> List[Dict[str, object]]:
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
) -> List[Dict[str, object]]:
    try:
        schedule_games = extract_schedule_games(listing_url)
        game_urls = [
            str(game["game_url"])
            for game in schedule_games
            if isinstance(game, dict) and game.get("game_url")
        ]

        if not game_urls:
            raise ExtractGamesFromListingWithProgressError(
                f"No game event links were found on listing page: {listing_url}"
            )

        results: List[Dict[str, object]] = []
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


def extract_games_from_listing_by_date(listing_url: str, game_date: str) -> List[Dict[str, object]]:
    try:
        schedule_games = extract_schedule_games(listing_url)
        game_urls = [
            str(game["game_url"])
            for game in schedule_games
            if isinstance(game, dict) and game.get("date") == game_date and game.get("game_url")
        ]

        if not game_urls:
            return []

        results: List[Dict[str, object]] = []
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
