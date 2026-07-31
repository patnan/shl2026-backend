from typing import Dict, List

from src.shl.helpers.extraction import (
    extract_games_from_listing,
    extract_games_from_listing_by_date,
    extract_games_from_listing_with_progress,
    extract_schedule_games,
)


class FetchScheduleError(RuntimeError):
    pass


class FetchGamesForDateError(RuntimeError):
    pass


class FetchAllPlayedGamesError(RuntimeError):
    pass


def fetch_schedule(listing_url: str) -> List[Dict[str, object]]:
    try:
        return extract_schedule_games(listing_url)
    except Exception as exc:
        raise FetchScheduleError(f"fetch_schedule failed for '{listing_url}': {exc}") from exc


def fetch_games_for_date(listing_url: str, game_date: str) -> List[Dict[str, object]]:
    try:
        return extract_games_from_listing_by_date(listing_url, game_date)
    except Exception as exc:
        raise FetchGamesForDateError(
            f"fetch_games_for_date failed for '{listing_url}' and '{game_date}': {exc}"
        ) from exc


def fetch_all_played_games(listing_url: str) -> List[Dict[str, object]]:
    try:
        return extract_games_from_listing(listing_url)
    except Exception as exc:
        raise FetchAllPlayedGamesError(f"fetch_all_played_games failed for '{listing_url}': {exc}") from exc


def fetch_all_played_games_with_progress(listing_url: str, progress_callback=None) -> List[Dict[str, object]]:
    try:
        return extract_games_from_listing_with_progress(listing_url, progress_callback=progress_callback)
    except Exception as exc:
        raise FetchAllPlayedGamesError(
            f"fetch_all_played_games_with_progress failed for '{listing_url}': {exc}"
        ) from exc


# REQ facade aliases.
fetchSchedule = fetch_schedule
fetchGamesForDate = fetch_games_for_date
fetchAllPlayedGames = fetch_all_played_games
