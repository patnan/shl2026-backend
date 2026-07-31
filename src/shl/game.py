import re
from typing import Dict, List, Optional


class CompareGameScoreChangeError(RuntimeError):
    pass


def _extract_score_pair(game: Dict[str, object]) -> Dict[str, int]:
    score = game.get("score")
    if not isinstance(score, dict):
        raise CompareGameScoreChangeError("Game object is missing a 'score' dictionary")

    home_score = score.get("home_score")
    away_score = score.get("away_score")
    if isinstance(home_score, int) and isinstance(away_score, int):
        return {"home": home_score, "away": away_score}

    raw_score = score.get("current") or score.get("final")
    if not isinstance(raw_score, str):
        raise CompareGameScoreChangeError("Score must contain 'home_score'/'away_score' or 'current'/'final'")

    match = re.search(r"(\d+)\s*-\s*(\d+)", raw_score)
    if match is None:
        raise CompareGameScoreChangeError(f"Could not parse score from '{raw_score}'")

    return {"home": int(match.group(1)), "away": int(match.group(2))}


def _goal_action_key(action: Dict[str, object]) -> Optional[tuple]:
    goal = action.get("goal")
    if not isinstance(goal, dict):
        return None

    home_score = goal.get("home_score")
    away_score = goal.get("away_score")
    game_time = action.get("game_time")
    player_text = action.get("player_text")
    if not isinstance(home_score, int) or not isinstance(away_score, int):
        return None

    return (home_score, away_score, str(game_time), str(player_text))


