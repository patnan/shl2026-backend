# SHL Poller + DB + REST API Design Plan

This document describes a smart implementation plan for the requirements in [REQ.md](REQ.md):
- pollers fetch data from the internet and store it in DB
- REST API serves persisted data through get methods
- notification worker pushes real-time alerts on score/state changes

## Goals

1. Reliable polling with adaptive cadence.
2. Idempotent DB writes and change detection.
3. Fast read APIs backed only by persisted state.
4. Minimal upstream load with cache-first behavior.
5. Clear separation: fetch writes, get reads.
6. Real-time push notifications for live game events.

## High-Level Architecture

1. Polling Worker Service
- Runs schedule, game, and standings pollers.
- Calls fetch methods only.
- Emits domain events on detected changes.

2. Storage Layer
- SQLite with WAL mode ([src/shl/store.py](src/shl/store.py)).
- Store class with schema init once, thread-local connections, batch game loading.
- Schema designed for easy migration to Postgres.

3. REST API Service
- Exposes read-only endpoints over persisted data.
- Calls get methods only.
- CORS middleware with configurable allowed origins.
- In-memory per-IP rate limiting.

4. Notification Worker
- Reads `score_changed` and `game_state_changed` domain events from outbox.
- Sends Firebase Cloud Messaging push notifications to registered devices.
- Implemented in [src/shl/notifier.py](src/shl/notifier.py).

## Pollers

### Architecture: Schedule-Driven Polling

The schedule poller is the primary driver for all change detection. The schedule page is polled at dynamic intervals and used to detect score changes across all games simultaneously. No individual game pages are fetched during polling — change events are emitted directly from schedule data.

### 1) Schedule Poller (Primary)

Targets: season schedule IDs.

Dynamic cadence (adapts to game activity):
- Live games today: every **30 seconds**
- Game day, games not yet started: every **5 minutes**
- No games today: every **15 minutes**

On each tick:
1. Fetch fresh schedule page.
2. Compare previous vs new schedule entry scores.
3. For each game with a score change, emit `score_changed` domain event (teams, score, overtime — no game detail fetch needed).
4. On initial seed (no previous schedule exists), skip event emission to avoid flooding with historical data.
5. Recalculate standings from updated schedule.
6. If standings changed, emit `standings_changed` domain event.

Method used:
- [src/shl/schedule.py](src/shl/schedule.py) fetch_schedule(season_id, db_dir, force_reparse=True)
- [src/shl/schedule.py](src/shl/schedule.py) get_standings(season_id, db_dir) — computed from schedule

### 2) Game Targets

Game targets exist in the database but are **not actively polled**. The `GET /games/{game_id}` endpoint always fetches fresh data from SweHockey on each request, ensuring live game details are current. The result is persisted as a side effect (used by standings calculation).

### 3) Standings

Standings are **computed from schedule data** (not a separate poller). Recalculated on every schedule tick and compared with the previous value. No separate standings polling needed.

**Pre-season:** When no games have been played yet, standings returns all teams from the schedule at rank 1, sorted alphabetically by team name. All stats are zero.

Because SweHockey updates the schedule page with in-progress scores during live games, and the poller fetches every 30s during game windows, standings are **effectively live** — they reflect goals within ~30 seconds of being scored. No separate "live standings" endpoint is needed.

### 4) Overview Standings Poller (Legacy/Validation)

Fetches the SweHockey overview page standings table. Used for validation against the computed standings.

Cadence: every 5 minutes.

Method used:
- [src/shl/standings.py](src/shl/standings.py) fetch_table(season_id, db_dir, force_reparse=False)

### 5) Player Stats, Goalie Stats, Rosters

Scraped from SweHockey stats pages. Low-frequency polling since this data changes infrequently.

| Target type | Source URL | Cadence |
|---|---|---|
| `player_stats` | `/Players/Statistics/ScoringLeaders/{season_id}` | Every 2 hours |
| `goalie_stats` | `/Players/Statistics/LeadingGoaliesSVS/{season_id}` | Every 2 hours |
| `rosters` | `/Teams/Info/TeamRoster/{season_id}` | Every 24 hours |
| `team_info` | `/Teams/Info/TeamRoster/{season_id}` (nav anchors) | Every 24 hours |

