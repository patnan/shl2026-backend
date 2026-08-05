# Implementation Plan: Player Stats, Goalie Stats & Rosters

## SweHockey Source URLs

All data comes from `stats.swehockey.se` using the season ID (e.g. `18263`):

| Data | URL |
|------|-----|
| Scoring leaders | `/Players/Statistics/ScoringLeaders/{season_id}` |
| Leading goalies | `/Players/Statistics/LeadingGoaliesSVS/{season_id}` |
| Players by team (stats) | `/Teams/Info/PlayersByTeam/{season_id}` |
| Players by team (penalties) | `/Teams/Info/PlayersByTeamPenalties/{season_id}` |
| Team rosters | `/Teams/Info/TeamRoster/{season_id}` |

All pages return HTML tables with the full season's data. One request per page gives all teams/players.

---

## Data Models

### PlayerStat

From the ScoringLeaders page. Fields:

| Field | Source column | Type |
|-------|-------------|------|
| `rank` | Rk | `int` |
| `jersey` | No | `int` |
| `name` | Name | `str` |
| `team` | Team | `str` (abbreviation) |
| `position` | Pos | `str` (CE, LW, RW, LD, RD) |
| `games_played` | GP | `int` |
| `goals` | G | `int` |
| `assists` | A | `int` |
| `total_points` | TP | `int` |
| `points_per_game` | AVG. | `float` |
| `penalty_minutes` | PIM | `int` |
| `plus_minus` | +/- | `int` |

### GoalieStat

From the LeadingGoaliesSVS page. Fields:

| Field | Source column | Type |
|-------|-------------|------|
| `rank` | Rk | `int` |
| `jersey` | No | `int` |
| `name` | Name | `str` |
| `team` | Team | `str` (abbreviation) |
| `games_played` | GP | `int` |
| `games_played_in` | GPI | `int` |
| `minutes_in_play` | MIP | `str` (e.g. "1425:53") |
| `shots_on_goal` | SOG | `int` |
| `goals_against` | GA | `int` |
| `goals_against_avg` | GAA | `float` |
| `saves` | SVS | `int` |
| `save_percentage` | SVS% | `float` |
| `shutouts` | SO | `int` |
| `wins` | W | `int` |
| `losses` | L | `int` |
| `win_percentage` | W% | `float` |

### RosterEntry

From the TeamRoster page. Fields:

| Field | Source column | Type |
|-------|-------------|------|
| `team` | Section header | `str` (full team name) |
| `jersey` | No | `int` |
| `name` | Name | `str` |
| `birthdate` | Birthdate | `str` |
| `position` | Position | `str` |
| `handedness` | L/R | `str` |
| `height` | Height | `int` (cm) |
| `weight` | Weight | `int` (kg) |
| `nationality` | Nationality / Club | `str` |
| `youth_club` | Youth club | `str` |

---

## Implementation Steps

### 1. Models (`src/shl/models.py`)

Add three frozen dataclasses: `PlayerStat`, `GoalieStat`, `RosterEntry`. Each with `from_dict` and included in `to_dict` via `dataclasses.asdict`.

### 2. Parser (`src/shl/helpers/parsing.py` or new `src/shl/helpers/stats_parsing.py`)

Three parser functions:

- `parse_scoring_leaders(html: str) -> List[PlayerStat]`
  - Find the table with headers Rk/No/Name/Team/Pos/GP/G/A/TP/AVG./PIM/+/-
  - Parse each data row into a PlayerStat
  
- `parse_leading_goalies(html: str) -> List[GoalieStat]`
  - Find the table with headers Rk/No/Name/Team/GP/GPI/MIP/SOG/GA/GAA/SVS/SVS%/SO/W/L/W%
  - Parse each data row into a GoalieStat

- `parse_team_rosters(html: str) -> List[RosterEntry]`
  - Page has one table per team (56 tables = 14 teams × 2 duplicates + officials)
  - Track current team from section headers
  - Parse each player row into a RosterEntry

### 3. Fetch/Store (`src/shl/stats.py` — new module)

Public functions:

```python
def fetch_player_stats(season_id: int, db_dir: Path) -> List[PlayerStat]
def fetch_goalie_stats(season_id: int, db_dir: Path) -> List[GoalieStat]
def fetch_rosters(season_id: int, db_dir: Path) -> List[RosterEntry]

def get_player_stats(season_id: int, db_dir: Path) -> Optional[List[PlayerStat]]
def get_goalie_stats(season_id: int, db_dir: Path) -> Optional[List[GoalieStat]]
def get_rosters(season_id: int, db_dir: Path) -> Optional[List[RosterEntry]]
```

Each `fetch_*` hits SweHockey, parses, saves to DB, returns data.
Each `get_*` loads from DB only (cache read).

### 4. Store (`src/shl/store.py`)

New tables:

```sql
CREATE TABLE IF NOT EXISTS player_stats (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goalie_stats (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rosters (
    season_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
```

Methods: `save_player_stats`, `load_player_stats`, `save_goalie_stats`, `load_goalie_stats`, `save_rosters`, `load_rosters` (same pattern as schedule/standings).

### 5. Poller targets (`src/shl/poller.py`)

New target types:

| Target type | Key | Cadence |
|-------------|-----|---------|
| `player_stats` | season_id | Every 2 hours (data changes at most once per game day) |
| `goalie_stats` | season_id | Every 2 hours |
| `rosters` | season_id | Every 24 hours (roster changes are rare) |

Add to `seed_season_targets` so they're created alongside schedule/standings.

Add handlers in `_run_target`:
```python
if target_type == "player_stats":
    fetch_player_stats(int(target_key), cache_dir)
    return

if target_type == "goalie_stats":
    fetch_goalie_stats(int(target_key), cache_dir)
    return

if target_type == "rosters":
    fetch_rosters(int(target_key), cache_dir)
    return
```

### 6. REST API (`src/shl/rest_api.py`)

New endpoints:

```
GET /seasons/{season_id}/players          -> List[PlayerStat]
GET /seasons/{season_id}/players?team=SKE -> filtered by team abbreviation
GET /seasons/{season_id}/goalies          -> List[GoalieStat]
GET /seasons/{season_id}/goalies?team=FRÖ -> filtered by team abbreviation
GET /seasons/{season_id}/rosters          -> List[RosterEntry] (all teams)
GET /seasons/{season_id}/rosters/{team}   -> List[RosterEntry] (one team)
```

Response format follows existing pattern with `data` + `meta` envelope.

### 7. Seeding CLI

Update `poller-seed` to include player_stats, goalie_stats, and rosters targets. Maybe add a `--skip-stats` flag for lightweight seeds.

---

## Effort Estimate

| Step | Effort |
|------|--------|
| Models | 30 min |
| Parsers | 2-3 hours (HTML table parsing, handling duplicates/edge cases) |
| Fetch/Store | 1 hour |
| Poller targets | 30 min |
| REST API | 30 min |
| Tests | 1-2 hours |
| **Total** | **~1 day** |

---

## Risk / Edge Cases

- SweHockey duplicates tables on these pages (each table appears twice — visible + print version). Need to deduplicate.
- Team abbreviations on stats pages (e.g. "SKE", "FRÖ") need to map to full team names for consistency with schedule/standings data.
- The PlayersByTeam page has both skater stats and goalie stats per team — could parse this single page for per-team views instead of using the league-wide pages.
- PIM field on ScoringLeaders uses format like "53:36" (minutes:seconds) — needs parsing to total minutes int.
- +/- might have leading sign that needs parsing.
