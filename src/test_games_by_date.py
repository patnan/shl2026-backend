#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from src.shl.extract_top_stats import extract_games_from_listing_by_date


def resolve_output_path(cache_dir: Path, path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return cache_dir / path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape only games for a specific date from a SweHockey schedule page"
    )
    parser.add_argument(
        "listing_url",
        help="Schedule page URL, for example https://stats.swehockey.se/ScheduleAndResults/Schedule/18263",
    )
    parser.add_argument(
        "game_date",
        help="Game date in YYYY-MM-DD format, for example 2025-09-16",
    )
    parser.add_argument(
        "--output",
        default="games_by_date.json",
        help="Output JSON file path (default: games_by_date.json)",
    )
    parser.add_argument(
        "--cache-dir",
        default="cache",
        help="Directory where generated JSON files are stored (default: cache)",
    )
    args = parser.parse_args()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    games = extract_games_from_listing_by_date(args.listing_url, args.game_date)

    output_path = resolve_output_path(cache_dir, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Date: {args.game_date}")
    print(f"Games found: {len(games)}")
    print(f"Saved JSON to: {output_path}")

    if not games:
        return

    print("Found games:")
    for index, game in enumerate(games, start=1):
        game_info = game.get("game", {})
        score_info = game.get("score", {})
        date_time = game_info.get("date_time")
        home_team = game_info.get("home_team")
        away_team = game_info.get("away_team")
        score = score_info.get("current")
        arena = game_info.get("arena")

        print(f"{index}. {date_time} | {home_team} - {away_team} | {score} | {arena}")


if __name__ == "__main__":
    main()
