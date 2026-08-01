# SHL Domain Models and Data Classes

This file documents the immutable dataclasses defined in [src/shl/models.py](src/shl/models.py).

All classes use Python dataclasses with frozen=True.

## Core game models

### GoalDetail
- home_score: int
- away_score: int
- strength: str
- qualifier: Optional[str]

Used on action rows that contain a parsed score transition like 2-1 (PP).

### PenaltyTimeRange
- start: Optional[str]
- end: Optional[str]

Represents a parsed penalty time window, for example 32:14-34:14.

### Action
- period: Optional[str]
- game_time: str
- event_type: str
- team_abbrev: str
- player_text: str
- players: List[str]
- player_numbers: List[int]
- is_goal: bool
- goal: Optional[GoalDetail]
- event_detail: Optional[str]
- shot_outcome: Optional[str]
- penalty_reason: Optional[str]
- penalty_time_range: Optional[PenaltyTimeRange]

Represents one event in the Actions table.

### Score
- current: str
- home_score: int
- away_score: int
- periods: List[str]
- current_period: Optional[int]
- state: Optional[str]

Represents the scoreboard state and period breakdown.

### GameInfo
- home_team: str
- away_team: str
- is_overtime: bool
- is_shootout: bool
- date_time: Optional[str]
- league: Optional[str]
- arena: Optional[str]

Metadata for a game page.

### ShotStats
- total: int
- by_period: List[int]
- percentage: str

### SaveStats
- total: int
- by_period: List[int]
- percentage: str

### PimStats
- total: int
- by_period: List[int]

### PpStats
- percentage: str
- time: str

### TeamStats
- shots: ShotStats
- saves: SaveStats
- pim: PimStats
- pp: PpStats

Team-level metrics grouped under a game.

### Game
- game: GameInfo
- score: Score
- teams: Dict[str, TeamStats]
- actions: List[Action]

Top-level game snapshot used throughout fetching, persistence, and comparisons.

## Schedule and standings models

### ScheduleEntry
- date: str
- time: str
- game_result: str
- spectators: str
- venue: str
- game_url: str
- round: str

Represents one row in the season schedule.

### StandingsRow
- rank: int
- team: str
- games_played: int
- w: int
- t: int
- l: int
- goals_for: int
- goals_against: int
- goal_difference: int
- tp: int
- otw: int
- otl: int
- gwsw: int
- gwsl: int

Represents one row in standings output.

## Comparison models

### PenaltyMetadata
- clean_player_text: str
- players: List[str]
- player_numbers: List[int]
- reason: Optional[str]
- time_range: Optional[PenaltyTimeRange]

Internal helper shape returned by penalty parsing logic.

### ScoringEvent
- team: str
- goals_added: int
- scorer: Optional[str]
- scorer_players: Optional[List[str]]
- game_time: Optional[str]

Represents one team scoring event between snapshots.

### ScoreChangeResult
- scored: bool
- teams_scored: List[ScoringEvent]
- score: str
- previous_score: str

Result object from game snapshot comparison.

## Serialization helpers

The following classes expose from_dict and/or to_dict helpers:
- GoalDetail: from_dict
- PenaltyTimeRange: from_dict
- Action: from_dict
- Score: from_dict
- GameInfo: from_dict
- ShotStats: from_dict
- SaveStats: from_dict
- PimStats: from_dict
- PpStats: from_dict
- TeamStats: from_dict
- Game: from_dict, to_dict
- ScheduleEntry: from_dict, to_dict
- StandingsRow: from_dict, to_dict
- ScoringEvent: from_dict
- ScoreChangeResult: from_dict, to_dict