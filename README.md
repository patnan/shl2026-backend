# SHL 2026 Scraper Toolkit

This project scrapes SweHockey game and schedule pages, stores normalized snapshots in SQLite, computes standings, and compares score changes between snapshots.

Code root: [src](src)

**Getting started?** See [GETTING_STARTED.md](GETTING_STARTED.md).

**API contract:** See [openapi.yaml](openapi.yaml) — the single source of truth for all endpoints and data types. See [OPENAPI.md](OPENAPI.md) for how to generate clients from it.

## Implemented capabilities

- Parse a single game page into typed dataclasses.
- Parse season schedule pages into typed schedule entries.
- Persist games, schedules, standings, player stats, goalie stats, and rosters in SQLite.
- Compute standings from played games (effectively live during game days — recalculated every 30s from schedule data). Pre-season: returns all teams at rank 1, sorted alphabetically.
- Standings movement tracking (position change compared to previous snapshot).
- Fetch standings from SweHockey overview pages.
- Scrape player scoring leaders from SweHockey.
- Scrape goalie stats (save %, GAA, wins) from SweHockey.
- Scrape team rosters and per-player game stats (GP, G, A, TP, PIM, +/-, GWG, PPG, SHG, SOG, SG%, FO) from SweHockey.
- Scrape team abbreviations dynamically from SweHockey roster page navigation.
- Enrich player data with portraits and shl.se UUIDs via shl.se API.
- Compare two game snapshots and detect scoring changes.
- Scrape today's live/upcoming games from SweHockey Live page (polled every 30s).
- Push notifications for live score changes via FCM.
- CLI support for scraping, overview validation preview, snapshot comparison, poller seeding/worker runs, and REST API serving.

## Data models

Dataclasses are defined in [src/shl/models.py](src/shl/models.py).

Model documentation:
- [MODELS.md](MODELS.md)

Architecture and implementation planning:
- [ARCHITECTURE_PLAN.md](ARCHITECTURE_PLAN.md)

Key model types:
- Game
- ScheduleEntry
- StandingsRow
- PlayerStat
- GoalieStat
- RosterEntry
- ShlSeTeam
- ShlSePlayer
- ScoreChangeResult

## Project modules

- [src/shl/api.py](src/shl/api.py)
  Public API re-export surface.

- [src/shl/game.py](src/shl/game.py)
  Game fetch flow and score-change comparison.

- [src/shl/schedule.py](src/shl/schedule.py)
  Schedule fetch/read methods and standings-from-saved-games flow.

- [src/shl/standings.py](src/shl/standings.py)
  Standings parser and standings calculator.

- [src/shl/stats.py](src/shl/stats.py)
  Player stats, goalie stats, and roster fetch/get functions.

- [src/shl/store.py](src/shl/store.py)
  SQLite persistence for games, schedule, standings, player stats, goalie stats, and rosters.

- [src/shl/helpers/extraction.py](src/shl/helpers/extraction.py)
  HTML fetch and extraction orchestration helpers.

- [src/shl/helpers/parsing.py](src/shl/helpers/parsing.py)
  SweHockey-specific parsing logic for top stats and actions.

- [src/shl/helpers/stats_parsing.py](src/shl/helpers/stats_parsing.py)
  Parsers for player stats, goalie stats, and roster HTML pages.

- [src/shl/shl_se.py](src/shl/shl_se.py)
  SHL.se API client and SweHockey ↔ shl.se team/player mapping (logos, portraits).

- [src/cli.py](src/cli.py)
  CLI entrypoint with scrape, validate, compare, serve, poller-seed, and poller-run commands.

## Persistence and cache

- Default cache directory: cache
- SQLite database path: cache/cache.db
- CLI writes relative output paths under cache unless absolute paths are provided.

Database tables created automatically:
- games
- schedule
- standings
- player_stats
- goalie_stats
- rosters
- poll_targets / poll_state
- domain_events
- devices

## CLI usage

Single game by id:

```bash
python -m src.cli scrape --game-id 1004840
```

Scrape all games from a schedule/listing URL and compute standings:

```bash
python -m src.cli scrape https://stats.swehockey.se/ScheduleAndResults/Schedule/18263
```

Scrape games for a specific date:

```bash
python -m src.cli scrape https://stats.swehockey.se/ScheduleAndResults/Schedule/18263 --date 2025-09-16
```

Fetch and preview overview HTML for one season:

```bash
python -m src.cli validate 18263 --output overview_18263.html
```

Compare two snapshot files:

```bash
python -m src.cli compare cache/aggregated_1004357-a.json cache/aggregated_1004357-b.json
```

Run REST API (Swagger at /docs):

```bash
python -m src.cli serve --host 127.0.0.1 --port 8000
```

Seed poll targets for a season:

```bash
python -m src.cli poller-seed 18263
```

Seed only schedule and standings targets (skip game targets):

```bash
python -m src.cli poller-seed 18263 --skip-games
```

Run poller worker loop:

```bash
python -m src.cli poller-run --tick-interval 5 --max-ticks 10
```

Run notification worker (push notifications):

```bash
python -m src.cli notifier-run --tick-interval 5
```

