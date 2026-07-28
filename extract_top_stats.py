#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


class GameScrapeError(RuntimeError):
    pass


class CleanTextError(GameScrapeError):
    pass


class FormatPeriodLabelError(GameScrapeError):
    pass


class ParsePeriodValuesError(GameScrapeError):
    pass


class ParseTotalAndPeriodsError(GameScrapeError):
    pass


class ParseScoreBlockError(GameScrapeError):
    pass


class SplitTeamsError(GameScrapeError):
    pass


class FindTopStatsTableError(GameScrapeError):
    pass


class RowCellsError(GameScrapeError):
    pass


class FindActionsTableError(GameScrapeError):
    pass


class ParsePlayersError(GameScrapeError):
    pass


class ParseGoalEventTypeError(GameScrapeError):
    pass


class ExtractPenaltyMetadataError(GameScrapeError):
    pass


class InferMissingPeriodLabelError(GameScrapeError):
    pass


class ParseActionsError(GameScrapeError):
    pass


class ParseTopStatsError(GameScrapeError):
    pass


class FetchHtmlError(GameScrapeError):
    pass


class ExtractGameUrlsFromListingHtmlError(GameScrapeError):
    pass


class ExtractGameError(GameScrapeError):
    pass


class ExtractGamesFromListingError(GameScrapeError):
    pass


class ExtractGamesFromListingWithProgressError(GameScrapeError):
    pass


class ExtractGameUrlsFromListingHtmlByDateError(GameScrapeError):
    pass


class ExtractGamesFromListingByDateError(GameScrapeError):
    pass


class LoadGameObjectFromFileError(GameScrapeError):
    pass


class CompareGameScoreChangeError(GameScrapeError):
    pass


class CalculateStandingsError(GameScrapeError):
    pass


class ParseOverviewStandingsError(GameScrapeError):
    pass


class ValidateSeasonStandingsError(GameScrapeError):
    pass


class MainExecutionError(GameScrapeError):
    pass


@dataclass
class TeamStats:
    shots_total: int
    shots_by_period: List[int]
    saves_total: int
    saves_by_period: List[int]
    pim_total: int
    pim_by_period: List[int]
    pp_percentage: str
    pp_time: str


PENALTY_REASON_START_WORDS = {
    "Abuse",
    "Boarding",
    "Charging",
    "Checking",
    "Crosschecking",
    "Delay",
    "Diving",
    "Elbowing",
    "Fighting",
    "High",
    "Holding",
    "Hooking",
    "Illegal",
    "Interference",
    "Kneeing",
    "Roughing",
    "Slashing",
    "Spearing",
    "Too",
    "Tripping",
    "Unsportsmanlike",
}


def clean_text(value: str) -> str:
    try:
        return re.sub(r"\s+", " ", value).strip()
    except CleanTextError:
        raise
    except Exception as exc:
        raise CleanTextError(f"clean_text failed: {exc}") from exc


def format_period_label(period_number: int) -> str:
    try:
        if period_number == 1:
            return "1st period"
        if period_number == 2:
            return "2nd period"
        if period_number == 3:
            return "3rd period"
        return f"period {period_number}"
    except FormatPeriodLabelError:
        raise
    except Exception as exc:
        raise FormatPeriodLabelError(f"format_period_label failed: {exc}") from exc


def parse_period_values(text: str) -> List[int]:
    try:
        numbers = re.findall(r"\d+", text)
        return [int(x) for x in numbers]
    except ParsePeriodValuesError:
        raise
    except Exception as exc:
        raise ParsePeriodValuesError(f"parse_period_values failed for '{text}': {exc}") from exc


def parse_total_and_periods(total_text: str, period_text: str) -> (int, List[int]):
    try:
        total_match = re.search(r"\d+", total_text)
        if not total_match:
            raise ParseTotalAndPeriodsError(f"Could not parse total from: {total_text}")
        total = int(total_match.group(0))
        periods = parse_period_values(period_text)
        return total, periods
    except ParseTotalAndPeriodsError:
        raise
    except Exception as exc:
        raise ParseTotalAndPeriodsError(
            f"parse_total_and_periods failed for total='{total_text}', periods='{period_text}': {exc}"
        ) from exc


