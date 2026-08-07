# Data Models

All models are frozen dataclasses defined in `src/shl/models.py`. Every model that crosses a serialization boundary has a `from_dict` classmethod; top-level models also have `to_dict`.

---

## GoalDetail

Describes the score state and context at the moment a goal was scored.

| Field | Type | Description |
|---|---|---|
| `home_score` | `int` | Home team score after this goal |
| `away_score` | `int` | Away team score after this goal |
| `strength` | `str` | Strength state, e.g. `"EV"`, `"PP"`, `"SH"`, `"GWS"` |
| `qualifier` | `Optional[str]` | Extra qualifier, e.g. `"EN"` (empty net) |

---

## PenaltyTimeRange

Start and end clock times for a penalty.

| Field | Type | Description |
|---|---|---|
| `start` | `Optional[str]` | Clock time when penalty starts, e.g. `"32:14"` |
| `end` | `Optional[str]` | Clock time when penalty ends |

---

## PenaltyMetadata

Parsed penalty player and reason data. Used internally by `extract_penalty_metadata`.

| Field | Type | Description |
|---|---|---|
| `clean_player_text` | `str` | Normalised player text after stripping time range |
| `players` | `List[str]` | Player name entries |
| `player_numbers` | `List[int]` | Jersey numbers |
| `reason` | `Optional[str]` | Penalty reason, e.g. `"Hooking"` |
| `time_range` | `Optional[PenaltyTimeRange]` | Penalty clock range |

---

## Action

A single game event (goal, penalty, GWS, PS, etc.).

| Field | Type | Description |
|---|---|---|
| `period` | `Optional[str]` | Period label, e.g. `"1st period"`, `"overtime"`, `"period 5"` |
| `game_time` | `str` | Clock time, e.g. `"32:14"` |
| `event_type` | `str` | `"goal"`, `"penalty"`, `"GWS"`, `"PS"`, or raw cell text |
| `team_abbrev` | `str` | Team abbreviation as it appears on the page |
| `player_text` | `str` | Raw player cell text (cleaned) |
| `players` | `List[str]` | Parsed player name entries |
| `player_numbers` | `List[int]` | Jersey numbers |
| `is_goal` | `bool` | Whether this action resulted in a goal |
| `goal` | `Optional[GoalDetail]` | Goal detail if `is_goal` is true |
| `event_detail` | `Optional[str]` | Raw event type cell, e.g. `"2 min"` or score string |
| `shot_outcome` | `Optional[str]` | `"scored"` or `"missed"` for GWS rows |
| `penalty_reason` | `Optional[str]` | Penalty reason extracted from player text |
| `penalty_time_range` | `Optional[PenaltyTimeRange]` | Penalty clock range |

---

## Score

Final score and period breakdown for a game.

| Field | Type | Description |
|---|---|---|
| `current` | `str` | Score string, e.g. `"3-2"` |
| `home_score` | `int` | Home team goals |
| `away_score` | `int` | Away team goals |
| `periods` | `List[str]` | Per-period score strings, e.g. `["1-0", "1-1", "1-1"]` |
| `current_period` | `Optional[int]` | Number of completed periods |
| `state` | `Optional[str]` | `"Final Score"` when the game is finished |

`from_dict` tolerates missing `home_score`/`away_score` by parsing them from `current` (or legacy `final` key).

---

## GameInfo

Metadata about a game.

| Field | Type | Description |
|---|---|---|
| `home_team` | `str` | Home team name |
| `away_team` | `str` | Away team name |
| `is_overtime` | `bool` | True if the game went to overtime |
| `is_shootout` | `bool` | True if the game went to a shootout |
| `date_time` | `Optional[str]` | Date/time string from the page |
| `league` | `Optional[str]` | League name |
| `arena` | `Optional[str]` | Arena name |

---

## ShotStats

Shot statistics for one team.

| Field | Type | Description |
|---|---|---|
| `total` | `int` | Total shots |
| `by_period` | `List[int]` | Shots per period |
| `percentage` | `str` | Shot percentage string |

---

## SaveStats

Save statistics for one team.

| Field | Type | Description |
|---|---|---|
| `total` | `int` | Total saves |
| `by_period` | `List[int]` | Saves per period |
| `percentage` | `str` | Save percentage string |

---

## PimStats

Penalty minutes for one team.

| Field | Type | Description |
|---|---|---|
| `total` | `int` | Total penalty minutes |
| `by_period` | `List[int]` | Penalty minutes per period |

---

## PpStats

Power play statistics for one team.

| Field | Type | Description |
|---|---|---|
| `percentage` | `str` | Power play percentage string |
| `time` | `str` | Total power play time string |

---

## TeamStats

All stats for one team in a game. Keyed by team name in `Game.teams`.

| Field | Type | Description |
|---|---|---|
| `shots` | `ShotStats` | Shot statistics |
| `saves` | `SaveStats` | Save statistics |
| `pim` | `PimStats` | Penalty minute statistics |
| `pp` | `PpStats` | Power play statistics |

---

## Game

Top-level game object. Returned by all fetch and extract functions.

