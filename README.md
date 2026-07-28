# SHL 2026 Scraper and Validation Toolkit

This project scrapes SweHockey game pages, normalizes game data, computes standings, validates standings against SweHockey overview tables, and compares score changes between game snapshots.

The implementation now lives under `src/`.

## What has been implemented

- Core game extraction from SweHockey event pages.
- Top stats parsing:
  - score and period breakdown
  - shots, saves, PIM, and power play values
- Actions parsing into structured JSON objects.
- Improved shootout handling:
  - explicit parsing of Game Winning Shot and Game Winning Shots subsections
  - PS events are checked for Missed Penalty Shot text to decide goal vs no-goal
- Standings calculation including regulation, overtime, and game winning shot columns.
- Validation flow against SweHockey Overview pages.
- Batch validation across multiple seasons with cache reuse.
- Date-based game scraping from schedule pages.
- Snapshot-to-snapshot score comparison with team, scorer, and time details.
- Convenience API to extract a single game by id.

## Cache behavior

Generated files are now routed to a cache directory by default.

- Default cache folder: cache/
- Relative output paths are stored under cache/
- Absolute output paths are respected as-is
- Overview validation cache files are stored as:
  - games_<season_id>.json
  - overview_<season_id>.html

The cache folder is ignored by git.

## Main modules and scripts

- src/shl/api.py
  - Primary functions: `main()`, `extract_game()`, `extract_game_by_id()`, `extract_games_from_listing()`, `extract_games_from_listing_with_progress()`, `extract_games_from_listing_by_date()`, `parse_top_stats()`, `parse_actions()`, `calculate_standings()`, `validate_season_standings()`, `validate_multiple_seasons()`, `compare_game_score_change()`, and `compare_game_score_change_from_files()`.
  - This is the public entrypoint for the toolkit and also exposes the CLI used for single-game extraction.

- src/shl/parsing.py
  - Primary functions: `parse_top_stats()`, `parse_actions()`, `parse_score_block()`, `parse_players()`, `extract_penalty_metadata()`, `find_top_stats_table()`, `find_actions_table()`, and `clean_text()`.
  - Handles the HTML parsing, normalization, and event extraction logic.

- src/shl/extraction.py
  - Primary functions: `fetch_html()`, `extract_game_urls_from_listing_html()`, `extract_game_urls_from_listing_html_by_date()`, `extract_game()`, `extract_game_by_id()`, `extract_games_from_listing()`, `extract_games_from_listing_with_progress()`, and `extract_games_from_listing_by_date()`.
  - This layer is responsible for fetching and orchestrating the scrape pipeline.

- src/shl/validation.py
  - Primary functions: `calculate_standings()`, `parse_overview_standings_html()`, `compare_standings()`, `build_validation_report()`, `load_or_fetch_season_validation_inputs()`, `validate_season_standings()`, and `validate_multiple_seasons()`.
  - Covers standings computation and validation against overview data.

- src/shl/compare.py
  - Primary functions: `compare_game_score_change()` and `compare_game_score_change_from_files()`.
  - Used to compare snapshots and report which team scored, along with scorer and time details.

- src/standings_cli.py
  - Primary functions: `main()`, `format_standings_row()`, `print_standings_table()`, `write_standings_csv()`, and `resolve_output_path()`.
  - Scrapes a listing page, computes standings, and optionally writes JSON/CSV output.

- src/validation_cli.py
  - Primary functions: `main()`, `resolve_output_path()`, and `resolve_input_path()`.
  - Fetches overview pages or validates calculated standings for one or many seasons.

- src/scrape_all_games_cli.py
  - Primary functions: `main()` and `resolve_output_path()`.
  - Scrapes all linked games from a listing page and saves aggregated JSON.

- src/scrape_games_by_date_cli.py
  - Primary functions: `main()` and `resolve_output_path()`.
  - Scrapes only games from a specific YYYY-MM-DD date and saves JSON.

- src/compare_scores_cli.py
  - Primary functions: `main()` and `resolve_output_path()`.
  - Compares two saved game JSON files for score-change events.

## Quick usage

Single game by id:

  /bin/python -m src.shl.api --game-id 1004357

Standings from a listing:

  /bin/python -m src.standings_cli <listing_url>

Validate one season:

  /bin/python -m src.validation_cli 18263 --validate --output validation_report_18263.json

Validate multiple seasons:

  /bin/python -m src.validation_cli --validate --season-ids 18263 17556 15977 --output batch_validation.json

Scrape games by date:

  /bin/python -m src.scrape_games_by_date_cli <schedule_url> 2025-09-16

Compare two snapshots:

  /bin/python -m src.compare_scores_cli cache/aggregated_1004357-a.json cache/aggregated_1004357-b.json

## Testing

Run the full suite:

  /bin/python -m pytest -q tests

The test coverage is now split across focused modules:

- tests/test_parsing.py
- tests/test_extraction.py
- tests/test_compare.py
- tests/test_validation.py

Current status during latest updates: all tests passing.

## Notes

- The parser is tuned for SweHockey page structure, including nested tables and subsection-based action blocks.
- UTF-8 handling is applied to preserve Swedish characters in team and player names.