def parse_score_block(score_cell_text: str) -> Dict[str, object]:
    try:
        final_match = re.search(r"(\d+\s*-\s*\d+)", score_cell_text)
        period_match = re.search(r"\((\s*\d+\s*-\s*\d+(?:\s*,\s*\d+\s*-\s*\d+)+\s*)\)", score_cell_text)
        state_match = re.search(r"\b(Final Score)\b", score_cell_text, flags=re.IGNORECASE)

        if not final_match:
            raise ParseScoreBlockError(f"Could not parse final score from: {score_cell_text}")

        home_score_text, away_score_text = [part.strip() for part in final_match.group(1).split("-", 1)]
        current_score = f"{home_score_text}-{away_score_text}"
        period_scores = []
        if period_match:
            period_scores = [part.strip().replace(" ", "") for part in period_match.group(1).split(",")]

        current_period = len(period_scores) if period_scores else None

        return {
            "current": current_score,
            "home_score": int(home_score_text),
            "away_score": int(away_score_text),
            "periods": period_scores,
            "current_period": current_period,
            "state": state_match.group(1).title() if state_match else None,
        }
    except ParseScoreBlockError:
        raise
    except Exception as exc:
        raise ParseScoreBlockError(f"parse_score_block failed: {exc}") from exc


def split_teams(title_text: str) -> (str, str):
    try:
        parts = [clean_text(x) for x in title_text.split("-")]
        if len(parts) < 2:
            raise SplitTeamsError(f"Could not parse team names from title: {title_text}")
        home_team = parts[0]
        away_team = "-".join(parts[1:]).strip()
        return home_team, away_team
    except SplitTeamsError:
        raise
    except Exception as exc:
        raise SplitTeamsError(f"split_teams failed for '{title_text}': {exc}") from exc


def find_top_stats_table(soup: BeautifulSoup):
    try:
        candidates = []
        for table in soup.find_all("table"):
            text = clean_text(table.get_text(" ", strip=True))
            if not all(key in text for key in ["Final Score", "Shots", "Saves", "PIM", "PP"]):
                continue

            direct_rows = table.find_all("tr", recursive=False)
            if len(direct_rows) < 8:
                continue

            # Prefer the innermost compact table that directly contains the 8 top stats rows.
            candidates.append((table, len(direct_rows)))

        if not candidates:
            return None

        return min(candidates, key=lambda item: item[1])[0]
    except FindTopStatsTableError:
        raise
    except Exception as exc:
        raise FindTopStatsTableError(f"find_top_stats_table failed: {exc}") from exc


def row_cells(row) -> List[str]:
    try:
        return [
            clean_text(cell.get_text(" ", strip=True))
            for cell in row.find_all(["td", "th"], recursive=False)
        ]
    except RowCellsError:
        raise
    except Exception as exc:
        raise RowCellsError(f"row_cells failed: {exc}") from exc


def find_actions_table(soup: BeautifulSoup):
    try:
        candidates = []
        for table in soup.find_all("table"):
            direct_rows = table.find_all("tr", recursive=False)
            if len(direct_rows) < 2:
                continue

            first_row_cells = row_cells(direct_rows[0])
            if not first_row_cells:
                continue
            if "Actions" not in " ".join(first_row_cells):
                continue

            table_text = clean_text(table.get_text(" ", strip=True))
            if "Last update:" not in table_text:
                continue

            # Prefer the largest direct-row table because it contains the full event list.
            candidates.append((table, len(direct_rows)))

        if not candidates:
            return None

        return max(candidates, key=lambda item: item[1])[0]
    except FindActionsTableError:
        raise
    except Exception as exc:
        raise FindActionsTableError(f"find_actions_table failed: {exc}") from exc


