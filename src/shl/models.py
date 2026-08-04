from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class GoalDetail:
    home_score: int
    away_score: int
    strength: str
    qualifier: Optional[str]

    @classmethod
    def from_dict(cls, d: Dict) -> GoalDetail:
        return cls(
            home_score=d["home_score"],
            away_score=d["away_score"],
            strength=d.get("strength") or "",
            qualifier=d.get("qualifier"),
        )


@dataclass(frozen=True)
class PenaltyTimeRange:
    start: Optional[str]
    end: Optional[str]

    @classmethod
    def from_dict(cls, d: Dict) -> PenaltyTimeRange:
        return cls(start=d.get("start"), end=d.get("end"))


@dataclass(frozen=True)
class Action:
    period: Optional[str]
    game_time: str
    event_type: str
    team_abbrev: str
    player_text: str
    players: List[str]
    player_numbers: List[int]
    is_goal: bool
    goal: Optional[GoalDetail] = None
    event_detail: Optional[str] = None
    shot_outcome: Optional[str] = None
    penalty_reason: Optional[str] = None
    penalty_time_range: Optional[PenaltyTimeRange] = None

    @classmethod
    def from_dict(cls, d: Dict) -> Action:
        goal_raw = d.get("goal")
        ptr_raw = d.get("penalty_time_range")
        return cls(
            period=d.get("period"),
            game_time=d.get("game_time") or "",
            event_type=d.get("event_type") or "",
            team_abbrev=d.get("team_abbrev") or "",
            player_text=d.get("player_text") or "",
            players=list(d.get("players") or []),
            player_numbers=list(d.get("player_numbers") or []),
            is_goal=bool(d.get("is_goal")),
            goal=GoalDetail.from_dict(goal_raw) if goal_raw else None,
            event_detail=d.get("event_detail"),
            shot_outcome=d.get("shot_outcome"),
            penalty_reason=d.get("penalty_reason"),
            penalty_time_range=PenaltyTimeRange.from_dict(ptr_raw) if ptr_raw else None,
        )


@dataclass(frozen=True)
class Score:
    current: str
    home_score: int
    away_score: int
    periods: List[str]
    current_period: Optional[int]
    state: Optional[str]

    @classmethod
    def from_dict(cls, d: Dict) -> Score:
        import re
        current = d.get("current") or d.get("final") or ""
        home_score = d.get("home_score")
        away_score = d.get("away_score")
        if home_score is None or away_score is None:
            m = re.search(r"(\d+)\s*-\s*(\d+)", current)
            if m:
                home_score = int(m.group(1))
                away_score = int(m.group(2))
            else:
                home_score = home_score or 0
                away_score = away_score or 0
        return cls(
            current=current,
            home_score=home_score,
            away_score=away_score,
            periods=list(d.get("periods") or []),
            current_period=d.get("current_period"),
            state=d.get("state"),
        )


@dataclass(frozen=True)
class GameInfo:
    home_team: str
    away_team: str
    is_overtime: bool
    is_shootout: bool
    date_time: Optional[str]
    league: Optional[str]
    arena: Optional[str]

    @classmethod
    def from_dict(cls, d: Dict) -> GameInfo:
        return cls(
            home_team=d["home_team"],
            away_team=d["away_team"],
            is_overtime=bool(d.get("is_overtime")),
            is_shootout=bool(d.get("is_shootout")),
            date_time=d.get("date_time"),
            league=d.get("league"),
            arena=d.get("arena"),
        )


@dataclass(frozen=True)
class ShotStats:
    total: int
    by_period: List[int]
    percentage: str

    @classmethod
    def from_dict(cls, d: Dict) -> ShotStats:
        return cls(total=d["total"], by_period=list(d.get("by_period") or []), percentage=d["percentage"])


@dataclass(frozen=True)
class SaveStats:
    total: int
    by_period: List[int]
    percentage: str

    @classmethod
    def from_dict(cls, d: Dict) -> SaveStats:
        return cls(total=d["total"], by_period=list(d.get("by_period") or []), percentage=d["percentage"])


@dataclass(frozen=True)
class PimStats:
    total: int
    by_period: List[int]

    @classmethod
    def from_dict(cls, d: Dict) -> PimStats:
        return cls(total=d["total"], by_period=list(d.get("by_period") or []))


