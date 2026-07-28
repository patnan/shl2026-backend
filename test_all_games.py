#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from extract_top_stats import extract_games_from_listing_with_progress


def resolve_output_path(cache_dir: Path, path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return cache_dir / path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape all game event links from a listing page and return aggregated game data"
    )
    parser.add_argument(
        "listing_url",
        help="Listing page URL containing /Game/Events/<id> links",
    )
    parser.add_argument(
        "--output",
        default="all_games.json",
        help="Output JSON file path (default: all_games.json)",
    )
    parser.add_argument(
        "--cache-dir",
        default="cache",
        help="Directory where generated JSON files are stored (default: cache)",
    )
    args = parser.parse_args()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    def on_progress(index: int, total: int, game_url: str) -> None:
        print(f"[{index}/{total}] scraping {game_url}", flush=True)

    games = extract_games_from_listing_with_progress(args.listing_url, progress_callback=on_progress)

    output_path = resolve_output_path(cache_dir, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Scraped {len(games)} games from: {args.listing_url}")
    print(f"Saved JSON to: {output_path}")


if __name__ == "__main__":
    main()