def parse_players(player_cell_text: str) -> (List[str], List[int]):
    try:
        if not player_cell_text:
            return [], []

        main_part = player_cell_text
        if "Pos. Part.:" in main_part:
            main_part = main_part.split("Pos. Part.:", 1)[0].strip()

        if not main_part:
            return [], []

        player_entries: List[str] = []
        player_numbers: List[int] = []

        # Match players like "28. Lastname, Firstname ..." and avoid splitting inside multi-digit numbers.
        for match in re.finditer(r"(?:^|\s)(\d{1,2})\.\s(.*?)(?=(?:\s+\d{1,2}\.\s)|$)", main_part):
            number = int(match.group(1))
            details = clean_text(match.group(2))
            player_entries.append(f"{number}. {details}")
            player_numbers.append(number)

        if player_entries:
            return player_entries, player_numbers

        return [main_part], []
    except ParsePlayersError:
        raise
    except Exception as exc:
        raise ParsePlayersError(f"parse_players failed for '{player_cell_text}': {exc}") from exc


def parse_goal_event_type(event_type: str) -> Optional[Dict[str, object]]:
    try:
        match = re.match(r"^\s*(\d+\s*-\s*\d+)\s*\(([^)]+)\)\s*(.*)$", event_type)
        if not match:
            return None

        home_score_text, away_score_text = [part.strip() for part in match.group(1).split("-", 1)]

        return {
            "home_score": int(home_score_text),
            "away_score": int(away_score_text),
            "strength": match.group(2).strip(),
            "qualifier": match.group(3).strip() or None,
        }
    except ParseGoalEventTypeError:
        raise
    except Exception as exc:
        raise ParseGoalEventTypeError(f"parse_goal_event_type failed for '{event_type}': {exc}") from exc


def extract_penalty_metadata(player_text: str) -> Dict[str, Optional[object]]:
    try:
        text = clean_text(player_text)
        time_match = re.search(r"\(([^)]*)\)\s*$", text)
        time_range_raw = time_match.group(1) if time_match else None
        text_without_range = clean_text(text[:time_match.start()]) if time_match else text

        time_range = None
        if time_range_raw and "-" in time_range_raw:
            start, end = [clean_text(part) for part in time_range_raw.split("-", 1)]
            time_range = {"start": start or None, "end": end or None}

        if text_without_range.lower().startswith("team penalty"):
            reason = clean_text(text_without_range[len("Team penalty"):])
            return {
                "clean_player_text": "Team penalty",
                "players": [],
                "player_numbers": [],
                "reason": reason or None,
                "time_range": time_range,
            }

        numbered_match = re.match(r"^(\d{1,2})\.\s(.+)$", text_without_range)
        if not numbered_match:
            players, player_numbers = parse_players(text_without_range)
            return {
                "clean_player_text": text_without_range,
                "players": players,
                "player_numbers": player_numbers,
                "reason": None,
                "time_range": time_range,
            }

        jersey_number = int(numbered_match.group(1))
        remainder = numbered_match.group(2)

        if "," in remainder:
            last_name, rest = remainder.split(",", 1)
            rest_tokens = clean_text(rest).split()
            reason_start_index = None
            for i, token in enumerate(rest_tokens):
                if token in PENALTY_REASON_START_WORDS:
                    reason_start_index = i
                    break

            if reason_start_index is None:
                first_name_tokens = rest_tokens
                reason_tokens = []
            else:
                first_name_tokens = rest_tokens[:reason_start_index]
                reason_tokens = rest_tokens[reason_start_index:]

            player_name = f"{jersey_number}. {clean_text(last_name)}, {' '.join(first_name_tokens).strip()}".strip()
            reason = clean_text(" ".join(reason_tokens)) if reason_tokens else None
        else:
            player_name = f"{jersey_number}. {remainder}"
            reason = None

        return {
            "clean_player_text": player_name,
            "players": [player_name],
            "player_numbers": [jersey_number],
            "reason": reason,
            "time_range": time_range,
        }
    except ExtractPenaltyMetadataError:
        raise
    except Exception as exc:
        raise ExtractPenaltyMetadataError(f"extract_penalty_metadata failed for '{player_text}': {exc}") from exc


