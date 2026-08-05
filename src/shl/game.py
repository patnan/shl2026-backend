import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from src.shl.helpers.extraction import extract_game_by_id
from src.shl.models import Action, Game, Score, ScoreChangeResult, ScoringEvent
from src.shl.store import load_game, save_game


class CompareGameScoreChangeError(RuntimeError):
    pass


class FetchGameError(RuntimeError):
    pass


def _is_past_game_snapshot(game: Game) -> bool:
    game_date_text = (game.game.date_time or "")[:10]
    if not game_date_text:
        return False

    try:
        game_date = date.fromisoformat(game_date_text)
    except ValueError:
        return False

    return game_date < date.today()


def fetch_game(game_id: int, db_dir: Path, force_reparse: bool = False) -> Game:
    """Fetch a game by ID, using cached data if available and the game is in the past.

    If the game is not cached or is still in progress (today or future),
    it will be scraped from SweHockey and saved to the database.

    Args:
        game_id: SweHockey game event ID.
        db_dir: Path to the cache/database directory.
        force_reparse: If True, always re-scrape regardless of cache state.

    Returns:
        The parsed Game dataclass.

    Raises:
        FetchGameError: If scraping or loading fails.
    """
    try:
        if not force_reparse:
            cached = load_game(db_dir, game_id)
            if cached is not None and _is_past_game_snapshot(cached):
                return cached

        game = extract_game_by_id(game_id)
        save_game(db_dir, game_id, game)
        return game
    except Exception as exc:
        raise FetchGameError(f"fetch_game failed for '{game_id}': {exc}") from exc


fetchGame = fetch_game


def _extract_score_pair(game: Game) -> Score:
    return game.score


def _goal_action_key(action: Action) -> Optional[tuple]:
    if action.goal is None:
        return None
    return (action.goal.home_score, action.goal.away_score, action.game_time, action.player_text)


def _extract_goal_actions(game: Game) -> List[Action]:
    return [a for a in game.actions if a.goal is not None]


def _action_key(action: Action) -> tuple:
    return (
        str(action.period),
        action.game_time,
        action.event_type,
        action.team_abbrev,
        action.player_text,
        tuple(action.players),
    )


def _extract_actions(game: Game) -> List[Action]:
    return list(game.actions)


def _extract_new_actions(previous_game: Game, current_game: Game) -> List[Action]:
    prev_counts: dict = {}
    for action in previous_game.actions:
        key = _action_key(action)
        prev_counts[key] = prev_counts.get(key, 0) + 1

    new_actions: List[Action] = []
    for action in current_game.actions:
        key = _action_key(action)
        count = prev_counts.get(key, 0)
        if count > 0:
            prev_counts[key] = count - 1
            continue
        new_actions.append(action)

    return new_actions


def _normalize_abbrev(value: str) -> str:
    return re.sub(r"\W+", "", value, flags=re.UNICODE).upper()


_team_abbrev_cache: Dict[str, str] = {}  # team_name -> abbreviation


def load_team_abbrev_map(season_id: int, db_dir: Path) -> None:
    """Load team abbreviations into the module-level cache."""
    from src.shl.store import load_team_info
    teams = load_team_info(db_dir, season_id)
    if teams:
        _team_abbrev_cache.clear()
        for t in teams:
            _team_abbrev_cache[t.team] = t.abbreviation


def _team_abbrev_candidates(team_name: str) -> set:
    tokens = re.findall(r"[A-Za-zÅÄÖåäö]+", team_name)
    if not tokens:
        return set()

    candidates = set()
    candidates.add("".join(token[0] for token in tokens).upper())
    candidates.add(tokens[0][:3].upper())

    if len(tokens) >= 2:
        candidates.add((tokens[0][0] + tokens[-1][0]).upper())
        for token in tokens[1:]:
            if len(token) <= 3:
                candidates.add((tokens[0][0] + token).upper())

    # Include stored official abbreviation if available.
    stored = _team_abbrev_cache.get(team_name)
    if stored:
        candidates.add(_normalize_abbrev(stored))

    return {_normalize_abbrev(candidate) for candidate in candidates if candidate}


def _action_matches_team(action: Action, team_name: str) -> bool:
    if not action.team_abbrev.strip():
        return False
    return _normalize_abbrev(action.team_abbrev) in _team_abbrev_candidates(team_name)


def _build_event_payload(action: Action) -> ScoringEvent:
    return ScoringEvent(
        team="",
        goals_added=0,
        scorer=action.player_text,
        scorer_players=list(action.players),
        game_time=action.game_time,
    )


