from typing import Dict, List


class CalculateStandingsError(RuntimeError):
    pass



def calculate_standings(games: List[Dict]) -> List[Dict]:
    try:
        standings: Dict[str, Dict] = {}

        def ensure_team(team_name: str) -> Dict:
            if team_name not in standings:
                standings[team_name] = {
                    "rank": 0,
                    "team": team_name,
                    "games_played": 0,
                    "wins_regulation": 0,
                    "wins_overtime": 0,
                    "wins_shootout": 0,
                    "wins_overtime_or_shootout": 0,
                    "losses_regulation": 0,
                    "losses_overtime": 0,
                    "losses_shootout": 0,
                    "losses_overtime_or_shootout": 0,
                    "tied_after_regulation": 0,
                    "unfinished_games": 0,
                    "points": 0,
                    "goals_for": 0,
                    "goals_against": 0,
                    "goal_difference": 0,
                    "w": 0,
                    "t": 0,
                    "l": 0,
                    "tp": 0,
                    "otw": 0,
                    "otl": 0,
                    "gwsw": 0,
                    "gwsl": 0,
                }
            return standings[team_name]

        for game in games:
            game_info = game.get("game")
            score_info = game.get("score")

            if not isinstance(game_info, dict) or not isinstance(score_info, dict):
                raise CalculateStandingsError("Each game must contain 'game' and 'score' dictionaries")

            home_team = game_info.get("home_team")
            away_team = game_info.get("away_team")
            home_score = score_info.get("home_score")
            away_score = score_info.get("away_score")

            if not isinstance(home_team, str) or not isinstance(away_team, str):
                raise CalculateStandingsError("Each game must include string home_team and away_team values")
            if not isinstance(home_score, int) or not isinstance(away_score, int):
                raise CalculateStandingsError("Each game must include integer home_score and away_score values")

            home_entry = ensure_team(home_team)
            away_entry = ensure_team(away_team)

            home_entry["games_played"] += 1
            away_entry["games_played"] += 1
            home_entry["goals_for"] += home_score
            home_entry["goals_against"] += away_score
            away_entry["goals_for"] += away_score
            away_entry["goals_against"] += home_score

            is_finished = score_info.get("state") == "Final Score"
            is_extra_time = bool(game_info.get("is_overtime") or game_info.get("is_shootout"))

            if not is_finished or home_score == away_score:
                home_entry["unfinished_games"] += 1
                away_entry["unfinished_games"] += 1
                home_entry["points"] += 1
                away_entry["points"] += 1
                continue

            winner_entry = home_entry if home_score > away_score else away_entry
            loser_entry = away_entry if home_score > away_score else home_entry

            if is_extra_time:
                home_entry["tied_after_regulation"] += 1
                away_entry["tied_after_regulation"] += 1
                winner_entry["wins_overtime_or_shootout"] += 1
                loser_entry["losses_overtime_or_shootout"] += 1
                winner_entry["points"] += 2
                loser_entry["points"] += 1

                if game_info.get("is_shootout"):
                    winner_entry["wins_shootout"] += 1
                    loser_entry["losses_shootout"] += 1
                else:
                    winner_entry["wins_overtime"] += 1
                    loser_entry["losses_overtime"] += 1
            else:
                winner_entry["wins_regulation"] += 1
                loser_entry["losses_regulation"] += 1
                winner_entry["points"] += 3

        for entry in standings.values():
            entry["goal_difference"] = entry["goals_for"] - entry["goals_against"]

        sorted_standings = sorted(
            standings.values(),
            key=lambda entry: (
                -entry["points"],
                -entry["goal_difference"],
                -entry["goals_for"],
                entry["team"],
            ),
        )

        for index, entry in enumerate(sorted_standings, start=1):
            entry["rank"] = index
            entry["w"] = entry["wins_regulation"]
            entry["t"] = entry["tied_after_regulation"]
            entry["l"] = entry["losses_regulation"]
            entry["tp"] = entry["points"]
            entry["otw"] = entry["wins_overtime"]
            entry["otl"] = entry["losses_overtime"]
            entry["gwsw"] = entry["wins_shootout"]
            entry["gwsl"] = entry["losses_shootout"]

        return sorted_standings
    except CalculateStandingsError:
        raise
    except Exception as exc:
        raise CalculateStandingsError(f"calculate_standings failed: {exc}") from exc



