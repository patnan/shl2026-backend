#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path

from src.shl.api import (
    calculate_standings,
    compare_game_score_change,
    extract_game_by_id,
    extract_games_from_listing_by_date,
    extract_games_from_listing_with_progress,
)
from src.shl.helpers.extraction import fetch_html


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


def resolve_output_path(cache_dir: Path, path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return cache_dir / path


def resolve_input_path(cache_dir: Path, path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute() or path.exists():
        return path
    cached = cache_dir / path
    return cached if cached.exists() else path


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


def cmd_scrape(args: argparse.Namespace, cache_dir: Path) -> None:
    if args.game_id is not None:
        result = extract_game_by_id(args.game_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if not args.listing_url:
        print("error: listing_url is required unless --game-id is provided")
        raise SystemExit(1)

    if args.date:
        games = extract_games_from_listing_by_date(args.listing_url, args.date)
        output_path = resolve_output_path(cache_dir, args.output or "games_by_date.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Date: {args.date}")
        print(f"Games found: {len(games)}")
        print(f"Saved JSON to: {output_path}")
        for index, game in enumerate(games, start=1):
            g, s = game.get("game", {}), game.get("score", {})
            print(f"{index}. {g.get('date_time')} | {g.get('home_team')} - {g.get('away_team')} | {s.get('current')} | {g.get('arena')}")
        return

    def on_progress(index: int, total: int, game_url: str) -> None:
        print(f"[{index}/{total}] scraping {game_url}", flush=True)

    games = extract_games_from_listing_with_progress(args.listing_url, progress_callback=on_progress)

    if args.games_output:
        games_path = resolve_output_path(cache_dir, args.games_output)
        games_path.parent.mkdir(parents=True, exist_ok=True)
        games_path.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved raw game JSON to: {games_path}")

    if args.standings or not args.games_output:
        standings = calculate_standings(games)
        output_path = resolve_output_path(cache_dir, args.output or "standings.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(standings, ensure_ascii=False, indent=2), encoding="utf-8")
        print_standings_table(standings)
        if args.csv_output:
            csv_path = resolve_output_path(cache_dir, args.csv_output)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            write_standings_csv(standings, csv_path)
            print(f"Saved standings CSV to: {csv_path}")
        print(f"Scraped {len(games)} games from: {args.listing_url}")
        print(f"Saved standings JSON to: {output_path}")


def cmd_validate(args: argparse.Namespace, cache_dir: Path) -> None:
    season_id = args.season_id
    overview_url = f"https://stats.swehockey.se/ScheduleAndResults/Overview/{season_id}"

    html = fetch_html(overview_url)
    if args.output:
        out = resolve_output_path(cache_dir, args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"Saved HTML to: {out}")
    print(f"Loaded {len(html)} characters from: {overview_url}")
    print(f"Consent markers detected: {'Responsible use of your data' in html or 'Cookiebot' in html}")
    print(f"Standings markers detected: {'Group Standings' in html or 'GF:GA' in html or 'GWSW' in html}")
    print("Preview:")
    print(html[: args.preview_chars])


def cmd_compare(args: argparse.Namespace, cache_dir: Path) -> None:
    previous_game = json.loads(Path(args.previous_file).read_text(encoding="utf-8"))
    current_game = json.loads(Path(args.current_file).read_text(encoding="utf-8"))
    result = compare_game_score_change(previous_game, current_game)

    if args.output:
        out = resolve_output_path(cache_dir, args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved comparison JSON to: {out}")

    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="SHL scraper and validation toolkit")
    parser.add_argument("--cache-dir", default="cache", help="Cache directory (default: cache)")
    sub = parser.add_subparsers(dest="command", required=True)

    # scrape
    p_scrape = sub.add_parser("scrape", help="Scrape games from a listing page")
    p_scrape.add_argument("listing_url", nargs="?", help="Listing page URL containing /Game/Events/<id> links")
    p_scrape.add_argument("--game-id", type=int, help="Extract a single game by id")
    p_scrape.add_argument("--date", help="Filter to a specific date in YYYY-MM-DD format")
    p_scrape.add_argument("--output", help="Output JSON file path")
    p_scrape.add_argument("--games-output", help="Save raw scraped games to this JSON path")
    p_scrape.add_argument("--standings", action="store_true", help="Compute and print standings (default when no --games-output)")
    p_scrape.add_argument("--csv-output", help="Save standings as CSV to this path")

    # validate
    p_val = sub.add_parser("validate", help="Fetch and preview overview page for a season")
    p_val.add_argument("season_id", nargs="?", type=int, default=18263, help="Season/tournament id")
    p_val.add_argument("--output", help="Output path for raw HTML")
    p_val.add_argument("--preview-chars", type=int, default=1000, help="Characters of HTML preview to print (default: 1000)")

    # compare
    p_cmp = sub.add_parser("compare", help="Compare two game JSON snapshots for score changes")
    p_cmp.add_argument("previous_file", help="Path to previous game JSON file")
    p_cmp.add_argument("current_file", help="Path to current game JSON file")
    p_cmp.add_argument("--output", help="Output path for comparison result JSON")

    args = parser.parse_args()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    {"scrape": cmd_scrape, "validate": cmd_validate, "compare": cmd_compare}[args.command](args, cache_dir)


if __name__ == "__main__":
    main()
