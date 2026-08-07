# Requirements

This document defines the service requirements for scraping SweHockey data, storing it in a local database, and exposing API methods to read persisted data.

Implementation language: Python.

## Goals

- fetch methods: pull external data and persist it in the database.
- get methods: read persisted data and return typed objects.
- compare methods: detect score changes between snapshots and support notifications.
- notification worker: push real-time alerts on game events via Firebase Cloud Messaging.

## Runtime architecture

- Poller 1: live games.
  Smart polling: only polls games within a 4-hour active window around scheduled start time.
  Active game cadence: every 30 seconds.
  Emits `score_changed` and `game_state_changed` domain events by comparing previous/current game snapshot.
- Poller 2: schedule updates.
- Poller 3: standings refresh.
  Can be event-driven after game/score changes, or periodic.
- REST server: exposes read APIs based on get methods. Includes CORS middleware and in-memory rate limiting.
- Notification worker: reads domain events from outbox, sends FCM push notifications to registered devices.

## Data classes

Domain dataclasses are defined in [src/shl/models.py](src/shl/models.py) and documented in [MODELS.md](MODELS.md).

Primary return dataclasses used by service methods:
- Game
- ScheduleEntry
- StandingsRow
- ScoreChangeResult

## Service method contracts

The code currently exposes snake_case methods, with camelCase aliases for compatibility.

### Fetch game data

Source URL pattern:
https://stats.swehockey.se/Game/Events/{game_id}

File: [src/shl/game.py](src/shl/game.py)

Method:
- fetch_game(game_id: int, db_dir: Path) -> Game
- alias: fetchGame

Dataclass contracts:

```python
@dataclass(frozen=True)
class FetchGameArgs:
    game_id: int
    db_dir: Path

@dataclass(frozen=True)
class FetchGameResult:
    game: Game
```

Behavior:
- Scrape a single game.
- Persist game snapshot in DB.
- Return a typed Game object.

### Fetch table/standings

Source URL pattern:
https://stats.swehockey.se/ScheduleAndResults/Overview/{season_id}

File: [src/shl/standings.py](src/shl/standings.py)

Method:
- fetch_table(season_id: int, db_dir: Path) -> List[StandingsRow]
- alias: fetchTable

Dataclass contracts:

```python
@dataclass(frozen=True)
class FetchTableArgs:
    season_id: int
    db_dir: Path

@dataclass(frozen=True)
class FetchTableResult:
    standings: List[StandingsRow]
```

Behavior:
- Fetch season overview standings.
- Persist standings in DB.
- Return typed standings rows.

### Fetch schedule

Source URL pattern:
https://stats.swehockey.se/ScheduleAndResults/Schedule/{season_id}

File: [src/shl/schedule.py](src/shl/schedule.py)

Method:
- fetch_schedule(season_id: int, db_dir: Path) -> List[ScheduleEntry]
- alias: fetchSchedule

Dataclass contracts:

```python
@dataclass(frozen=True)
class FetchScheduleArgs:
    season_id: int
    db_dir: Path

@dataclass(frozen=True)
class FetchScheduleResult:
    schedule: List[ScheduleEntry]
```

Behavior:
- Fetch season schedule.
- Persist schedule in DB.
- Return typed schedule entries.

## Data provider methods (get methods)

### Get schedule

File: [src/shl/schedule.py](src/shl/schedule.py)

Method:
- get_schedule(season_id: int, db_dir: Path) -> Optional[List[ScheduleEntry]]
- alias: getSchedule

Dataclass contracts:

```python
@dataclass(frozen=True)
class GetScheduleArgs:
    season_id: int
    db_dir: Path

@dataclass(frozen=True)
class GetScheduleResult:
    schedule: Optional[List[ScheduleEntry]]
```

API endpoint: GET /seasons/{season_id}/schedule

### Get games for date

File: [src/shl/schedule.py](src/shl/schedule.py)

Method:
- get_games_for_date(season_id: int, game_date: str, db_dir: Path) -> List[ScheduleEntry]
- alias: getGamesForDate

Dataclass contracts:

```python
@dataclass(frozen=True)
class GetGamesForDateArgs:
    season_id: int
    game_date: str  # YYYY-MM-DD
    db_dir: Path

@dataclass(frozen=True)
class GetGamesForDateResult:
    games: List[ScheduleEntry]
```

Behavior:
- Read all schedule rows for a season.
- Filter by date.

API endpoint: GET /seasons/{season_id}/games (all, or ?date=YYYY-MM-DD to filter)

### Get all played games

File: [src/shl/schedule.py](src/shl/schedule.py)

Method:
- get_all_played_games(season_id: int, db_dir: Path) -> List[ScheduleEntry]
- alias: getAllPlayedGames

Dataclass contracts:

```python
@dataclass(frozen=True)
class GetAllPlayedGamesArgs:
    season_id: int
    db_dir: Path

@dataclass(frozen=True)
class GetAllPlayedGamesResult:
    games: List[ScheduleEntry]
```