Methods:
- [src/shl/stats.py](src/shl/stats.py) fetch_player_stats, fetch_goalie_stats, fetch_rosters, fetch_team_info

### 6) Live Game Scores

The SweHockey Live page at `/ScheduleAndResults/Live/{season_id}` lists today's upcoming and in-progress games. A parser (`parse_live_games_html`) extracts home team, away team, start time, and venue from the responsive HTML. Data is stored in the `live_games` table and served via `GET /seasons/{season_id}/games/live`.

| Target type | Source URL | Cadence |
|---|---|---|
| `live_games` | `/ScheduleAndResults/Live/{season_id}` | Every 30 seconds |

The poller keeps the live games cache fresh every 30 seconds. If the cache is empty (first request before poller has run), the API endpoint fetches on demand and caches the result.

The live games parser extracts: home/away teams, score, period scores, game_url (from score link), venue, start time, game status (e.g. "2nd period"), game clock (e.g. "01:49"), and current period. It also extracts the "Last update" timestamp from the SweHockey page header, which indicates when their data was last refreshed. This is stored in the `page_last_update` column and exposed in the API meta. The game page parser also works during live games (no longer requires "Final Score" in the HTML).

The live page has two sections: "Upcoming / In Progress" (active/upcoming games) and "Final Score" (finished games). Both are parsed. When a game transitions to a finished state ("Game Finished" or "Final Score"), the poller emits a `game_state_changed` domain event which triggers a push notification.

## DB Design

Use current tables as base and extend.

### Current-state tables

1. games_current
- game_id (PK)
- payload_json
- payload_hash
- state (not_started, live, final)
- fetched_at
- updated_at

2. schedule_current
- season_id (PK)
- payload_json
- payload_hash
- fetched_at
- updated_at

3. standings_current
- season_id (PK)
- payload_json
- payload_hash
- fetched_at
- updated_at

### History tables

1. game_snapshots
- id (PK)
- game_id
- payload_json
- payload_hash
- fetched_at

2. schedule_snapshots
- id (PK)
- season_id
- payload_json
- payload_hash
- fetched_at

3. standings_snapshots
- id (PK)
- season_id
- payload_json
- payload_hash
- fetched_at

### Poll control tables

1. poll_targets
- id (PK)
- target_type (game, schedule, standings, live_games, player_stats, goalie_stats, rosters, team_info)
- target_key (game_id or season_id)
- enabled
- one_shot (if true, target is disabled after first successful poll — used for past seasons via `--once`)

2. poll_state
- target_id (FK)
- last_success_at
- last_error_at
- error_count
- next_poll_at
- last_duration_ms

### Outbox/events table

1. domain_events
- id (PK)
- event_type (score_changed, game_state_changed, schedule_changed, standings_changed)
- aggregate_key (game_id or season_id)
- payload_json
- created_at
- processed_at (nullable)

### Device registration table

1. devices
- fcm_token (PK)
- platform (android, web, ios)
- registered_at

## Write Pipeline

For each due poll target:

1. Read poll target + state.
2. Execute fetch method.
3. Normalize and hash payload.
4. If unchanged:
- update fetched_at/last_seen
- compute next_poll_at by cadence rules

5. If changed:
- upsert current-state table
- append snapshot table row
- append domain_events row (score_changed / game_state_changed)
- compute next_poll_at by new state

6. Persist poll metrics/status.

## Read/API Pipeline

REST API reads from DB only. No live scrape in request path.

Endpoints:
1. GET / (endpoint index with descriptions)
2. GET /health
3. GET /seasons/{season_id}/schedule
4. GET /seasons/{season_id}/games (all, or ?date=YYYY-MM-DD to filter)
5. GET /seasons/{season_id}/games/played
6. GET /seasons/{season_id}/games/today
7. GET /seasons/{season_id}/standings
8. GET /seasons/{season_id}/rounds
9. GET /seasons/{season_id}/rounds/played
10. GET /seasons/{season_id}/rounds/next
11. GET /seasons/{season_id}/teams
12. GET /games/{game_id}
13. POST /devices
14. DELETE /devices

