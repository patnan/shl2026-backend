#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from extract_top_stats import (
    build_validation_report,
    fetch_html,
    load_or_fetch_season_validation_inputs,
    validate_multiple_seasons,
    validate_season_standings,
)


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load a SweHockey overview page or validate calculated standings against the overview table"
    )
    parser.add_argument(
        "season_id",
        nargs="?",
        type=int,
        default=18263,
        help="Season/tournament id shared by Schedule and Overview URLs",
    )
    parser.add_argument(
        "--season-ids",
        nargs="+",
        type=int,
        help="Optional list of season/tournament ids to validate in one batch",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Compare standings calculated from the Schedule page against the Overview standings table",
    )
    parser.add_argument(
        "--games-input",
        help="Optional path to previously scraped games JSON to avoid refetching the Schedule page",
    )
    parser.add_argument(
        "--overview-input",
        help="Optional path to saved Overview HTML to avoid refetching the Overview page",
    )
    parser.add_argument(
        "--cache-dir",
        default="cache",
        help="Directory for season-specific cache files like games_<season_id>.json and overview_<season_id>.html",
    )
    parser.add_argument(
        "--output",
        help="Optional file path to save the raw HTML response or compact validation report JSON",
    )
    parser.add_argument(
        "--full-output",
        help="Optional file path to save the full validation JSON payload",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=1000,
        help="How many characters of the response to print (default: 1000)",
    )
    args = parser.parse_args()
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    overview_url = f"https://stats.swehockey.se/ScheduleAndResults/Overview/{args.season_id}"

    if args.validate:
        if args.season_ids:
            def make_progress_callback(batch_index: int, batch_total: int, season_id: int):
                def on_progress(index: int, total: int, game_url: str) -> None:
                    print(f"[{batch_index}/{batch_total}] season {season_id} [{index}/{total}] scraping {game_url}", flush=True)

                return on_progress

            batch_validation = validate_multiple_seasons(
                args.season_ids,
                progress_callback_factory=make_progress_callback,
                cache_dir=cache_dir,
            )

            if args.output:
                output_path = resolve_output_path(cache_dir, args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(batch_validation, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"Saved batch validation JSON to: {output_path}")

            print(f"Validated seasons: {', '.join(str(season_id) for season_id in args.season_ids)}")
            print(f"All match: {batch_validation['all_match']}")
            print(f"Successful seasons: {batch_validation['successful_seasons']}")
            print(f"Failed seasons: {batch_validation['failed_seasons']}")
            print(f"Mismatching seasons: {batch_validation['mismatching_seasons']}")
            for result in batch_validation["results"]:
                status = "match" if result["matches"] and result["error"] is None else "failed"
                if result["error"] is None and not result["matches"]:
                    status = "mismatch"
                print(
                    f"Season {result['season_id']}: status={status}, mismatches={result['mismatch_count']}, "
                    f"games_source={result['games_source']}, overview_source={result['overview_source']}, error={result['error']}"
                )
            return

        games = None
        overview_html = None

        if args.games_input:
            games_input_path = resolve_input_path(cache_dir, args.games_input)
            games = json.loads(games_input_path.read_text(encoding="utf-8"))
        if args.overview_input:
            overview_input_path = resolve_input_path(cache_dir, args.overview_input)
            overview_html = overview_input_path.read_text(encoding="utf-8")

        def on_progress(index: int, total: int, game_url: str) -> None:
            print(f"[{index}/{total}] scraping {game_url}", flush=True)

        season_inputs = load_or_fetch_season_validation_inputs(
            args.season_id,
            cache_dir=cache_dir,
            progress_callback=on_progress if games is None else None,
            games=games,
            overview_html=overview_html,
        )
        validation = validate_season_standings(args.season_id, games=season_inputs["games"], overview_html=season_inputs["overview_html"])
        report = build_validation_report(validation)

        if args.output:
            output_path = resolve_output_path(cache_dir, args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Saved validation report JSON to: {output_path}")

        if args.full_output:
            full_output_path = resolve_output_path(cache_dir, args.full_output)
            full_output_path.parent.mkdir(parents=True, exist_ok=True)
            full_output_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Saved full validation JSON to: {full_output_path}")

        print(f"Season: {args.season_id}")
        print(f"Matches overview: {report['matches']}")
        print(f"Mismatch count: {report['mismatch_count']}")
        if args.games_input:
            print(f"Used cached games input: {args.games_input}")
        else:
            print(f"Games source: {season_inputs['games_source']}")
        if args.overview_input:
            print(f"Used cached overview input: {args.overview_input}")
        else:
            print(f"Overview source: {season_inputs['overview_source']}")
        if report["mismatches"]:
            print("Mismatches:")
            for mismatch in report["mismatches"]:
                print(json.dumps(mismatch, ensure_ascii=False))
        return

    html = fetch_html(overview_url)

    if args.output:
        output_path = resolve_output_path(cache_dir, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        print(f"Saved HTML to: {output_path}")

    print(f"Loaded {len(html)} characters from: {overview_url}")

    consent_detected = "Responsible use of your data" in html or "Cookiebot" in html
    standings_detected = "Group Standings" in html or "GF:GA" in html or "GWSW" in html

    print(f"Consent markers detected: {consent_detected}")
    print(f"Standings markers detected: {standings_detected}")
    print("Preview:")
    print(html[: args.preview_chars])


if __name__ == "__main__":
    main()