from src.shl.game import (
    compare_game_score_change,
    fetchGame,
    fetchGameById,
    fetch_game,
    fetch_game_by_id,
)
from src.shl.helpers.extraction import extract_schedule_games_from_listing_html
from src.shl.schedule import (
    fetchAllPlayedGames,
    fetchGamesForDate,
    fetchSchedule,
    fetch_all_played_games,
    fetch_all_played_games_with_progress,
    fetch_games_for_date,
    fetch_schedule,
)
from src.shl.standings import calculate_standings, fetchTable, fetch_table


# Backward-compatible aliases for existing callers.
extract_game_by_id = fetch_game_by_id
extract_games_from_listing = fetch_all_played_games
extract_games_from_listing_by_date = fetch_games_for_date
extract_games_from_listing_with_progress = fetch_all_played_games_with_progress
extract_schedule_games = fetch_schedule

__all__ = [
    "extract_game_by_id",
    "extract_games_from_listing",
    "extract_games_from_listing_by_date",
    "extract_games_from_listing_with_progress",
    "extract_schedule_games",
    "extract_schedule_games_from_listing_html",
    "calculate_standings",
    "compare_game_score_change",
    "fetch_game",
    "fetch_game_by_id",
    "fetch_schedule",
    "fetch_games_for_date",
    "fetch_all_played_games",
    "fetch_table",
    "fetchGame",
    "fetchGameById",
    "fetchSchedule",
    "fetchGamesForDate",
    "fetchAllPlayedGames",
    "fetchTable",
]
