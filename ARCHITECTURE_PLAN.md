# SHL Poller + DB + REST API Design Plan

This document describes a smart implementation plan for the requirements in [REQ.md](REQ.md):
- pollers fetch data from the internet and store it in DB
- REST API serves persisted data through get methods

## Goals

1. Reliable polling with adaptive cadence.
2. Idempotent DB writes and change detection.
3. Fast read APIs backed only by persisted state.
4. Minimal upstream load with cache-first behavior.
5. Clear separation: fetch writes, get reads.

## High-Level Architecture

1. Polling Worker Service
- Runs schedule, game, and standings pollers.
- Calls fetch methods only.

2. Storage Layer
- SQLite first (existing [src/shl/store.py](src/shl/store.py)).
- Schema designed for easy migration to Postgres.

3. REST API Service
- Exposes read-only endpoints over persisted data.
- Calls get methods only.

4. Notification/Outbox Worker (optional phase 2)
- Reads domain events from DB and publishes notifications.

## Pollers

### 1) Live Games Poller

Targets: active season game IDs.

State-based cadence:
1. Not started: every 5 to 15 minutes.
2. In progress: every 15 to 45 seconds.
3. Final: one or two confirmation polls, then stop/reduce.

Method used:
- [src/shl/game.py](src/shl/game.py) fetch_game(game_id, db_dir, force_reparse=False)

Change detection:
- compare latest stored snapshot vs new snapshot via score/actions.
- if score changed, enqueue domain event.

### 2) Schedule Poller

Targets: season schedule IDs.

Cadence:
1. Normal: every 15 to 60 minutes.
2. Near game windows: every 5 to 15 minutes.

Method used:
- [src/shl/schedule.py](src/shl/schedule.py) fetch_schedule(season_id, db_dir, force_reparse=False)

Smartness:
- cache-first by default.
- force_reparse for manual refresh.

### 3) Standings Poller

Preferred trigger:
1. Event-driven after game status/score transitions.

Fallback cadence:
1. Every 5 to 15 minutes.

Method used:
- [src/shl/standings.py](src/shl/standings.py) fetch_table(season_id, db_dir, force_reparse=False)

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
- target_type (game, schedule, standings)
- target_key (game_id or season_id)
- enabled

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
- event_type (score_changed, game_final, schedule_changed, standings_changed)
- aggregate_key (game_id or season_id)
- payload_json
- created_at
- processed_at (nullable)

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
- append domain_events row
- compute next_poll_at by new state

6. Persist poll metrics/status.

## Read/API Pipeline

REST API reads from DB only. No live scrape in request path.

Suggested endpoints:
1. GET /seasons/{season_id}/schedule
2. GET /seasons/{season_id}/games?date=YYYY-MM-DD
3. GET /games/{game_id}
4. GET /seasons/{season_id}/standings
5. GET /events/recent

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

## Observability

Track metrics:
1. poll_success_count / poll_error_count
2. poll_duration_ms
3. stale_targets_count
4. score_change_events_count
5. cache_hit_ratio for fetch methods

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

Phase 2:
1. add REST API server endpoints over get methods
2. add freshness metadata in responses

Phase 3:
1. add outbox worker and notifications
2. add admin force-reparse endpoints

Phase 4:
1. harden observability and failure recovery
2. add integration tests for poll lifecycle and event generation

## Open Decisions

1. SQLite vs Postgres timeline.
2. Poller runtime model (single process, cron, or queue worker).
3. Notification channels and dedupe keys.
4. Retention policy for snapshot/history tables.