| Field | Type | Description |
|---|---|---|
| `game` | `GameInfo` | Game metadata |
| `score` | `Score` | Final score and period breakdown |
| `teams` | `Dict[str, TeamStats]` | Stats keyed by team name |
| `actions` | `List[Action]` | All game events in order |

Has `to_dict` for JSON serialisation.

---

## ScheduleEntry

One row from a season schedule page.

| Field | Type | Description |
|---|---|---|
| `date` | `str` | Game date, `YYYY-MM-DD` |
| `time` | `str` | Game time, `HH:MM` |
| `home_team` | `str` | Home team name |
| `away_team` | `str` | Away team name |
| `game_result` | `str` | Score string if played (e.g. `"2 - 3"`), empty if not yet played |
| `periods` | `str` | Period breakdown string, e.g. `"(0-0, 1-1, 1-1, 0-1)"` |
| `spectators` | `str` | Attendance figure as a string |
| `venue` | `str` | Arena name |
| `game_url` | `str` | Full URL to the game events page (empty for unstarted seasons) |
| `round` | `str` | Round number as a string (from page header, or empty if inferred by date) |
| `status` | `str` | Game status during live games (e.g. `"2nd period (01:49)"`, `"Waiting for 1st period"`). Empty when not live. |
| `game_clock` | `str` | Current game clock parsed from status (e.g. `"01:49"`). Empty when not in progress. |
| `current_period` | `str` | Current period parsed from status (e.g. `"2nd period"`). Empty when not in progress. |

Computed property (included in `to_dict` output):

| Property | Type | Description |
|---|---|---|
| `overtime` | `str` | `"OT"` (4 periods), `"SO"` (5 periods), or `""` (regulation/unplayed) |

Has `to_dict` for JSON serialisation.

---

## StandingsRow

One team row in the standings table.

| Field | Type | Description |
|---|---|---|
| `rank` | `int` | Current rank |
| `team` | `str` | Team name |
| `games_played` | `int` | Games played |
| `w` | `int` | Regulation wins |
| `t` | `int` | Ties (games that went to OT/SO) |
| `l` | `int` | Regulation losses |
| `goals_for` | `int` | Goals scored |
| `goals_against` | `int` | Goals conceded |
| `goal_difference` | `int` | Goal difference |
| `tp` | `int` | Total points |
| `otw` | `int` | Overtime wins |
| `otl` | `int` | Overtime losses |
| `gwsw` | `int` | Game winning shot wins |
| `gwsl` | `int` | Game winning shot losses |
| `movement` | `int` | Position change since last saved standings (positive = moved up, negative = moved down, 0 = unchanged) |

Has `to_dict` for JSON serialisation.

---

## PlayerStat

One player row from the SweHockey scoring leaders page.

| Field | Type | Description |
|---|---|---|
| `rank` | `int` | Scoring rank |
| `jersey` | `int` | Jersey number |
| `name` | `str` | Player name (Last, First) |
| `team` | `str` | Team abbreviation (e.g. SKE, FRÖ) |
| `position` | `str` | Position (CE, LW, RW, LD, RD) |
| `games_played` | `int` | Games played |
| `goals` | `int` | Goals scored |
| `assists` | `int` | Assists |
| `total_points` | `int` | Total points (G + A) |
| `points_per_game` | `float` | Points per game average |
| `penalty_minutes` | `int` | Penalty minutes |
| `plus_minus` | `int` | Plus/minus (goals for minus goals against while on ice) |

---

## GoalieStat

One goalie row from the SweHockey leading goalies page.

| Field | Type | Description |
|---|---|---|
| `rank` | `int` | Ranking by save percentage |
| `jersey` | `int` | Jersey number |
| `name` | `str` | Goalie name (Last, First) |
| `team` | `str` | Team abbreviation |
| `games_played` | `int` | Games in roster |
| `games_played_in` | `int` | Games actually played |
| `minutes_in_play` | `str` | Minutes in play (MM:SS format) |
| `shots_on_goal` | `int` | Shots faced |
| `goals_against` | `int` | Goals allowed |
| `goals_against_avg` | `float` | Goals against average |
| `saves` | `int` | Total saves |
| `save_percentage` | `float` | Save percentage |
| `shutouts` | `int` | Shutouts |
| `wins` | `int` | Wins |
| `losses` | `int` | Losses |
| `win_percentage` | `float` | Win percentage |

---

## RosterEntry

One player row from the SweHockey team roster page.

| Field | Type | Description |
|---|---|---|
| `team` | `str` | Full team name |
| `jersey` | `int` | Jersey number |
| `name` | `str` | Player name (Last, First) |
| `birthdate` | `str` | Birth date (YYYY-MM-DD) |
| `position` | `str` | Position (GK, LD, RD, CE, LW, RW) |
| `handedness` | `str` | Stick hand (L/R) |
| `height` | `int` | Height in cm |
| `weight` | `int` | Weight in kg |
| `nationality` | `str` | Nationality code (SWE, CZE, USA, etc.) |
| `youth_club` | `str` | Youth club name |

---

## ScoringEvent