Behavior:
- Read schedule rows from DB.
- Return rows with non-empty game_result.

API endpoint: GET /seasons/{season_id}/games/played

### Get today's games

File: [src/shl/schedule.py](src/shl/schedule.py)

Method:
- get_todays_games(season_id: int, db_dir: Path) -> List[ScheduleEntry]

Behavior:
- Read schedule rows from DB.
- Return today's unfinished games.

API endpoint: GET /seasons/{season_id}/games/today

### Get computed standings

File: [src/shl/schedule.py](src/shl/schedule.py)

Method:
- get_standings(season_id: int, db_dir: Path) -> List[StandingsRow]
- alias: getStandings

Dataclass contracts:

```python
@dataclass(frozen=True)
class GetStandingsArgs:
    season_id: int
    db_dir: Path

@dataclass(frozen=True)
class GetStandingsResult:
    standings: List[StandingsRow]
```

Behavior:
- Read played games for a season.
- Load persisted game snapshots.
- Compute standings from game outcomes.

API endpoint: GET /seasons/{season_id}/standings

### Get rounds

File: [src/shl/schedule.py](src/shl/schedule.py)

Method:
- get_rounds(season_id: int, db_dir: Path) -> List[Dict]

Behavior:
- Read schedule rows from DB.
- Group games by round number.
- Return all rounds with their games.

API endpoint: GET /seasons/{season_id}/rounds

### Get played rounds

File: [src/shl/schedule.py](src/shl/schedule.py)

Method:
- get_played_rounds(season_id: int, db_dir: Path) -> List[Dict]

Behavior:
- Read schedule rows from DB.
- Group by round and return only rounds where all games have results.

API endpoint: GET /seasons/{season_id}/rounds/played

### Get next round

File: [src/shl/schedule.py](src/shl/schedule.py)

Method:
- get_next_round(season_id: int, db_dir: Path) -> Optional[Dict]

Behavior:
- Read schedule rows from DB.
- Find the first round that has unplayed games.

API endpoint: GET /seasons/{season_id}/rounds/next

### Get single game

File: [src/shl/game.py](src/shl/game.py)

Method:
- Loads persisted game snapshot by game_id.

API endpoint: GET /games/{game_id}

## Device registration

File: [src/shl/store.py](src/shl/store.py)

Methods:
- register_device(fcm_token: str, platform: str) -> None
- unregister_device(fcm_token: str) -> None
- list_device_tokens() -> List[str]

REST endpoints:
- POST /devices — register a device token for push notifications.
- DELETE /devices — unregister a device token.

## Utility methods

### Compare game score change

File: [src/shl/game.py](src/shl/game.py)

Method:
- compare_game_score_change(previous_game: Game, current_game: Game) -> ScoreChangeResult
- alias name in requirements/docs: compareGameScoreChange

Dataclass contracts:

```python
@dataclass(frozen=True)
class CompareGameScoreChangeArgs:
    previous_game: Game
    current_game: Game

@dataclass(frozen=True)
class CompareGameScoreChangeResult:
    result: ScoreChangeResult
```

Behavior:
- Compare two snapshots of the same game.
- Detect scoring changes and the teams that scored.
- Include score and previous_score strings for notification payloads.

## Notification worker

File: [src/shl/notifier.py](src/shl/notifier.py)

Behavior:
- Polls domain_events outbox for unprocessed `score_changed` and `game_state_changed` events.
- Builds notification payload from event data.
- Sends Firebase Cloud Messaging multicast to all registered device tokens.
- Marks events as processed after successful delivery.

Notification types:
| Event | Title | Body example |
|-------|-------|--------------|
| Goal scored | ⚽ Mål! {score} | {team} {scorer} ({time}) |
| Game ended | 🏁 Slutsignal | Slutresultat: {final_score} |

Environment variables:
- GOOGLE_APPLICATION_CREDENTIALS — path to Firebase service account JSON key.
- SHL_FCM_DRY_RUN — set to "1" to log notifications without sending.

## REST API endpoints

All endpoints are implemented in [src/shl/rest_api.py](src/shl/rest_api.py).

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /seasons/{season_id}/schedule | Full season schedule |
| GET | /seasons/{season_id}/games | All games (optional `?date=YYYY-MM-DD` filter) |
| GET | /seasons/{season_id}/games/played | All games with results |
| GET | /seasons/{season_id}/games/today | Today's unfinished games |
| GET | /seasons/{season_id}/standings | Computed standings |
| GET | /seasons/{season_id}/rounds | All rounds grouped |
| GET | /seasons/{season_id}/rounds/played | Completed rounds only |
| GET | /seasons/{season_id}/rounds/next | Next upcoming round |
| GET | /games/{game_id} | Single game details |
| POST | /devices | Register device for push notifications |
| DELETE | /devices | Unregister device |

Middleware:
- CORS: configurable via SHL_CORS_ORIGINS env var (default: `*`).
- Rate limiting: in-memory per-IP, configurable via SHL_RATE_LIMIT_PER_MINUTE (default: 60).
