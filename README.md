# SHL 2026 Scraper and Validation Toolkit

This project scrapes SweHockey game pages, normalizes game data, computes standings, validates standings against SweHockey overview tables, and compares score changes between game snapshots.

The implementation lives under `src/`.

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

Generated files are routed to a cache directory by default.

- Default cache folder: cache/
- Relative output paths are stored under cache/
- Absolute output paths are respected as-is
- Overview validation cache files are stored as:
  - games_<season_id>.json
  - overview_<season_id>.html

The cache folder is ignored by git.

## Main modules and scripts

- src/shl/api.py
  - Public re-export surface for the toolkit. Imports and exposes everything from `parsing`, `extraction`, `validation`, and `compare`.

- src/shl/parsing.py
  - Primary functions: `parse_top_stats()`, `parse_actions()`, `parse_score_block()`, `parse_players()`, `extract_penalty_metadata()`, `find_top_stats_table()`, `find_actions_table()`, and `clean_text()`.
  - Handles the HTML parsing, normalization, and event extraction logic.

- src/shl/extraction.py
  - Primary functions: `fetch_html()`, `extract_game_urls_from_listing_html()`, `extract_game_urls_from_listing_html_by_date()`, `extract_game()`, `extract_game_by_id()`, `extract_games_from_listing()`, `extract_games_from_listing_with_progress()`, and `extract_games_from_listing_by_date()`.
  - Responsible for fetching and orchestrating the scrape pipeline.

- src/shl/validation.py
  - Primary functions: `calculate_standings()`, `parse_overview_standings_html()`, `compare_standings()`, `build_validation_report()`, `load_or_fetch_season_validation_inputs()`, `validate_season_standings()`, and `validate_multiple_seasons()`.
  - Covers standings computation and validation against overview data.

- src/shl/compare.py
  - Primary functions: `compare_game_score_change()` and `compare_game_score_change_from_files()`.
  - Used to compare snapshots and report which team scored, along with scorer and time details.

- src/cli.py
  - Unified CLI with three subcommands: `scrape`, `validate`, and `compare`.
  - Primary functions: `main()`, `cmd_scrape()`, `cmd_validate()`, `cmd_compare()`, `format_standings_row()`, `print_standings_table()`, `write_standings_csv()`, `resolve_output_path()`, and `resolve_input_path()`.

## Quick usage

Single game by id:

  python -m src.cli scrape --game-id 1004357

Scrape all games and compute standings:

  python -m src.cli scrape <listing_url>

Scrape games by date:

  python -m src.cli scrape <schedule_url> --date 2025-09-16

Validate one season:

  python -m src.cli validate 18263 --validate --output validation_report_18263.json

Validate multiple seasons:

  python -m src.cli validate --validate --season-ids 18263 17556 15977 --output batch_validation.json

Compare two snapshots:

  python -m src.cli compare cache/aggregated_1004357-a.json cache/aggregated_1004357-b.json

## Testing

Unit tests run without network access. Integration tests make real network calls and are skipped by default.

Run unit tests:

  python -m pytest tests/unit/

Run integration tests:

  python -m pytest tests/integration/

Run everything:

  python -m pytest tests/ --integration

Test files:

- tests/unit/test_parsing.py
- tests/unit/test_extraction.py
- tests/unit/test_compare.py
- tests/unit/test_validation.py
- tests/unit/test_cli.py
- tests/integration/test_integration.py

## Notes

- The parser is tuned for SweHockey page structure, including nested tables and subsection-based action blocks.
- UTF-8 handling is applied to preserve Swedish characters in team and player names.