One team's scoring contribution within a `ScoreChangeResult`.

| Field | Type | Description |
|---|---|---|
| `team` | `str` | Team name |
| `goals_added` | `int` | Number of goals scored in this change |
| `scorer` | `Optional[str]` | Player text of the scorer |
| `scorer_players` | `Optional[List[str]]` | Parsed player name entries |
| `game_time` | `Optional[str]` | Clock time of the goal |

---

## ScoreChangeResult

Result of comparing two game snapshots. Returned by `compare_game_score_change`.

| Field | Type | Description |
|---|---|---|
| `scored` | `bool` | True if any team scored |
| `teams_scored` | `List[ScoringEvent]` | One entry per team that scored |
| `score` | `str` | Current score string, e.g. `"3-2"` |
| `previous_score` | `str` | Previous score string, e.g. `"2-2"` |

Has `to_dict` for JSON serialisation.

---

## PollTarget

Represents a poll target with its scheduling state. Returned by store list/query methods.

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Target ID (primary key) |
| `target_type` | `str` | `"game"`, `"schedule"`, or `"standings"` |
| `target_key` | `str` | Game ID or season ID as string |
| `enabled` | `bool` | Whether the target is active |
| `created_at` | `Optional[str]` | ISO timestamp of creation |
| `updated_at` | `Optional[str]` | ISO timestamp of last update |
| `last_success_at` | `Optional[str]` | ISO timestamp of last successful poll |
| `last_error_at` | `Optional[str]` | ISO timestamp of last failed poll |
| `error_count` | `int` | Consecutive error count |
| `next_poll_at` | `Optional[str]` | ISO timestamp of next scheduled poll |
| `last_duration_ms` | `Optional[int]` | Duration of last poll in milliseconds |

---

## DomainEvent

An event written to the outbox table for downstream processing (e.g. notifications).

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Event ID (primary key) |
| `event_type` | `str` | `"score_changed"`, `"game_state_changed"`, `"poll_completed"`, `"poll_failed"` |
| `aggregate_key` | `str` | e.g. `"game:1004308"` |
| `payload` | `Dict` | Event-specific data |
| `created_at` | `Optional[str]` | ISO timestamp |
| `processed_at` | `Optional[str]` | ISO timestamp when consumed (None if pending) |

---

## ShlSeTeam

Team data from shl.se (Sportality platform). Used for mapping SweHockey team names to shl.se resources.

Defined in: [src/shl/shl_se.py](src/shl/shl_se.py)

| Field | Type | Description |
|---|---|---|
| `uuid` | `str` | shl.se team UUID |
| `team_code` | `str` | Short team code (e.g. "BIF", "SAIK", "FHC") |
| `instance_id` | `str` | Sportality instance ID |
| `name_short` | `str` | Short name used for substring matching (e.g. "Brynäs", "Skellefteå") |
| `name_long` | `str` | Long name (e.g. "Brynäs IF", "Skellefteå AIK") |
| `name_full` | `str` | Full official name |
| `logo_url` | `str` | Team logo URL |

Has `from_api(data: dict)` class method for constructing from shl.se API response.

---

## ShlSePlayer

Player data from shl.se. Enriches SweHockey data with portraits, UUIDs, and detailed position info.

Defined in: [src/shl/shl_se.py](src/shl/shl_se.py)

| Field | Type | Description |
|---|---|---|
| `uuid` | `str` | shl.se player UUID |
| `first_name` | `str` | First name |
| `last_name` | `str` | Last name |
| `full_name` | `str` | Full display name |
| `jersey_number` | `int` | Jersey number |
| `nationality` | `str` | Two-letter country code (e.g. "SE", "FI") |
| `position` | `str` | Position group in Swedish (e.g. "Backar", "Forwards", "Målvakter") |
| `position_code` | `str` | Position code: "F" (forward), "D" (defense), "GK" (goalie) |
| `portrait_url` | `str` | URL to player portrait image on shl.se CDN (empty if unavailable) |

---

## TeamMapper

Maps between SweHockey team names and shl.se team data. Uses substring matching (shl.se short name ⊂ SweHockey full name) with a normalized-space fallback for edge cases like "HV 71" vs "HV71".

Defined in: [src/shl/shl_se.py](src/shl/shl_se.py)

Key methods:
- `from_api()` — create from live shl.se API
- `swehockey_to_shl_se(name)` → `Optional[ShlSeTeam]`
- `shl_se_to_swehockey(team, names)` → `Optional[str]`
- `get_team_by_code(code)` → `Optional[ShlSeTeam]`

---

## PlayerMapper

Maps SweHockey players to shl.se player data using (team_name, jersey_number) as key. Loads team rosters on demand.

Defined in: [src/shl/shl_se.py](src/shl/shl_se.py)

Key methods:
- `load_team(swehockey_team_name)` → `bool`
- `find(swehockey_team_name, jersey_number)` → `Optional[ShlSePlayer]`
- `get_portrait_url(swehockey_team_name, jersey_number)` → `Optional[str]`
- `get_team_logo_url(swehockey_team_name)` → `Optional[str]`
