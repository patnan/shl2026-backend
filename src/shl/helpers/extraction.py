import json
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


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



def fetch_html(url: str, timeout: int = 20) -> str:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text
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



def _get_facade_module():
    try:
        import src.shl.api as api

        return api
    except ModuleNotFoundError:
        import extract_top_stats as api

        return api


def extract_game(url: str) -> Dict[str, object]:
    try:
        api = _get_facade_module()

        html = api.fetch_html(url)
        stats = api.parse_top_stats(html)
        stats["actions"] = api.parse_actions(html, score_period_count=len(stats.get("score", {}).get("periods", [])))
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

        api = _get_facade_module()

        return api.extract_game(f"https://stats.swehockey.se/Game/Events/{normalized_id}")
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
        api = _get_facade_module()

        listing_html = api.fetch_html(listing_url)
        game_urls = api.extract_game_urls_from_listing_html(listing_html, base_url=listing_url)

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
                results.append(api.extract_game(game_url))
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
        api = _get_facade_module()

        listing_html = api.fetch_html(listing_url)
        game_urls = api.extract_game_urls_from_listing_html_by_date(listing_html, base_url=listing_url, game_date=game_date)

        if not game_urls:
            return []

        results: List[Dict[str, object]] = []
        for game_url in game_urls:
            try:
                results.append(api.extract_game(game_url))
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