def _extract_new_scored_shootout_actions(
    previous_game: Game,
    current_game: Game,
    home_team: str,
    away_team: str,
) -> List[ScoringEvent]:
    new_actions = _extract_new_actions(previous_game, current_game)
    counts: dict = {
        home_team: {"count": 0, "last": None},
        away_team: {"count": 0, "last": None},
    }

    for action in new_actions:
        if action.event_type.upper() != "GWS":
            continue
        if (action.shot_outcome or "").lower() != "scored":
            continue

        target_team: Optional[str] = None
        if _action_matches_team(action, home_team):
            target_team = home_team
        elif _action_matches_team(action, away_team):
            target_team = away_team

        if target_team is None:
            continue

        counts[target_team]["count"] += 1
        if counts[target_team]["last"] is None:
            counts[target_team]["last"] = action

    results: List[ScoringEvent] = []
    for team in [home_team, away_team]:
        if counts[team]["count"] <= 0:
            continue
        last = counts[team]["last"]
        payload = _build_event_payload(last) if last is not None else ScoringEvent(team="", goals_added=0, scorer=None, scorer_players=None, game_time=None)
        results.append(ScoringEvent(
            team=team,
            goals_added=counts[team]["count"],
            scorer=payload.scorer,
            scorer_players=payload.scorer_players,
            game_time=payload.game_time,
        ))

    return results


def _find_scoring_event_for_team(
    previous_game: Game,
    current_game: Game,
    prev_score: Score,
    curr_score: Score,
    team_side: str,
    team_name: str,
) -> ScoringEvent:
    prev_goal_actions = _extract_goal_actions(previous_game)
    curr_goal_actions = _extract_goal_actions(current_game)

    prev_keys = {_goal_action_key(a) for a in prev_goal_actions if _goal_action_key(a) is not None}

    new_goals = [a for a in curr_goal_actions if _goal_action_key(a) not in prev_keys]

    prev_home = prev_score.home_score
    prev_away = prev_score.away_score
    curr_home = curr_score.home_score
    curr_away = curr_score.away_score
    team_delta = (curr_home if team_side == "home" else curr_away) - (prev_home if team_side == "home" else prev_away)

    if team_delta <= 0:
        return ScoringEvent(team="", goals_added=0, scorer=None, scorer_players=None, game_time=None)

    target_action: Optional[Action] = None

    if (curr_home - prev_home) + (curr_away - prev_away) == 1:
        for action in new_goals + curr_goal_actions:
            if action.goal and action.goal.home_score == curr_home and action.goal.away_score == curr_away:
                target_action = action
                break

    if target_action is None:
        for action in new_goals:
            if action.goal is None:
                continue
            if team_side == "home":
                if action.goal.home_score <= prev_home or action.goal.home_score > curr_home:
                    continue
            else:
                if action.goal.away_score <= prev_away or action.goal.away_score > curr_away:
                    continue
            target_action = action
            break

    if target_action is None:
        new_actions = _extract_new_actions(previous_game, current_game)
        for action in new_actions:
            if _action_matches_team(action, team_name):
                target_action = action
                break
        if target_action is None and new_actions:
            target_action = new_actions[0]

    if target_action is None:
        return ScoringEvent(team="", goals_added=0, scorer=None, scorer_players=None, game_time=None)

    payload = _build_event_payload(target_action)
    return ScoringEvent(team="", goals_added=0, scorer=payload.scorer, scorer_players=payload.scorer_players, game_time=payload.game_time)


def compare_game_score_change(previous_game: Game, current_game: Game) -> ScoreChangeResult:
    """Compare two snapshots of the same game and detect scoring changes.

    Identifies which teams scored, how many goals were added, and attributes
    goals to specific players when possible by analyzing action lists.

    Args:
        previous_game: The earlier game snapshot.
        current_game: The later game snapshot.

    Returns:
        A ScoreChangeResult indicating whether scoring occurred and details.

    Raises:
        CompareGameScoreChangeError: If comparison logic fails.
    """
    try:
        prev_score = _extract_score_pair(previous_game)
        curr_score = _extract_score_pair(current_game)

        home_team = current_game.game.home_team
        away_team = current_game.game.away_team

        scored: List[ScoringEvent] = []
        if curr_score.home_score > prev_score.home_score:
            event = _find_scoring_event_for_team(previous_game, current_game, prev_score, curr_score, "home", home_team)
            scored.append(ScoringEvent(
                team=home_team,
                goals_added=curr_score.home_score - prev_score.home_score,
                scorer=event.scorer,
                scorer_players=event.scorer_players,
                game_time=event.game_time,
            ))
        if curr_score.away_score > prev_score.away_score:
            event = _find_scoring_event_for_team(previous_game, current_game, prev_score, curr_score, "away", away_team)
            scored.append(ScoringEvent(
                team=away_team,
                goals_added=curr_score.away_score - prev_score.away_score,
                scorer=event.scorer,
                scorer_players=event.scorer_players,
                game_time=event.game_time,
            ))

        if not scored:
            scored.extend(_extract_new_scored_shootout_actions(previous_game, current_game, home_team, away_team))

        return ScoreChangeResult(
            scored=len(scored) > 0,
            teams_scored=scored,
            score=f"{curr_score.home_score}-{curr_score.away_score}",
            previous_score=f"{prev_score.home_score}-{prev_score.away_score}",
        )
    except CompareGameScoreChangeError:
        raise
    except Exception as exc:
        raise CompareGameScoreChangeError(f"compare_game_score_change failed: {exc}") from exc