def infer_missing_period_label(
    current_period: Optional[str],
    game_time: str,
    score_period_count: Optional[int],
) -> Optional[str]:
    try:
        time_match = re.match(r"^(\d{2}):(\d{2})$", game_time)
        if not time_match:
            return current_period

        minute = int(time_match.group(1))
        if minute < 60:
            return current_period

        if score_period_count is not None and score_period_count >= 5 and minute >= 65:
            return "period 5"

        return "period 4"
    except InferMissingPeriodLabelError:
        raise
    except Exception as exc:
        raise InferMissingPeriodLabelError(
            f"infer_missing_period_label failed for period='{current_period}', game_time='{game_time}', "
            f"score_period_count='{score_period_count}': {exc}"
        ) from exc


def _parse_score_pair_text(score_text: str) -> Optional[Dict[str, int]]:
    match = re.search(r"(\d+)\s*-\s*(\d+)", score_text)
    if not match:
        return None
    return {"home_score": int(match.group(1)), "away_score": int(match.group(2))}


def _build_shootout_event_from_subsection_row(
    cells: List[str],
    subsection: str,
    score_period_count: Optional[int],
) -> Optional[Dict[str, object]]:
    if len(cells) < 4:
        return None

    period_label = "period 5" if score_period_count and score_period_count >= 5 else "shootout"

    # "Game Winning Shot" has rows like: "", "4-3 (GWS)", "BIF", "52. Name..."
    if subsection == "game winning shot":
        event_type_cell = cells[1]
        team_abbrev = cells[2]
        player_text = cells[3]
        goal_data = parse_goal_event_type(event_type_cell)
        players, player_numbers = parse_players(player_text)

        event: Dict[str, object] = {
            "period": period_label,
            "game_time": "65:00",
            "event_type": "goal" if goal_data is not None else "GWS",
            "team_abbrev": team_abbrev,
            "player_text": player_text,
            "players": players,
            "player_numbers": player_numbers,
            "is_goal": goal_data is not None,
            "event_detail": event_type_cell,
        }
        if goal_data is not None:
            event["goal"] = goal_data
        return event

    # "Game Winning Shots" has rows like: "Scored|Missed", "1 - 0", "BIF", "52. Name vs. goalie..."
    outcome = clean_text(cells[0]).lower()
    if outcome not in {"scored", "missed"}:
        return None

    score_cell = cells[1]
    team_abbrev = cells[2]
    player_text = cells[3]
    players, player_numbers = parse_players(player_text)
    goal_score = _parse_score_pair_text(score_cell)

    event = {
        "period": period_label,
        "game_time": "65:00",
        "event_type": "GWS",
        "team_abbrev": team_abbrev,
        "player_text": player_text,
        "players": players,
        "player_numbers": player_numbers,
        "is_goal": outcome == "scored",
        "shot_outcome": outcome,
        "event_detail": score_cell,
    }
    if goal_score is not None and outcome == "scored":
        event["goal"] = {
            "home_score": goal_score["home_score"],
            "away_score": goal_score["away_score"],
            "strength": "GWS",
            "qualifier": outcome,
        }
    return event


def _is_missed_penalty_shot(text: str) -> bool:
    return "missed penalty shot" in clean_text(text).lower()


