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
| `game_result` | `str` | Score string if played, empty if not yet played |
| `spectators` | `str` | Attendance figure as a string |
| `venue` | `str` | Arena name |
| `game_url` | `str` | Full URL to the game events page |
| `round` | `str` | Round number as a string |

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

Has `to_dict` for JSON serialisation.

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