Typical first run (seed -> poll -> API):

```bash
# 1) Seed targets for one season
python -m src.cli poller-seed 18263

# 2) Run a short worker cycle to populate cache/db
python -m src.cli poller-run --tick-interval 1 --max-ticks 5

# 3) Start API server
python -m src.cli serve --host 127.0.0.1 --port 8000

# 4) In another terminal, query persisted data
curl "http://127.0.0.1:8000/seasons/18263/standings"
curl "http://127.0.0.1:8000/seasons/18263/games?date=2025-09-16"
curl "http://127.0.0.1:8000/seasons/18263/games/today"
curl "http://127.0.0.1:8000/seasons/18263/games/live"
curl "http://127.0.0.1:8000/seasons/18263/rounds"
curl "http://127.0.0.1:8000/seasons/18263/rounds/played"
curl "http://127.0.0.1:8000/seasons/18263/rounds/next"
curl "http://127.0.0.1:8000/seasons/18263/players"
curl "http://127.0.0.1:8000/seasons/18263/players?team=SKE"
curl "http://127.0.0.1:8000/seasons/18263/goalies"
curl "http://127.0.0.1:8000/seasons/18263/players/Bryn%C3%A4s%20IF"
curl "http://127.0.0.1:8000/seasons/18263/players/Bryn%C3%A4s%20IF/3"
curl "http://127.0.0.1:8000/seasons/18263/players/Bryn%C3%A4s%20IF/3/stats"
curl "http://127.0.0.1:8000/games/1004308"
curl "http://127.0.0.1:8000/portraits/SAIK_24.png"
```

## Start scripts

Convenience scripts for local development (require `.venv`):

```bash
# Start API server:
./start_api.sh

# Start poller (seeds + runs):
SEASON_ID=18263 ./start_poller.sh

# Start notification worker:
./start_notifier.sh
```

## Python API usage

Import surface:

```python
from src.shl.api import (
    fetch_game,
    fetch_schedule,
    fetch_table,
    get_schedule,
    get_games_for_date,
    get_all_played_games,
    get_standings,
    compare_game_score_change,
)
```

Compatibility aliases also exist:
- fetchGame
- fetchSchedule
- fetchTable
- getSchedule
- getGamesForDate
- getAllPlayedGames
- getStandings

## Testing

Run unit tests:

```bash
python -m pytest tests/unit/
```

Run integration tests:

```bash
python -m pytest tests/integration/
```

Run all tests:

```bash
python -m pytest tests/
```

## Container usage

Build and run with Docker:

```bash
docker build -t shl-api .
docker run --rm -p 8000:8000 -v "$(pwd)/cache:/app/cache" shl-api
```

Run with Docker Compose (includes restart policy, healthcheck, persistent cache mapping, and basic resource limits):

```bash
docker compose up -d --build
```

Compose services:
- `shl-api` — REST API server (port 8000, 1GB memory, 2 CPUs)
- `shl-poller` — Poller worker, ticks every 30s (512MB memory, 1 CPU)
- `shl-notifier` — Notification worker, checks events every 5s (256MB memory, 0.5 CPU)

Inspect health status:

```bash
docker compose ps
```

Stop compose service:

```bash
docker compose down
```

## Push notifications (Firebase Cloud Messaging)

The notification worker sends push notifications to registered Android/web devices when goals are scored or games end.

### Setup

1. Create a Firebase project at https://console.firebase.google.com
2. Go to Project Settings → Service Accounts → Generate New Private Key
3. Save the JSON file as `firebase-credentials.json` in the project root

### Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Firebase service account JSON key | Required for FCM |
| `SHL_FCM_DRY_RUN` | Set to `"1"` to log notifications without sending | Off |
| `SHL_CORS_ORIGINS` | Comma-separated allowed CORS origins | `*` |
| `SHL_RATE_LIMIT_PER_MINUTE` | API rate limit per IP per minute | `60` |
| `SHL_LOG_LEVEL` | Log level: DEBUG, INFO, WARNING, ERROR | `INFO` |
| `SHL_LOG_FORMAT` | Log format: `json` (structured) or `text` (human-readable) | `json` |

### Device registration

Your app registers for notifications on startup:

```bash
# Register
curl -X POST http://127.0.0.1:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"fcm_token": "<FCM_TOKEN>", "platform": "android"}'

# Unregister
curl -X DELETE http://127.0.0.1:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"fcm_token": "<FCM_TOKEN>"}'
```

### Running the notification worker

```bash
# Local testing (dry-run, logs only):
SHL_FCM_DRY_RUN=1 python -m src.cli notifier-run

# Production:
python -m src.cli notifier-run --tick-interval 5
```

With Docker Compose, the `shl-notifier` service starts automatically and reads `firebase-credentials.json` from the project root.

### Notification types

| Event | Title | Body example |
|-------|-------|--------------|
| Goal scored | ⚽ Mål! 2-1 | Brynäs IF Victor Söderström (45:23) |
| Game ended | 🏁 Slutsignal | Slutresultat: 3-2 |

## Notes

- Parsing is tuned to SweHockey page structure, including nested tables.
- UTF-8 decoding is explicitly set to preserve Swedish characters.
