# Requirements

This document defines the service requirements for scraping SweHockey data, storing it in a local database, and exposing API methods to read persisted data.

Implementation language: Python.

## Goals

- fetch methods: pull external data and persist it in the database.
- get methods: read persisted data and return typed objects.
- compare methods: detect score changes between snapshots and support notifications.

## Runtime architecture

- Poller 1: live games.
  Cadence differs by game state: not started, in progress, finished.
- Poller 2: schedule updates.
- Poller 3: standings refresh.
  Can be event-driven after game/score changes, or periodic.
- REST server: exposes read APIs based on get methods.

## Data classes

Domain dataclasses are defined in [src/shl/models.py](src/shl/models.py) and documented in [MODELS.md](MODELS.md) and [MODELS.m](MODELS.m).

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

API endpoint: TBD.

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

API endpoint: TBD.

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

API endpoint: TBD.

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