@dataclass(frozen=True)
class PpStats:
    percentage: str
    time: str

    @classmethod
    def from_dict(cls, d: Dict) -> PpStats:
        return cls(percentage=d["percentage"], time=d["time"])


@dataclass(frozen=True)
class TeamStats:
    shots: ShotStats
    saves: SaveStats
    pim: PimStats
    pp: PpStats

    @classmethod
    def from_dict(cls, d: Dict) -> TeamStats:
        return cls(
            shots=ShotStats.from_dict(d["shots"]),
            saves=SaveStats.from_dict(d["saves"]),
            pim=PimStats.from_dict(d["pim"]),
            pp=PpStats.from_dict(d["pp"]),
        )


@dataclass(frozen=True)
class Game:
    game: GameInfo
    score: Score
    teams: Dict[str, TeamStats]
    actions: List[Action]

    @classmethod
    def from_dict(cls, d: Dict) -> Game:
        return cls(
            game=GameInfo.from_dict(d["game"]),
            score=Score.from_dict(d["score"]),
            teams={name: TeamStats.from_dict(stats) for name, stats in (d.get("teams") or {}).items()},
            actions=[Action.from_dict(a) for a in (d.get("actions") or [])],
        )

    def to_dict(self) -> Dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ScheduleEntry:
    date: str
    time: str
    game_result: str
    spectators: str
    venue: str
    game_url: str
    round: str

    @classmethod
    def from_dict(cls, d: Dict) -> ScheduleEntry:
        return cls(
            date=d.get("date") or "",
            time=d.get("time") or "",
            game_result=d.get("game_result") or "",
            spectators=d.get("spectators") or "",
            venue=d.get("venue") or "",
            game_url=d.get("game_url") or "",
            round=d.get("round") or "",
        )

    def to_dict(self) -> Dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class StandingsRow:
    rank: int
    team: str
    games_played: int
    w: int
    t: int
    l: int
    goals_for: int
    goals_against: int
    goal_difference: int
    tp: int
    otw: int
    otl: int
    gwsw: int
    gwsl: int

    @classmethod
    def from_dict(cls, d: Dict) -> StandingsRow:
        return cls(
            rank=d["rank"],
            team=d["team"],
            games_played=d["games_played"],
            w=d["w"],
            t=d["t"],
            l=d["l"],
            goals_for=d["goals_for"],
            goals_against=d["goals_against"],
            goal_difference=d["goal_difference"],
            tp=d["tp"],
            otw=d["otw"],
            otl=d["otl"],
            gwsw=d["gwsw"],
            gwsl=d["gwsl"],
        )

    def to_dict(self) -> Dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class PenaltyMetadata:
    clean_player_text: str
    players: List[str]
    player_numbers: List[int]
    reason: Optional[str]
    time_range: Optional[PenaltyTimeRange]


@dataclass(frozen=True)
class ScoringEvent:
    team: str
    goals_added: int
    scorer: Optional[str]
    scorer_players: Optional[List[str]]
    game_time: Optional[str]

    @classmethod
    def from_dict(cls, d: Dict) -> ScoringEvent:
        return cls(
            team=d["team"],
            goals_added=d["goals_added"],
            scorer=d.get("scorer"),
            scorer_players=list(d["scorer_players"]) if d.get("scorer_players") else None,
            game_time=d.get("game_time"),
        )


@dataclass(frozen=True)
class ScoreChangeResult:
    scored: bool
    teams_scored: List[ScoringEvent]
    score: str
    previous_score: str

    @classmethod
    def from_dict(cls, d: Dict) -> ScoreChangeResult:
        return cls(
            scored=d["scored"],
            teams_scored=[ScoringEvent.from_dict(e) for e in d.get("teams_scored") or []],
            score=d["score"],
            previous_score=d["previous_score"],
        )

    def to_dict(self) -> Dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class PollTarget:
    id: int
    target_type: str
    target_key: str
    enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_error_at: Optional[str] = None
    error_count: int = 0
    next_poll_at: Optional[str] = None
    last_duration_ms: Optional[int] = None


@dataclass(frozen=True)
class DomainEvent:
    id: int
    event_type: str
    aggregate_key: str
    payload: Dict
    created_at: Optional[str] = None
    processed_at: Optional[str] = None