Response metadata:
1. fetched_at
2. updated_at
3. source freshness indicators

## Method Mapping

Fetch (write path):
1. fetch_game
2. fetch_schedule
3. fetch_table

Get (read path):
1. get_schedule
2. get_games_for_date
3. get_all_played_games
4. get_standings
5. get_rounds
6. get_played_rounds
7. get_next_round
8. get_todays_games

Device registration:
1. register_device
2. unregister_device
3. list_device_tokens

## Notification Pipeline

1. Notification worker polls domain_events outbox for unprocessed events.
2. Filters for `score_changed` and `game_state_changed` event types.
3. Builds notification payload (title, body, data).
4. Sends FCM multicast to all registered device tokens.
5. Marks events as processed.

Notification types:
- Goal scored: "⚽ Mål! {score}" with scorer details.
- Game ended: "🏁 Slutsignal" with final result.

## Deployment

Docker Compose runs 3 services:
1. `shl-api` — REST API server (port 8000, 1GB memory, 2 CPUs).
2. `shl-poller` — Poller worker, ticks every 30 seconds (512MB memory, 1 CPU).
3. `shl-notifier` — Notification worker, checks events every 5 seconds (256MB memory, 0.5 CPU).

All services share a volume-mounted SQLite database in `cache/`.

## Reliability and Safety

1. Idempotent upserts everywhere.
2. Retry with exponential backoff + jitter.
3. Circuit breaker on repeated upstream failures.
4. Outbox pattern for notifications.
5. At-least-once delivery with consumer dedupe.

## Performance Strategy

1. Smart cache-first fetch defaults (already implemented).
2. force_reparse only for admin/manual refresh.
3. Adaptive poll intervals by game state.
4. Persistent integration cache for faster test reruns.
5. WAL mode for concurrent read/write access.
6. Batch game loading for standings computation.

## Observability

Track metrics:
1. poll_success_count / poll_error_count
2. poll_duration_ms
3. stale_targets_count
4. score_change_events_count
5. cache_hit_ratio for fetch methods
6. notification_sent_count / notification_error_count

Structured logs include:
1. poller name
2. target id
3. cache hit/miss
4. duration
5. change detected true/false

## Suggested Implementation Phases

Phase 1:
1. [x] finalize DB schema changes
2. [x] add poll_state + target scheduler loop
3. [x] keep single process worker

Phase 1 Step 1 completion notes:
1. Added schema objects in [src/shl/store.py](src/shl/store.py): poll_targets, poll_state, domain_events.
2. Added supporting indexes for enabled targets, next poll time, and outbox processing.
3. Kept existing games/schedule/standings tables intact for backward compatibility.

Phase 1 Step 2 completion notes:
1. Added poller/store helper APIs in [src/shl/store.py](src/shl/store.py) for upserting poll targets, listing due targets, updating poll success/error state, and processing outbox events.
2. Added scheduler tick execution in [src/shl/poller.py](src/shl/poller.py) with target dispatch (game/schedule/standings), success/error handling, and domain event writes.
3. Added unit coverage in [tests/unit/test_poller.py](tests/unit/test_poller.py).

Phase 1 Step 3 completion notes:
1. Added single-process worker loop in [src/shl/poller.py](src/shl/poller.py) via run_poller_worker.
2. Worker supports bounded execution via max_ticks and tracks ok/error result counts.
3. Added loop and validation tests in [tests/unit/test_poller.py](tests/unit/test_poller.py).
4. Added seeding workflow in [src/shl/poller.py](src/shl/poller.py) via seed_season_targets and CLI commands in [src/cli.py](src/cli.py): poller-seed and poller-run.
5. Added `--once` flag for seeding past seasons: creates one_shot targets (all except live_games), which the poller auto-disables after first successful execution.

