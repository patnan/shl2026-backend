import re
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

from src.shl.parsing import (
    clean_text,
)


class CalculateStandingsError(RuntimeError):
    pass


class ParseOverviewStandingsError(RuntimeError):
    pass


class ValidateSeasonStandingsError(RuntimeError):
    pass


def _extract_games_from_listing_with_progress(listing_url: str, progress_callback=None):
    from src.shl.api import extract_games_from_listing_with_progress as _impl

    return _impl(listing_url, progress_callback=progress_callback)


def _fetch_html(url: str, timeout: int = 20) -> str:
    from src.shl.api import fetch_html as _impl

    return _impl(url, timeout=timeout)


def _calculate_standings(games: List[Dict[str, object]]) -> List[Dict[str, object]]:
    from src.shl.api import calculate_standings as _impl

    return _impl(games)


def _parse_overview_standings_html(html: str) -> List[Dict[str, object]]:
    from src.shl.api import parse_overview_standings_html as _impl

    return _impl(html)


def _compare_standings(
    calculated_standings: List[Dict[str, object]], overview_standings: List[Dict[str, object]]
) -> List[Dict[str, object]]:
    from src.shl.api import compare_standings as _impl

    return _impl(calculated_standings, overview_standings)


def _build_validation_report(validation: Dict[str, object]) -> Dict[str, object]:
    from src.shl.api import build_validation_report as _impl

    return _impl(validation)


def _load_or_fetch_season_validation_inputs(
    season_id: int,
    cache_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    games: Optional[List[Dict[str, object]]] = None,
    overview_html: Optional[str] = None,
) -> Dict[str, object]:
    from src.shl.api import load_or_fetch_season_validation_inputs as _impl

    return _impl(
        season_id,
        cache_dir=cache_dir,
        progress_callback=progress_callback,
        games=games,
        overview_html=overview_html,
    )


def _validate_season_standings(
    season_id: int,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    games: Optional[List[Dict[str, object]]] = None,
    overview_html: Optional[str] = None,
) -> Dict[str, object]:
    from src.shl.api import validate_season_standings as _impl

    return _impl(season_id, progress_callback=progress_callback, games=games, overview_html=overview_html)


def _validate_multiple_seasons(
    season_ids: List[int],
    progress_callback_factory: Optional[Callable[[int, int, int], Optional[Callable[[int, int, str], None]]]] = None,
    games_by_season: Optional[Dict[int, List[Dict[str, object]]]] = None,
    overview_html_by_season: Optional[Dict[int, str]] = None,
    cache_dir: Optional[Path] = None,
) -> Dict[str, object]:
    from src.shl.api import validate_multiple_seasons as _impl

    return _impl(
        season_ids,
        progress_callback_factory=progress_callback_factory,
        games_by_season=games_by_season,
        overview_html_by_season=overview_html_by_season,
        cache_dir=cache_dir,
    )


def calculate_standings(games: List[Dict[str, object]]) -> List[Dict[str, object]]:
    try:
        standings: Dict[str, Dict[str, object]] = {}

        def ensure_team(team_name: str) -> Dict[str, object]:
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


def parse_overview_standings_html(html: str) -> List[Dict[str, object]]:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        heading = soup.find("h2", string=lambda value: value and clean_text(value) == "Group Standings")
        if heading is None:
            raise ParseOverviewStandingsError("Group Standings heading was not found")

        table = heading.find_parent("table", class_="tblContent")
        if table is None:
            raise ParseOverviewStandingsError("Group Standings table was not found")

        rows = table.find_all("tr", recursive=False)
        standings: List[Dict[str, object]] = []

        for row in rows:
            cells = row.find_all("td", recursive=False)
            if len(cells) < 12:
                continue

            values = [clean_text(cell.get_text(" ", strip=True)) for cell in cells]
            gf_ga_match = re.match(r"(\d+):(\d+)\s*\((-?\d+)\)", values[6])
            if gf_ga_match is None:
                raise ParseOverviewStandingsError(
                    f"Could not parse GF:GA (GD) value '{values[6]}' for team '{values[1]}'"
                )

            has_mobile_goal_difference_cell = len(values) >= 13
            tp_index = 8 if has_mobile_goal_difference_cell else 7
            otw_index = tp_index + 1
            otl_index = tp_index + 2
            gwsw_index = tp_index + 3
            gwsl_index = tp_index + 4

            standings.append(
                {
                    "rank": int(values[0]),
                    "team": values[1],
                    "games_played": int(values[2]),
                    "w": int(values[3]),
                    "t": int(values[4]),
                    "l": int(values[5]),
                    "goals_for": int(gf_ga_match.group(1)),
                    "goals_against": int(gf_ga_match.group(2)),
                    "goal_difference": int(gf_ga_match.group(3)),
                    "tp": int(values[tp_index]),
                    "otw": int(values[otw_index]),
                    "otl": int(values[otl_index]),
                    "gwsw": int(values[gwsw_index]),
                    "gwsl": int(values[gwsl_index]),
                }
            )

        if not standings:
            raise ParseOverviewStandingsError("No standings rows were found in Group Standings table")

        return standings
    except ParseOverviewStandingsError:
        raise
    except Exception as exc:
        raise ParseOverviewStandingsError(f"parse_overview_standings_html failed: {exc}") from exc


