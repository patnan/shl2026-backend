#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path

from extract_top_stats import calculate_standings, extract_games_from_listing_with_progress


CSV_COLUMNS = [
    ("RK", "rank"),
    ("Team", "team"),
    ("GP", "games_played"),
    ("W", "w"),
    ("T", "t"),
    ("L", "l"),
    ("GF:GA (GD)", "gf_ga_gd"),
    ("TP", "tp"),
    ("OTW", "otw"),
    ("OTL", "otl"),
    ("GWSW", "gwsw"),
    ("GWSL", "gwsl"),
]


def format_standings_row(entry: dict) -> dict:
    return {
        "rank": entry["rank"],
        "team": entry["team"],
        "games_played": entry["games_played"],
        "w": entry["w"],
        "t": entry["t"],
        "l": entry["l"],
        "gf_ga_gd": f"{entry['goals_for']}:{entry['goals_against']} ({entry['goal_difference']})",
        "tp": entry["tp"],
        "otw": entry["otw"],
        "otl": entry["otl"],
        "gwsw": entry["gwsw"],
        "gwsl": entry["gwsl"],
    }


def print_standings_table(standings: list[dict]) -> None:
    rows = [format_standings_row(entry) for entry in standings]
    column_widths = {}

    for header, key in CSV_COLUMNS:
        value_width = max((len(str(row[key])) for row in rows), default=0)
        column_widths[key] = max(len(header), value_width)

    header_line = "  ".join(
        header.ljust(column_widths[key]) if key == "team" else header.rjust(column_widths[key])
        for header, key in CSV_COLUMNS
    )
    separator_line = "  ".join("-" * column_widths[key] for _, key in CSV_COLUMNS)

    print(header_line)
    print(separator_line)
    for row in rows:
        print(
            "  ".join(
                str(row[key]).ljust(column_widths[key]) if key == "team" else str(row[key]).rjust(column_widths[key])
                for _, key in CSV_COLUMNS
            )
        )


def write_standings_csv(standings: list[dict], output_path: Path) -> None:
    rows = [format_standings_row(entry) for entry in standings]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[header for header, _ in CSV_COLUMNS])
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row[key] for header, key in CSV_COLUMNS})


def resolve_output_path(cache_dir: Path, path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return cache_dir / path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape games from a SweHockey listing page and calculate standings"
    )
    parser.add_argument(
        "listing_url",
        help="Listing page URL containing /Game/Events/<id> links",
    )
    parser.add_argument(
        "--output",
        default="standings.json",
        help="Output JSON file path for standings (default: standings.json)",
    )
    parser.add_argument(
        "--cache-dir",
        default="cache",
        help="Directory where generated JSON/CSV files are stored (default: cache)",
    )
    parser.add_argument(
        "--games-output",
        help="Optional output JSON file path for the raw scraped games",
    )
    parser.add_argument(
        "--csv-output",
        help="Optional CSV file path for standings in screenshot-style column order",
    )
    args = parser.parse_args()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    def on_progress(index: int, total: int, game_url: str) -> None:
        print(f"[{index}/{total}] scraping {game_url}", flush=True)

    games = extract_games_from_listing_with_progress(args.listing_url, progress_callback=on_progress)
    standings = calculate_standings(games)

    output_path = resolve_output_path(cache_dir, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(standings, ensure_ascii=False, indent=2), encoding="utf-8")

    print_standings_table(standings)

    if args.games_output:
        games_output_path = resolve_output_path(cache_dir, args.games_output)
        games_output_path.parent.mkdir(parents=True, exist_ok=True)
        games_output_path.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved raw game JSON to: {games_output_path}")

    if args.csv_output:
        csv_output_path = resolve_output_path(cache_dir, args.csv_output)
        csv_output_path.parent.mkdir(parents=True, exist_ok=True)
        write_standings_csv(standings, csv_output_path)
        print(f"Saved standings CSV to: {csv_output_path}")

    print(f"Scraped {len(games)} games from: {args.listing_url}")
    print(f"Saved standings JSON to: {output_path}")


if __name__ == "__main__":
    main()