def parse_actions(html: str, score_period_count: Optional[int] = None) -> List[Dict[str, object]]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        table = find_actions_table(soup)
        if table is None:
            return []

        rows = table.find_all("tr", recursive=False)
        events: List[Dict[str, object]] = []
        current_period: Optional[str] = None
        current_subsection: Optional[str] = None

        for row in rows:
            cells = row_cells(row)
            if not cells:
                continue

            if len(cells) == 1:
                header = clean_text(cells[0]).lower()
                if re.match(r"^\d+(st|nd|rd|th)\s+period$", cells[0], flags=re.IGNORECASE):
                    current_period = cells[0]
                    current_subsection = None
                elif header in {"overtime", "game winning shot", "game winning shots"}:
                    current_subsection = header
                    if header in {"game winning shot", "game winning shots"} and score_period_count and score_period_count >= 5:
                        current_period = "period 5"
                continue

            if current_subsection in {"game winning shot", "game winning shots"}:
                shootout_event = _build_shootout_event_from_subsection_row(cells, current_subsection, score_period_count)
                if shootout_event is not None:
                    events.append(shootout_event)
                    continue

            if len(cells) < 4:
                continue

            game_time, raw_event_type, team_abbrev, player_text = cells[0], cells[1], cells[2], cells[3]
            if len(cells) > 4:
                # Some PS rows include result detail in extra cells (e.g., "Missed Penalty Shot").
                player_text = clean_text(" ".join([player_text] + cells[4:]))
            if not re.match(r"^\d{2}:\d{2}$", game_time):
                continue

            event_type = raw_event_type
            event_detail: Optional[str] = None
            if re.match(r"^\d+\s*min$", raw_event_type, flags=re.IGNORECASE):
                event_type = "penalty"
                event_detail = raw_event_type

            players, player_numbers = parse_players(player_text)
            goal_data = parse_goal_event_type(raw_event_type)
            if goal_data is not None:
                event_type = "goal"
                event_detail = raw_event_type

            ps_is_goal = False
            if raw_event_type.strip().upper() == "PS":
                ps_is_goal = not _is_missed_penalty_shot(player_text)

            penalty_meta = None
            if event_type == "penalty":
                penalty_meta = extract_penalty_metadata(player_text)
                player_text = penalty_meta["clean_player_text"]
                players = penalty_meta["players"]
                player_numbers = penalty_meta["player_numbers"]

            inferred_period = infer_missing_period_label(current_period, game_time, score_period_count)
            event = {
                "period": inferred_period,
                "game_time": game_time,
                "event_type": event_type,
                "team_abbrev": team_abbrev,
                "player_text": player_text,
                "players": players,
                "player_numbers": player_numbers,
                "is_goal": goal_data is not None or ps_is_goal,
            }
            if event_detail is not None:
                event["event_detail"] = event_detail
            if penalty_meta is not None:
                event["penalty_reason"] = penalty_meta["reason"]
                event["penalty_time_range"] = penalty_meta["time_range"]
            if goal_data is not None:
                event["goal"] = goal_data

            events.append(event)

        return events
    except ParseActionsError:
        raise
    except Exception as exc:
        raise ParseActionsError(f"parse_actions failed: {exc}") from exc


