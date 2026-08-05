#!/usr/bin/env python3
import argparse
import json
import logging
from pathlib import Path

from src.shl.logging_config import setup_logging

from src.shl.api import (
    calculate_standings,
    compare_game_score_change,
    extract_game_by_id,
    extract_games_from_listing_by_date,
    extract_games_from_listing_with_progress,
)
from src.shl.models import Game
from src.shl.helpers.extraction import fetch_html
from src.shl.poller import run_poller_worker, seed_season_targets
from src.shl.notifier import run_notification_worker


STANDINGS_COLUMNS = [
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


def format_standings_row(row) -> dict:
    return {
        "rank": row.rank,
        "team": row.team,
        "games_played": row.games_played,
        "w": row.w,
        "t": row.t,
        "l": row.l,
        "gf_ga_gd": f"{row.goals_for}:{row.goals_against} ({row.goal_difference})",
        "tp": row.tp,
        "otw": row.otw,
        "otl": row.otl,
        "gwsw": row.gwsw,
        "gwsl": row.gwsl,
    }


def print_standings_table(standings) -> None:
    rows = [format_standings_row(entry) for entry in standings]
    if not rows:
        print("No standings to display.")
        return

    column_widths = {}
    for header, key in STANDINGS_COLUMNS:
        value_width = max((len(str(row[key])) for row in rows), default=0)
        column_widths[key] = max(len(header), value_width)

    header_line = "  ".join(
        header.ljust(column_widths[key]) if key == "team" else header.rjust(column_widths[key])
        for header, key in STANDINGS_COLUMNS
    )
    separator_line = "  ".join("-" * column_widths[key] for _, key in STANDINGS_COLUMNS)

    print(header_line)
    print(separator_line)
    for row in rows:
        print(
            "  ".join(
                str(row[key]).ljust(column_widths[key]) if key == "team" else str(row[key]).rjust(column_widths[key])
                for _, key in STANDINGS_COLUMNS
            )
        )


def cmd_scrape(args: argparse.Namespace, cache_dir: Path) -> None:
    if args.game_id is not None:
        game = extract_game_by_id(args.game_id)
        print(json.dumps(game.to_dict(), indent=2, ensure_ascii=False))
        return

    if not args.listing_url:
        print("error: listing_url is required unless --game-id is provided")
        raise SystemExit(1)

    if args.date:
        games = extract_games_from_listing_by_date(args.listing_url, args.date)
        print(f"Date: {args.date} — {len(games)} game(s)")
        for i, game in enumerate(games, start=1):
            print(f"  {i}. {game.game.date_time} | {game.game.home_team} - {game.game.away_team} | {game.score.current} | {game.game.arena}")
        return

    def on_progress(index: int, total: int, game_url: str) -> None:
        print(f"[{index}/{total}] scraping {game_url}", flush=True)

    games = extract_games_from_listing_with_progress(args.listing_url, progress_callback=on_progress)
    print(f"\nScraped {len(games)} games from: {args.listing_url}")

    standings = calculate_standings(games)
    print_standings_table(standings)


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
    previous_game = Game.from_dict(json.loads(Path(args.previous_file).read_text(encoding="utf-8")))
    current_game = Game.from_dict(json.loads(Path(args.current_file).read_text(encoding="utf-8")))
    result = compare_game_score_change(previous_game, current_game)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


def cmd_serve(args: argparse.Namespace, cache_dir: Path) -> None:
    from src.shl.rest_api import create_app
    import uvicorn

    app = create_app(cache_dir)
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


def cmd_poller_seed(args: argparse.Namespace, cache_dir: Path) -> None:
    result = seed_season_targets(
        cache_dir,
        season_id=args.season_id,
        force_reparse_schedule=args.force_reparse_schedule,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_poller_run(args: argparse.Namespace, cache_dir: Path) -> None:
    result = run_poller_worker(
        cache_dir,
        tick_interval_seconds=args.tick_interval,
        max_ticks=args.max_ticks,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_notifier_run(args: argparse.Namespace, cache_dir: Path) -> None:
    result = run_notification_worker(
        cache_dir,
        tick_interval_seconds=args.tick_interval,
        max_ticks=args.max_ticks,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_snapshot(args: argparse.Namespace, cache_dir: Path) -> None:
    from datetime import datetime
    from urllib.parse import urlparse

    url = args.url
    html = fetch_html(url)

    if args.output:
        out = resolve_output_path(cache_dir, args.output)
    else:
        # Auto-generate filename from URL + timestamp
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        name_base = "_".join(path_parts) if path_parts else "page"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path("snapshots") / f"{name_base}_{timestamp}.html"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Downloaded {len(html):,} characters from: {url}")
    print(f"Saved to: {out}")


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="SHL scraper and validation toolkit")
    parser.add_argument("--cache-dir", default="cache", help="Cache directory (default: cache)")
    sub = parser.add_subparsers(dest="command", required=True)

    # scrape
    p_scrape = sub.add_parser("scrape", help="Scrape and display games from a listing page")
    p_scrape.add_argument("listing_url", nargs="?", help="Listing page URL")
    p_scrape.add_argument("--game-id", type=int, help="Extract a single game by id")
    p_scrape.add_argument("--date", help="Filter to a specific date (YYYY-MM-DD)")

    # validate
    p_val = sub.add_parser("validate", help="Fetch and preview overview page for a season")
    p_val.add_argument("season_id", nargs="?", type=int, default=18263, help="Season/tournament id")
    p_val.add_argument("--output", help="Output path for raw HTML")
    p_val.add_argument("--preview-chars", type=int, default=1000, help="Characters of HTML preview to print")

    # compare
    p_cmp = sub.add_parser("compare", help="Compare two game JSON snapshots for score changes")
    p_cmp.add_argument("previous_file", help="Path to previous game JSON file")
    p_cmp.add_argument("current_file", help="Path to current game JSON file")

    # serve
    p_srv = sub.add_parser("serve", help="Run REST API server")
    p_srv.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p_srv.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    p_srv.add_argument("--reload", action="store_true", help="Enable auto-reload (development)")

    # poller seed
    p_seed = sub.add_parser("poller-seed", help="Seed poll targets for a season")
    p_seed.add_argument("season_id", type=int, help="Season/tournament id")
    p_seed.add_argument("--force-reparse-schedule", action="store_true", help="Force schedule refetch")

    # poller run
    p_run = sub.add_parser("poller-run", help="Run poller worker loop")
    p_run.add_argument("--tick-interval", type=float, default=5.0, help="Seconds between ticks (default: 5.0)")
    p_run.add_argument("--max-ticks", type=int, help="Stop after N ticks (default: run forever)")

    # notifier run
    p_notif = sub.add_parser("notifier-run", help="Run notification worker (FCM push)")
    p_notif.add_argument("--tick-interval", type=float, default=5.0, help="Seconds between event checks (default: 5.0)")
    p_notif.add_argument("--max-ticks", type=int, help="Stop after N ticks (default: run forever)")

    # snapshot
    p_snap = sub.add_parser("snapshot", help="Download raw HTML from a URL and save to file")
    p_snap.add_argument("url", help="URL to download")
    p_snap.add_argument("--output", "-o", help="Output file path (default: auto-generated from URL)")

    args = parser.parse_args()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    {
        "scrape": cmd_scrape,
        "validate": cmd_validate,
        "compare": cmd_compare,
        "serve": cmd_serve,
        "poller-seed": cmd_poller_seed,
        "poller-run": cmd_poller_run,
        "notifier-run": cmd_notifier_run,
        "snapshot": cmd_snapshot,
    }[args.command](args, cache_dir)


if __name__ == "__main__":
    main()
