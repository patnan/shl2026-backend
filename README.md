# SHL 2026 Scraper and Validation Toolkit

This project scrapes SweHockey game pages, normalizes game data, computes standings, validates standings against SweHockey overview tables, and compares score changes between game snapshots.

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

## Main scripts

- extract_top_stats.py
  - Library functions for scraping, parsing, standings, validation, and comparisons.
  - CLI supports:
    - positional URL
    - --game-id for direct extraction by game id

- main.py
  - Scrape all games from a listing page and compute standings.
  - Optional raw games JSON and CSV export.
  - Uses --cache-dir (default cache).

- overview.py
  - Fetch overview pages or validate calculated standings.
  - Supports single-season and multi-season validation.
  - Uses --cache-dir (default cache).

- test_all_games.py
  - Scrape all games from a listing URL and save aggregated JSON.

- test_games_by_date.py
  - Scrape only games for a given YYYY-MM-DD date and save JSON.

- test_compare_game_scores.py
  - Compare two saved game JSON files for score change events.

## Quick usage

Single game by id:

  /bin/python extract_top_stats.py --game-id 1004357

Standings from a listing:

  /bin/python main.py <listing_url>

Validate one season:

  /bin/python overview.py 18263 --validate --output validation_report_18263.json

Validate multiple seasons:

  /bin/python overview.py --validate --season-ids 18263 17556 15977 --output batch_validation.json

Scrape games by date:

  /bin/python test_games_by_date.py <schedule_url> 2025-09-16

Compare two snapshots:

  /bin/python test_compare_game_scores.py cache/aggregated_1004357-a.json cache/aggregated_1004357-b.json

## Testing

Run the full test module:

  /bin/python -m pytest -q tests/test_extract_top_stats.py

Current status during latest updates: all tests passing.

## Notes

- The parser is tuned for SweHockey page structure, including nested tables and subsection-based action blocks.
- UTF-8 handling is applied to preserve Swedish characters in team and player names.