def parse_top_stats(html: str) -> Dict[str, object]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        table = find_top_stats_table(soup)
        if table is None:
            raise ParseTopStatsError("Top stats table was not found")

        rows = table.find_all("tr", recursive=False)
        if len(rows) < 8:
            raise ParseTopStatsError("Top stats table does not have the expected row count")

        title_cells = row_cells(rows[0])
        if not title_cells:
            raise ParseTopStatsError("Missing title row")
        home_team, away_team = split_teams(title_cells[0])

        meta_cells = row_cells(rows[1])
        game_meta = {
            "date_time": meta_cells[0] if len(meta_cells) > 0 else None,
            "league": meta_cells[1] if len(meta_cells) > 1 else None,
            "arena": meta_cells[2] if len(meta_cells) > 2 else None,
        }

        shots_cells = row_cells(rows[2])
        shots_percentage_cells = row_cells(rows[3])
        saves_cells = row_cells(rows[4])
        saves_percentage_cells = row_cells(rows[5])
        pim_cells = row_cells(rows[6])
        pp_cells = row_cells(rows[7])

        if len(shots_cells) < 7:
            raise ParseTopStatsError("Shots row does not have the expected structure")
        if len(shots_percentage_cells) < 4:
            raise ParseTopStatsError("Shots percentage row does not have the expected structure")
        if len(saves_cells) < 6:
            raise ParseTopStatsError("Saves row does not have the expected structure")
        if len(saves_percentage_cells) < 4:
            raise ParseTopStatsError("Saves percentage row does not have the expected structure")
        if len(pim_cells) < 7:
            raise ParseTopStatsError("PIM row does not have the expected structure")
        if len(pp_cells) < 6:
            raise ParseTopStatsError("PP row does not have the expected structure")

        score = parse_score_block(shots_cells[3])

        home_shots_total, home_shots_periods = parse_total_and_periods(shots_cells[1], shots_cells[2])
        away_shots_total, away_shots_periods = parse_total_and_periods(shots_cells[5], shots_cells[6])
        home_shots_percentage = shots_percentage_cells[1]
        away_shots_percentage = shots_percentage_cells[3]

        home_saves_total, home_saves_periods = parse_total_and_periods(saves_cells[1], saves_cells[2])
        away_saves_total, away_saves_periods = parse_total_and_periods(saves_cells[4], saves_cells[5])
        home_saves_percentage = saves_percentage_cells[1]
        away_saves_percentage = saves_percentage_cells[3]

        home_pim_total, home_pim_periods = parse_total_and_periods(pim_cells[1], pim_cells[2])
        away_pim_total, away_pim_periods = parse_total_and_periods(pim_cells[5], pim_cells[6])

        home_pp_percentage = pp_cells[1]
        away_pp_percentage = pp_cells[4]

        home_pp_time_match = re.search(r"\(([^)]+)\)", pp_cells[2])
        away_pp_time_match = re.search(r"\(([^)]+)\)", pp_cells[5])

        home_stats = TeamStats(
        shots_total=home_shots_total,
        shots_by_period=home_shots_periods,
        saves_total=home_saves_total,
        saves_by_period=home_saves_periods,
        pim_total=home_pim_total,
        pim_by_period=home_pim_periods,
        pp_percentage=home_pp_percentage,
        pp_time=home_pp_time_match.group(1) if home_pp_time_match else pp_cells[2],
    )

        away_stats = TeamStats(
        shots_total=away_shots_total,
        shots_by_period=away_shots_periods,
        saves_total=away_saves_total,
        saves_by_period=away_saves_periods,
        pim_total=away_pim_total,
        pim_by_period=away_pim_periods,
        pp_percentage=away_pp_percentage,
        pp_time=away_pp_time_match.group(1) if away_pp_time_match else pp_cells[5],
    )

        period_count = len(score.get("periods", []))
        is_overtime = period_count > 3
        is_shootout = period_count > 4

        return {
            "game": {
                "home_team": home_team,
                "away_team": away_team,
                "is_overtime": is_overtime,
                "is_shootout": is_shootout,
                **game_meta,
            },
            "score": score,
            "teams": {
                home_team: {
                    "shots": {
                        "total": home_stats.shots_total,
                        "by_period": home_stats.shots_by_period,
                        "percentage": home_shots_percentage,
                    },
                    "saves": {
                        "total": home_stats.saves_total,
                        "by_period": home_stats.saves_by_period,
                        "percentage": home_saves_percentage,
                    },
                    "pim": {
                        "total": home_stats.pim_total,
                        "by_period": home_stats.pim_by_period,
                    },
                    "pp": {
                        "percentage": home_stats.pp_percentage,
                        "time": home_stats.pp_time,
                    },
                },
                away_team: {
                    "shots": {
                        "total": away_stats.shots_total,
                        "by_period": away_stats.shots_by_period,
                        "percentage": away_shots_percentage,
                    },
                    "saves": {
                        "total": away_stats.saves_total,
                        "by_period": away_stats.saves_by_period,
                        "percentage": away_saves_percentage,
                    },
                    "pim": {
                        "total": away_stats.pim_total,
                        "by_period": away_stats.pim_by_period,
                    },
                    "pp": {
                        "percentage": away_stats.pp_percentage,
                        "time": away_stats.pp_time,
                    },
                },
            },
        }
    except ParseTopStatsError:
        raise
    except Exception as exc:
        raise ParseTopStatsError(f"parse_top_stats failed: {exc}") from exc


def fetch_html(url: str, timeout: int = 20) -> str:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text
    except FetchHtmlError:
        raise
    except Exception as exc:
        raise FetchHtmlError(f"fetch_html failed for '{url}': {exc}") from exc


def extract_game_urls_from_listing_html(html: str, base_url: str) -> List[str]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        urls: List[str] = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            match = re.search(r"/Game/Events/\d+", href)
            if not match:
                continue

            canonical = urljoin(base_url, match.group(0))
            if canonical in seen:
                continue

            seen.add(canonical)
            urls.append(canonical)

        return urls
    except ExtractGameUrlsFromListingHtmlError:
        raise
    except Exception as exc:
        raise ExtractGameUrlsFromListingHtmlError(
            f"extract_game_urls_from_listing_html failed for base_url '{base_url}': {exc}"
        ) from exc