Phase 2:
1. [x] add REST API server endpoints over get methods
2. [x] add freshness metadata in responses

Phase 2 Step 1 completion notes:
1. Added FastAPI app factory in [src/shl/rest_api.py](src/shl/rest_api.py) with endpoints:
	- /health
	- /seasons/{season_id}/schedule
	- /seasons/{season_id}/games (all, or ?date=YYYY-MM-DD)
	- /seasons/{season_id}/games/played
	- /seasons/{season_id}/standings
2. Added CLI serve command in [src/cli.py](src/cli.py) to run API via uvicorn.
3. Added API tests in [tests/unit/test_rest_api.py](tests/unit/test_rest_api.py).

Phase 2 Step 2 completion notes:
1. Added storage freshness helpers in [src/shl/store.py](src/shl/store.py): schedule/standings/game fetched-at accessors and game freshness summary.
2. Extended API metadata in [src/shl/rest_api.py](src/shl/rest_api.py) with source freshness fields for schedule, played games, date-filtered games, and computed standings inputs.
3. Expanded API tests in [tests/unit/test_rest_api.py](tests/unit/test_rest_api.py) to validate freshness metadata fields.

Phase 3:
1. [x] add outbox worker and notifications
2. [x] add device registration endpoints

Phase 3 completion notes:
1. Implemented notification worker in [src/shl/notifier.py](src/shl/notifier.py) reading `score_changed` and `game_state_changed` events from the domain_events outbox.
2. Sends Firebase Cloud Messaging push notifications via firebase-admin to all registered devices.
3. Added device registration store methods: register_device, unregister_device, list_device_tokens in [src/shl/store.py](src/shl/store.py).
4. Added POST /devices and DELETE /devices REST endpoints in [src/shl/rest_api.py](src/shl/rest_api.py).
5. Added CORS middleware with configurable origins (SHL_CORS_ORIGINS env var).
6. Added in-memory per-IP rate limiting (SHL_RATE_LIMIT_PER_MINUTE env var).
7. Added CLI notifier-run command in [src/cli.py](src/cli.py).
8. Smart game polling: poller checks schedule date/time and only polls games within a 4-hour active window.
9. Poller emits `score_changed` and `game_state_changed` domain events by comparing previous/current game snapshot.
10. Store refactored to Store class with WAL mode, schema init once, thread-local connections, and batch game loading.

Phase 4:
1. [x] harden observability and failure recovery
2. [x] add integration tests for poll lifecycle and event generation

Phase 4 Step 1 completion notes:
1. Enhanced poll failure recovery in [src/shl/poller.py](src/shl/poller.py) with jittered exponential backoff and a circuit-breaker cooldown mode after repeated target failures.
2. Added structured poller observability logs in [src/shl/poller.py](src/shl/poller.py) for per-target results, per-tick summaries, and worker summaries.
3. Extended worker summary metrics in [src/shl/poller.py](src/shl/poller.py) to include stale target counts, duration aggregates, total processed results, and worker start/finish timestamps.
4. Added/updated unit coverage in [tests/unit/test_poller.py](tests/unit/test_poller.py) for recovery mode fields, worker metric summaries, and circuit-breaker backoff behavior.

Phase 4 Step 2 completion notes:
1. Added poll lifecycle integration coverage in [tests/integration/test_poller_lifecycle.py](tests/integration/test_poller_lifecycle.py).
2. Added seed -> due-target selection -> tick execution verification with persisted poll_state updates and poll_completed event writes.
3. Added failed tick verification for poll_failed events including recovery_mode, retry_in_seconds, and error_count payload/state fields.
4. Added outbox delivery lifecycle integration tests verifying notification worker processes domain events correctly.

## Open Decisions

1. SQLite vs Postgres timeline — currently SQLite with WAL mode; migrate when concurrent write pressure requires it.
2. Retention policy for snapshot/history tables — no automatic pruning yet.
3. Admin force-reparse endpoints — not yet exposed via REST API.