def compare_standings(
    calculated_standings: List[Dict[str, object]], overview_standings: List[Dict[str, object]]
) -> List[Dict[str, object]]:
    comparison_fields = [
        "rank",
        "games_played",
        "w",
        "t",
        "l",
        "goals_for",
        "goals_against",
        "goal_difference",
        "tp",
        "otw",
        "otl",
        "gwsw",
        "gwsl",
    ]

    mismatches: List[Dict[str, object]] = []
    calculated_by_team = {entry["team"]: entry for entry in calculated_standings}
    overview_by_team = {entry["team"]: entry for entry in overview_standings}

    all_teams = sorted(set(calculated_by_team) | set(overview_by_team))
    for team in all_teams:
        calculated_entry = calculated_by_team.get(team)
        overview_entry = overview_by_team.get(team)

        if calculated_entry is None or overview_entry is None:
            mismatches.append(
                {
                    "team": team,
                    "field": "team_presence",
                    "calculated": calculated_entry is not None,
                    "overview": overview_entry is not None,
                }
            )
            continue

        for field in comparison_fields:
            if calculated_entry.get(field) != overview_entry.get(field):
                mismatches.append(
                    {
                        "team": team,
                        "field": field,
                        "calculated": calculated_entry.get(field),
                        "overview": overview_entry.get(field),
                    }
                )

    calculated_order = [entry["team"] for entry in calculated_standings]
    overview_order = [entry["team"] for entry in overview_standings]
    if calculated_order != overview_order:
        mismatches.append(
            {
                "team": None,
                "field": "team_order",
                "calculated": calculated_order,
                "overview": overview_order,
            }
        )

    return mismatches


def build_validation_report(validation: Dict[str, object]) -> Dict[str, object]:
    mismatches = validation.get("mismatches", [])
    return {
        "season_id": validation["season_id"],
        "schedule_url": validation["schedule_url"],
        "overview_url": validation["overview_url"],
        "matches": validation["matches"],
        "mismatch_count": len(mismatches),
        "team_count": len(validation.get("overview_standings", [])),
        "mismatches": mismatches,
    }


def games_cache_path(cache_dir: Path, season_id: int) -> Path:
    return cache_dir / f"games_{season_id}.json"


def overview_cache_path(cache_dir: Path, season_id: int) -> Path:
    return cache_dir / f"overview_{season_id}.html"


def load_or_fetch_season_validation_inputs(
    season_id: int,
    cache_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    games: Optional[List[Dict[str, object]]] = None,
    overview_html: Optional[str] = None,
) -> Dict[str, object]:
    schedule_url = f"https://stats.swehockey.se/ScheduleAndResults/Schedule/{season_id}"
    overview_url = f"https://stats.swehockey.se/ScheduleAndResults/Overview/{season_id}"

    games_source = "provided" if games is not None else None
    overview_source = "provided" if overview_html is not None else None
    games_path = games_cache_path(cache_dir, season_id) if cache_dir is not None else None
    overview_path = overview_cache_path(cache_dir, season_id) if cache_dir is not None else None

    if games is None:
        if games_path is not None and games_path.exists():
            games = json.loads(games_path.read_text(encoding="utf-8"))
            games_source = "cache"
        else:
            games = _extract_games_from_listing_with_progress(schedule_url, progress_callback=progress_callback)
            games_source = "live"
            if games_path is not None:
                games_path.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")

    if overview_html is None:
        if overview_path is not None and overview_path.exists():
            overview_html = overview_path.read_text(encoding="utf-8")
            overview_source = "cache"
        else:
            overview_html = _fetch_html(overview_url)
            overview_source = "live"
            if overview_path is not None:
                overview_path.write_text(overview_html, encoding="utf-8")

    return {
        "games": games,
        "overview_html": overview_html,
        "games_source": games_source,
        "overview_source": overview_source,
        "games_cache_path": str(games_path) if games_path is not None else None,
        "overview_cache_path": str(overview_path) if overview_path is not None else None,
    }