def extract_game_urls_from_listing_html_by_date(html: str, base_url: str, game_date: str) -> List[str]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        urls: List[str] = []
        seen = set()
        current_date: Optional[str] = None

        for row in soup.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if not cells:
                continue

            date_text = clean_text(cells[0].get_text(" ", strip=True))
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
            if date_match is not None:
                current_date = date_match.group(0)

            if current_date != game_date:
                continue

            for link in row.find_all("a", href=True):
                href = link["href"].strip()
                match = re.search(r"/Game/Events/\d+", href)
                if not match:
                    continue

                canonical = urljoin(base_url, match.group(0))
                if canonical in seen:
                    continue

                seen.add(canonical)
                urls.append(canonical)

        return urls
    except ExtractGameUrlsFromListingHtmlByDateError:
        raise
    except Exception as exc:
        raise ExtractGameUrlsFromListingHtmlByDateError(
            f"extract_game_urls_from_listing_html_by_date failed for date '{game_date}' and base_url '{base_url}': {exc}"
        ) from exc


def extract_game(url: str) -> Dict[str, object]:
    try:
        html = fetch_html(url)
        stats = parse_top_stats(html)
        stats["actions"] = parse_actions(html, score_period_count=len(stats.get("score", {}).get("periods", [])))
        return stats
    except ExtractGameError:
        raise
    except Exception as exc:
        raise ExtractGameError(f"extract_game failed for '{url}': {exc}") from exc


def extract_game_by_id(game_id: int) -> Dict[str, object]:
    try:
        normalized_id = int(game_id)
        if normalized_id <= 0:
            raise ValueError("game_id must be a positive integer")

        return extract_game(f"https://stats.swehockey.se/Game/Events/{normalized_id}")
    except ExtractGameError:
        raise
    except Exception as exc:
        raise ExtractGameError(f"extract_game_by_id failed for '{game_id}': {exc}") from exc


def extract_games_from_listing(listing_url: str) -> List[Dict[str, object]]:
    try:
        return extract_games_from_listing_with_progress(listing_url)
    except ExtractGamesFromListingError:
        raise
    except Exception as exc:
        raise ExtractGamesFromListingError(
            f"extract_games_from_listing failed for '{listing_url}': {exc}"
        ) from exc