def _extract_goal_actions(game: Dict[str, object]) -> List[Dict[str, object]]:
    actions = game.get("actions")
    if not isinstance(actions, list):
        return []

    goal_actions: List[Dict[str, object]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        key = _goal_action_key(action)
        if key is None:
            continue
        goal_actions.append(action)

    return goal_actions


def _action_key(action: Dict[str, object]) -> tuple:
    players = action.get("players")
    players_key = tuple(players) if isinstance(players, list) else ()
    return (
        str(action.get("period")),
        str(action.get("game_time")),
        str(action.get("event_type")),
        str(action.get("team_abbrev")),
        str(action.get("player_text")),
        players_key,
    )


def _extract_actions(game: Dict[str, object]) -> List[Dict[str, object]]:
    actions = game.get("actions")
    if not isinstance(actions, list):
        return []
    return [action for action in actions if isinstance(action, dict)]


def _extract_new_actions(previous_game: Dict[str, object], current_game: Dict[str, object]) -> List[Dict[str, object]]:
    prev_actions = _extract_actions(previous_game)
    curr_actions = _extract_actions(current_game)

    prev_counts: Dict[tuple, int] = {}
    for action in prev_actions:
        key = _action_key(action)
        prev_counts[key] = prev_counts.get(key, 0) + 1

    new_actions: List[Dict[str, object]] = []
    for action in curr_actions:
        key = _action_key(action)
        count = prev_counts.get(key, 0)
        if count > 0:
            prev_counts[key] = count - 1
            continue
        new_actions.append(action)

    return new_actions


def _normalize_abbrev(value: str) -> str:
    return re.sub(r"\W+", "", value, flags=re.UNICODE).upper()


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

    return {_normalize_abbrev(candidate) for candidate in candidates if candidate}


def _action_matches_team(action: Dict[str, object], team_name: str) -> bool:
    team_abbrev = action.get("team_abbrev")
    if not isinstance(team_abbrev, str) or not team_abbrev.strip():
        return False

    return _normalize_abbrev(team_abbrev) in _team_abbrev_candidates(team_name)


def _build_event_payload(action: Dict[str, object]) -> Dict[str, Optional[str]]:
    scorer = action.get("player_text") if isinstance(action.get("player_text"), str) else None
    scorer_players = action.get("players") if isinstance(action.get("players"), list) else None
    game_time = action.get("game_time") if isinstance(action.get("game_time"), str) else None
    return {"scorer": scorer, "scorer_players": scorer_players, "game_time": game_time}


def _extract_new_scored_shootout_actions(
    previous_game: Dict[str, object],
    current_game: Dict[str, object],
    home_team: str,
    away_team: str,
) -> List[Dict[str, object]]:
    new_actions = _extract_new_actions(previous_game, current_game)
    counts = {
        home_team: {"count": 0, "last": None},
        away_team: {"count": 0, "last": None},
    }

    for action in new_actions:
        if str(action.get("event_type", "")).upper() != "GWS":
            continue
        if str(action.get("shot_outcome", "")).lower() != "scored":
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

    results: List[Dict[str, object]] = []
    for team in [home_team, away_team]:
        if counts[team]["count"] <= 0:
            continue

        payload = _build_event_payload(counts[team]["last"]) if counts[team]["last"] is not None else {
            "scorer": None,
            "scorer_players": None,
            "game_time": None,
        }
        results.append(
            {
                "team": team,
                "goals_added": counts[team]["count"],
                "scorer": payload["scorer"],
                "scorer_players": payload["scorer_players"],
                "game_time": payload["game_time"],
            }
        )

    return results


def _find_scoring_event_for_team(
    previous_game: Dict[str, object],
    current_game: Dict[str, object],
    prev_score: Dict[str, int],
    curr_score: Dict[str, int],
    team_side: str,
    team_name: str,
) -> Dict[str, Optional[str]]:
    prev_goal_actions = _extract_goal_actions(previous_game)
    curr_goal_actions = _extract_goal_actions(current_game)

    prev_keys = set()
    for action in prev_goal_actions:
        key = _goal_action_key(action)
        if key is not None:
            prev_keys.add(key)

    new_goals: List[Dict[str, object]] = []
    for action in curr_goal_actions:
        key = _goal_action_key(action)
        if key is None:
            continue
        if key not in prev_keys:
            new_goals.append(action)

    team_delta = curr_score[team_side] - prev_score[team_side]
    if team_delta <= 0:
        return {"scorer": None, "scorer_players": None, "game_time": None}

    target_action: Optional[Dict[str, object]] = None

    if (curr_score["home"] - prev_score["home"]) + (curr_score["away"] - prev_score["away"]) == 1:
        for action in new_goals + curr_goal_actions:
            goal = action.get("goal")
            if not isinstance(goal, dict):
                continue
            if goal.get("home_score") == curr_score["home"] and goal.get("away_score") == curr_score["away"]:
                target_action = action
                break

    if target_action is None:
        for action in new_goals:
            goal = action.get("goal")
            if not isinstance(goal, dict):
                continue
            home_val = goal.get("home_score")
            away_val = goal.get("away_score")
            if not isinstance(home_val, int) or not isinstance(away_val, int):
                continue

            if team_side == "home":
                if home_val <= prev_score["home"] or home_val > curr_score["home"]:
                    continue
            else:
                if away_val <= prev_score["away"] or away_val > curr_score["away"]:
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
        return {"scorer": None, "scorer_players": None, "game_time": None}

    return _build_event_payload(target_action)


def compare_game_score_change(previous_game: Dict[str, object], current_game: Dict[str, object]) -> Dict[str, object]:
    try:
        prev_score = _extract_score_pair(previous_game)
        curr_score = _extract_score_pair(current_game)

        previous_game_info = previous_game.get("game")
        current_game_info = current_game.get("game")
        if not isinstance(previous_game_info, dict) or not isinstance(current_game_info, dict):
            raise CompareGameScoreChangeError("Both game objects must include a 'game' dictionary")

        home_team = current_game_info.get("home_team")
        away_team = current_game_info.get("away_team")
        if not isinstance(home_team, str) or not isinstance(away_team, str):
            raise CompareGameScoreChangeError("Both game objects must include string home_team and away_team")

        scored: List[Dict[str, object]] = []
        if curr_score["home"] > prev_score["home"]:
            event = _find_scoring_event_for_team(previous_game, current_game, prev_score, curr_score, "home", home_team)
            scored.append(
                {
                    "team": home_team,
                    "goals_added": curr_score["home"] - prev_score["home"],
                    "scorer": event["scorer"],
                    "scorer_players": event["scorer_players"],
                    "game_time": event["game_time"],
                }
            )
        if curr_score["away"] > prev_score["away"]:
            event = _find_scoring_event_for_team(previous_game, current_game, prev_score, curr_score, "away", away_team)
            scored.append(
                {
                    "team": away_team,
                    "goals_added": curr_score["away"] - prev_score["away"],
                    "scorer": event["scorer"],
                    "scorer_players": event["scorer_players"],
                    "game_time": event["game_time"],
                }
            )

        if not scored:
            scored.extend(_extract_new_scored_shootout_actions(previous_game, current_game, home_team, away_team))

        return {
            "scored": len(scored) > 0,
            "teams_scored": scored,
            "score": f"{curr_score['home']}-{curr_score['away']}",
            "previous_score": f"{prev_score['home']}-{prev_score['away']}",
        }
    except CompareGameScoreChangeError:
        raise
    except Exception as exc:
        raise CompareGameScoreChangeError(f"compare_game_score_change failed: {exc}") from exc