def validate_season_standings(
    season_id: int,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    games: Optional[List[Dict[str, object]]] = None,
    overview_html: Optional[str] = None,
) -> Dict[str, object]:
    try:
        schedule_url = f"https://stats.swehockey.se/ScheduleAndResults/Schedule/{season_id}"
        overview_url = f"https://stats.swehockey.se/ScheduleAndResults/Overview/{season_id}"

        if games is None:
            games = _extract_games_from_listing_with_progress(schedule_url, progress_callback=progress_callback)
        if overview_html is None:
            overview_html = fetch_html(overview_url)

        calculated_standings = _calculate_standings(games)
        overview_standings = _parse_overview_standings_html(overview_html)
        mismatches = _compare_standings(calculated_standings, overview_standings)

        validation = {
            "season_id": season_id,
            "schedule_url": schedule_url,
            "overview_url": overview_url,
            "matches": len(mismatches) == 0,
            "mismatches": mismatches,
            "calculated_standings": calculated_standings,
            "overview_standings": overview_standings,
        }
        validation["report"] = _build_validation_report(validation)
        return validation
    except ValidateSeasonStandingsError:
        raise
    except Exception as exc:
        raise ValidateSeasonStandingsError(
            f"validate_season_standings failed for season_id '{season_id}': {exc}"
        ) from exc


def validate_multiple_seasons(
    season_ids: List[int],
    progress_callback_factory: Optional[Callable[[int, int, int], Optional[Callable[[int, int, str], None]]]] = None,
    games_by_season: Optional[Dict[int, List[Dict[str, object]]]] = None,
    overview_html_by_season: Optional[Dict[int, str]] = None,
    cache_dir: Optional[Path] = None,
) -> Dict[str, object]:
    results: List[Dict[str, object]] = []
    games_by_season = games_by_season or {}
    overview_html_by_season = overview_html_by_season or {}

    for index, season_id in enumerate(season_ids, start=1):
        progress_callback = None
        if progress_callback_factory is not None:
            progress_callback = progress_callback_factory(index, len(season_ids), season_id)

        try:
            season_inputs = _load_or_fetch_season_validation_inputs(
                season_id,
                cache_dir=cache_dir,
                progress_callback=progress_callback,
                games=games_by_season.get(season_id),
                overview_html=overview_html_by_season.get(season_id),
            )
            validation = _validate_season_standings(
                season_id,
                progress_callback=None,
                games=season_inputs["games"],
                overview_html=season_inputs["overview_html"],
            )
            report = _build_validation_report(validation)
            report["error"] = None
            report["games_source"] = season_inputs["games_source"]
            report["overview_source"] = season_inputs["overview_source"]
            report["games_cache_path"] = season_inputs["games_cache_path"]
            report["overview_cache_path"] = season_inputs["overview_cache_path"]
        except Exception as exc:
            report = {
                "season_id": season_id,
                "schedule_url": f"https://stats.swehockey.se/ScheduleAndResults/Schedule/{season_id}",
                "overview_url": f"https://stats.swehockey.se/ScheduleAndResults/Overview/{season_id}",
                "matches": False,
                "mismatch_count": None,
                "team_count": 0,
                "mismatches": [],
                "error": str(exc),
                "games_source": None,
                "overview_source": None,
                "games_cache_path": str(games_cache_path(cache_dir, season_id)) if cache_dir is not None else None,
                "overview_cache_path": str(overview_cache_path(cache_dir, season_id)) if cache_dir is not None else None,
            }

        results.append(report)

    successful_results = [result for result in results if result["error"] is None]
    failed_results = [result for result in results if result["error"] is not None]
    mismatching_results = [result for result in successful_results if not result["matches"]]

    return {
        "season_ids": season_ids,
        "total_seasons": len(season_ids),
        "successful_seasons": len(successful_results),
        "failed_seasons": len(failed_results),
        "matching_seasons": len([result for result in successful_results if result["matches"]]),
        "mismatching_seasons": len(mismatching_results),
        "all_match": len(failed_results) == 0 and len(mismatching_results) == 0,
        "results": results,
    }