def extract_games_from_listing_with_progress(
    listing_url: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> List[Dict[str, object]]:
    try:
        listing_html = fetch_html(listing_url)
        game_urls = extract_game_urls_from_listing_html(listing_html, base_url=listing_url)

        if not game_urls:
            raise ExtractGamesFromListingWithProgressError(
                f"No game event links were found on listing page: {listing_url}"
            )

        results: List[Dict[str, object]] = []
        total = len(game_urls)
        for index, game_url in enumerate(game_urls, start=1):
            if progress_callback is not None:
                progress_callback(index, total, game_url)
            try:
                results.append(extract_game(game_url))
            except Exception as exc:
                raise ExtractGamesFromListingWithProgressError(
                    f"Failed to scrape game '{game_url}' from listing page '{listing_url}': {exc}"
                ) from exc

        return results
    except ExtractGamesFromListingWithProgressError:
        raise
    except Exception as exc:
        raise ExtractGamesFromListingWithProgressError(
            f"extract_games_from_listing_with_progress failed for '{listing_url}': {exc}"
        ) from exc


def extract_games_from_listing_by_date(listing_url: str, game_date: str) -> List[Dict[str, object]]:
    try:
        listing_html = fetch_html(listing_url)
        game_urls = extract_game_urls_from_listing_html_by_date(listing_html, base_url=listing_url, game_date=game_date)

        if not game_urls:
            return []

        results: List[Dict[str, object]] = []
        for game_url in game_urls:
            try:
                results.append(extract_game(game_url))
            except Exception as exc:
                raise ExtractGamesFromListingByDateError(
                    f"Failed to scrape game '{game_url}' for date '{game_date}' from listing page '{listing_url}': {exc}"
                ) from exc

        return results
    except ExtractGamesFromListingByDateError:
        raise
    except Exception as exc:
        raise ExtractGamesFromListingByDateError(
            f"extract_games_from_listing_by_date failed for listing_url '{listing_url}' and game_date '{game_date}': {exc}"
        ) from exc


def load_game_object_from_file(file_path: str) -> Dict[str, object]:
    try:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise LoadGameObjectFromFileError(f"File '{file_path}' does not contain a JSON object")
        return data
    except LoadGameObjectFromFileError:
        raise
    except Exception as exc:
        raise LoadGameObjectFromFileError(f"load_game_object_from_file failed for '{file_path}': {exc}") from exc


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

    # Common case: exactly one goal was added between snapshots.
    if (curr_score["home"] - prev_score["home"]) + (curr_score["away"] - prev_score["away"]) == 1:
        for action in new_goals + curr_goal_actions:
            goal = action.get("goal")
            if not isinstance(goal, dict):
                continue
            if goal.get("home_score") == curr_score["home"] and goal.get("away_score") == curr_score["away"]:
                target_action = action
                break

    # Fallback for larger jumps: pick the latest new goal compatible with this team's increase.
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

        # Shootout progress can include scored attempts in Game Winning Shots rows
        # even when the main game score text has not changed yet.
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


def compare_game_score_change_from_files(previous_file_path: str, current_file_path: str) -> Dict[str, object]:
    try:
        previous_game = load_game_object_from_file(previous_file_path)
        current_game = load_game_object_from_file(current_file_path)
        return compare_game_score_change(previous_game, current_game)
    except (LoadGameObjectFromFileError, CompareGameScoreChangeError):
        raise
    except Exception as exc:
        raise CompareGameScoreChangeError(
            f"compare_game_score_change_from_files failed for '{previous_file_path}' and '{current_file_path}': {exc}"
        ) from exc


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
            games = extract_games_from_listing_with_progress(schedule_url, progress_callback=progress_callback)
            games_source = "live"
            if games_path is not None:
                games_path.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")

    if overview_html is None:
        if overview_path is not None and overview_path.exists():
            overview_html = overview_path.read_text(encoding="utf-8")
            overview_source = "cache"
        else:
            overview_html = fetch_html(overview_url)
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
            games = extract_games_from_listing_with_progress(schedule_url, progress_callback=progress_callback)
        if overview_html is None:
            overview_html = fetch_html(overview_url)

        calculated_standings = calculate_standings(games)
        overview_standings = parse_overview_standings_html(overview_html)
        mismatches = compare_standings(calculated_standings, overview_standings)

        validation = {
            "season_id": season_id,
            "schedule_url": schedule_url,
            "overview_url": overview_url,
            "matches": len(mismatches) == 0,
            "mismatches": mismatches,
            "calculated_standings": calculated_standings,
            "overview_standings": overview_standings,
        }
        validation["report"] = build_validation_report(validation)
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
            season_inputs = load_or_fetch_season_validation_inputs(
                season_id,
                cache_dir=cache_dir,
                progress_callback=progress_callback,
                games=games_by_season.get(season_id),
                overview_html=overview_html_by_season.get(season_id),
            )
            validation = validate_season_standings(
                season_id,
                progress_callback=None,
                games=season_inputs["games"],
                overview_html=season_inputs["overview_html"],
            )
            report = build_validation_report(validation)
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


def main() -> None:
    try:
        parser = argparse.ArgumentParser(description="Extract top section stats from swehockey game events page")
        parser.add_argument(
            "url",
            nargs="?",
            default="https://stats.swehockey.se/Game/Events/1004840",
            help="Game events URL",
        )
        parser.add_argument(
            "--game-id",
            type=int,
            help="Game id (for example: 1004357). Overrides positional URL when provided.",
        )
        args = parser.parse_args()

        if args.game_id is not None:
            stats = extract_game_by_id(args.game_id)
        else:
            stats = extract_game(args.url)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    except MainExecutionError:
        raise
    except Exception as exc:
        raise MainExecutionError(f"main failed: {exc}") from exc


if __name__ == "__main__":
    main()
