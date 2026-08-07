# Getting Started

## Prerequisites

- Python 3.12+
- (Optional) Docker + Docker Compose for containerized deployment

## Install (local)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Season ID

The app operates per season. Everything is scoped to a SweHockey tournament ID:

| Season | ID |
|--------|-----|
| SHL 2025/2026 | `18263` |
| SHL 2026/2027 | `20961` |

Set via the `SEASON_IDS` environment variable (comma-separated). Default: `18263`.
For past seasons (fetched once), use `PAST_SEASON_IDS`.

---

## Option 1: Local (start scripts)

```bash
# Terminal 1 — Poller (seeds targets + starts polling SweHockey)
SEASON_IDS=18263 ./start_poller.sh

# Terminal 2 — API server (http://127.0.0.1:8000)
./start_api.sh

# Terminal 3 (optional) — Notification worker
SHL_FCM_DRY_RUN=1 ./start_notifier.sh
```

The poller will immediately fetch the schedule, standings, player stats, goalie stats, and rosters. After a few seconds, the API has data to serve.

### Verify

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/seasons/18263/standings
curl http://127.0.0.1:8000/seasons/18263/players
curl http://127.0.0.1:8000/seasons/18263/goalies
curl http://127.0.0.1:8000/seasons/18263/rosters?team=Skellefteå%20AIK
```

API docs (Swagger UI): http://127.0.0.1:8000/docs

---

## Option 2: Docker Compose

```bash
# Set season (or create a .env file)
echo "SEASON_IDS=18263" > .env

# Build and start all services
docker compose up -d --build
```

This starts three services:

| Service | Role | Resources |
|---------|------|-----------|
| `shl-api` | REST API on port 8000 | 1GB / 2 CPUs |
| `shl-poller` | Polls SweHockey every 30s | 512MB / 1 CPU |
| `shl-notifier` | Sends push notifications | 256MB / 0.5 CPU |

### Verify

```bash
docker compose ps          # Check health
curl http://localhost:8000/health
```

### Stop

```bash
docker compose down
```

---

## Option 3: Manual CLI

```bash
# 1) Seed poll targets for a season
python -m src.cli poller-seed 18263

# 2) Run poller (fetches data from SweHockey)
python -m src.cli poller-run --tick-interval 30 --max-ticks 5

# 3) Start API
python -m src.cli serve --host 127.0.0.1 --port 8000
```

---

## Switching seasons

When a new season starts:

1. Find the new season ID on stats.swehockey.se (it's in the URL)
2. Change `SEASON_IDS` and restart:
   ```bash
   SEASON_IDS=20961 ./start_poller.sh
   ```
   Or update `.env` and `docker compose up -d`.

The seed is idempotent — it creates new targets without affecting existing data.

---

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SEASON_ID` | SweHockey tournament ID | `18263` |
| `TICK_INTERVAL` | Poller base tick interval (seconds) | `30` |
| `HOST` | API bind address | `127.0.0.1` |
| `PORT` | API port | `8000` |
| `SHL_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `SHL_LOG_FORMAT` | `json` (structured) or `text` (human-readable) | `json` |
| `SHL_CORS_ORIGINS` | Allowed CORS origins | `*` |
| `SHL_RATE_LIMIT_PER_MINUTE` | API rate limit per IP | `60` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Firebase service account JSON path | Required for push notifications |
| `SHL_FCM_DRY_RUN` | `"1"` to log notifications without sending | Off |

---

## Push notifications (optional)

To enable goal/game-end notifications:

1. Create a Firebase project at https://console.firebase.google.com
2. Go to Project Settings → Service Accounts → Generate New Private Key
3. Save as `firebase-credentials.json` in the project root
4. Start the notifier:
   ```bash
   ./start_notifier.sh
   ```

Register a device:
```bash
curl -X POST http://127.0.0.1:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"fcm_token": "<FCM_TOKEN>", "platform": "android"}'
```

---

## What the poller fetches

On first seed, the poller creates 6 targets per season:

| Target | SweHockey source | Polling cadence |
|--------|-----------------|-----------------|
| Schedule | `/ScheduleAndResults/Schedule/{id}` | 30s (game days), 2h (off days) |
| Standings | Computed from schedule | Every schedule tick |
| Player stats | `/Players/Statistics/ScoringLeaders/{id}` | Every 2 hours |
| Goalie stats | `/Players/Statistics/LeadingGoaliesSVS/{id}` | Every 2 hours |
| Rosters | `/Teams/Info/TeamRoster/{id}` | Every 24 hours |
| Team info | `/Teams/Info/TeamRoster/{id}` (abbreviations) | Every 24 hours |

---

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /seasons/{id}/schedule` | Full season schedule |
| `GET /seasons/{id}/games?date=YYYY-MM-DD` | Games by date |
| `GET /seasons/{id}/games/today` | Today's upcoming games |
| `GET /seasons/{id}/rounds` | Schedule grouped by round |
| `GET /seasons/{id}/rounds/played` | Completed rounds |
| `GET /seasons/{id}/rounds/next` | Next unplayed round |
| `GET /seasons/{id}/standings` | Standings (live during games) |
| `GET /seasons/{id}/players` | Scoring leaders |
| `GET /seasons/{id}/players?team=SKE` | Scoring leaders filtered by team |
| `GET /seasons/{id}/goalies` | Goalie stats |
| `GET /seasons/{id}/goalies?team=FRÖ` | Goalie stats filtered by team |
| `GET /seasons/{id}/rosters` | All team rosters |
| `GET /seasons/{id}/rosters?team=Brynäs IF` | Single team roster |
| `GET /seasons/{id}/teams` | Teams with official abbreviations |
| `GET /games/{game_id}` | Game detail (score, events, team stats) |
| `POST /devices` | Register device for push notifications |
| `DELETE /devices` | Unregister device |

All data endpoints return a `{"data": [...], "meta": {...}}` envelope with freshness metadata.
