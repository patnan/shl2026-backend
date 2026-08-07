import re
from pathlib import Path
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup

from src.shl.models import (
    Action, Game, GameInfo, GoalDetail, PenaltyMetadata, PenaltyTimeRange,
    PimStats, PpStats, SaveStats, Score, ShotStats, TeamStats,
)


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


def parse_total_and_periods(total_text: str, period_text: str) -> Tuple[int, List[int]]:
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


def parse_score_block(score_cell_text: str) -> Score:
    try:
        final_match = re.search(r"(\d+\s*-\s*\d+)", score_cell_text)
        period_match = re.search(r"\((\s*\d+\s*-\s*\d+(?:\s*,\s*\d+\s*-\s*\d+)*\s*)\)", score_cell_text)
        state_match = re.search(r"\b(Final Score)\b", score_cell_text, flags=re.IGNORECASE)
        # Live games show period state instead of "Final Score", e.g. "2nd period 03:22"
        if not state_match:
            state_match = re.search(r"(\d+(?:st|nd|rd|th)\s+period(?:\s+\d{1,2}:\d{2})?)", score_cell_text, flags=re.IGNORECASE)

        if not final_match:
            raise ParseScoreBlockError(f"Could not parse final score from: {score_cell_text}")

        home_score_text, away_score_text = [part.strip() for part in final_match.group(1).split("-", 1)]
        period_scores = []
        if period_match:
            period_scores = [part.strip().replace(" ", "") for part in period_match.group(1).split(",")]

        return Score(
            current=f"{home_score_text}-{away_score_text}",
            home_score=int(home_score_text),
            away_score=int(away_score_text),
            periods=period_scores,
            current_period=len(period_scores) if period_scores else None,
            state=state_match.group(1).strip() if state_match else None,
        )
    except ParseScoreBlockError:
        raise
    except Exception as exc:
        raise ParseScoreBlockError(f"parse_score_block failed: {exc}") from exc


def split_teams(title_text: str) -> Tuple[str, str]:
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
            # Require Shots/Saves/PIM/PP but allow either "Final Score" or live state
            # (e.g. "1st period", "2nd period", "3rd period").
            if not all(key in text for key in ["Shots", "Saves", "PIM", "PP"]):
                continue

            direct_rows = table.find_all("tr", recursive=False)
            if len(direct_rows) < 8:
                continue

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
        return [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"], recursive=False)]
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

            candidates.append((table, len(direct_rows)))

        if not candidates:
            return None

        return max(candidates, key=lambda item: item[1])[0]
    except FindActionsTableError:
        raise
    except Exception as exc:
        raise FindActionsTableError(f"find_actions_table failed: {exc}") from exc


def parse_players(player_cell_text: str) -> Tuple[List[str], List[int]]:
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


def parse_goal_event_type(event_type: str) -> Optional[GoalDetail]:
    try:
        match = re.match(r"^\s*(\d+\s*-\s*\d+)\s*\(([^)]+)\)\s*(.*)$", event_type)
        if not match:
            return None
        home_score_text, away_score_text = [part.strip() for part in match.group(1).split("-", 1)]
        return GoalDetail(
            home_score=int(home_score_text),
            away_score=int(away_score_text),
            strength=match.group(2).strip(),
            qualifier=match.group(3).strip() or None,
        )
    except ParseGoalEventTypeError:
        raise
    except Exception as exc:
        raise ParseGoalEventTypeError(f"parse_goal_event_type failed for '{event_type}': {exc}") from exc


def extract_penalty_metadata(player_text: str) -> PenaltyMetadata:
    try:
        text = clean_text(player_text)
        time_match = re.search(r"\(([^)]*)\)\s*$", text)
        time_range_raw = time_match.group(1) if time_match else None
        text_without_range = clean_text(text[:time_match.start()]) if time_match else text

        time_range: Optional[PenaltyTimeRange] = None
        if time_range_raw and "-" in time_range_raw:
            start, end = [clean_text(part) for part in time_range_raw.split("-", 1)]
            time_range = PenaltyTimeRange(start=start or None, end=end or None)

        if text_without_range.lower().startswith("team penalty"):
            reason = clean_text(text_without_range[len("Team penalty"):])
            return PenaltyMetadata(
                clean_player_text="Team penalty",
                players=[],
                player_numbers=[],
                reason=reason or None,
                time_range=time_range,
            )

        numbered_match = re.match(r"^(\d{1,2})\.\s(.+)$", text_without_range)
        if not numbered_match:
            players, player_numbers = parse_players(text_without_range)
            return PenaltyMetadata(
                clean_player_text=text_without_range,
                players=players,
                player_numbers=player_numbers,
                reason=None,
                time_range=time_range,
            )

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

        return PenaltyMetadata(
            clean_player_text=player_name,
            players=[player_name],
            player_numbers=[jersey_number],
            reason=reason,
            time_range=time_range,
        )
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
            f"infer_missing_period_label failed for period='{current_period}', game_time='{game_time}', score_period_count='{score_period_count}': {exc}"
        ) from exc


def _build_shootout_event_from_subsection_row(
    cells: List[str],
    subsection: str,
    score_period_count: Optional[int],
) -> Optional[Action]:
    if len(cells) < 4:
        return None

    period_label = "period 5" if score_period_count and score_period_count >= 5 else "shootout"

    if subsection == "game winning shot":
        event_type_cell = cells[1]
        team_abbrev = cells[2]
        player_text = cells[3]
        goal_data = parse_goal_event_type(event_type_cell)
        players, player_numbers = parse_players(player_text)
        return Action(
            period=period_label,
            game_time="65:00",
            event_type="goal" if goal_data is not None else "GWS",
            team_abbrev=team_abbrev,
            player_text=player_text,
            players=players,
            player_numbers=player_numbers,
            is_goal=goal_data is not None,
            goal=goal_data,
            event_detail=event_type_cell,
        )

    outcome = clean_text(cells[0]).lower()
    if outcome not in {"scored", "missed"}:
        return None

    score_cell = cells[1]
    team_abbrev = cells[2]
    player_text = cells[3]
    players, player_numbers = parse_players(player_text)

    goal: Optional[GoalDetail] = None
    score_match = re.search(r"(\d+)\s*-\s*(\d+)", score_cell)
    if score_match and outcome == "scored":
        goal = GoalDetail(
            home_score=int(score_match.group(1)),
            away_score=int(score_match.group(2)),
            strength="GWS",
            qualifier=outcome,
        )

    return Action(
        period=period_label,
        game_time="65:00",
        event_type="GWS",
        team_abbrev=team_abbrev,
        player_text=player_text,
        players=players,
        player_numbers=player_numbers,
        is_goal=outcome == "scored",
        shot_outcome=outcome,
        event_detail=score_cell,
        goal=goal,
    )


def _is_missed_penalty_shot(text: str) -> bool:
    return "missed penalty shot" in clean_text(text).lower()


def parse_actions(html: str, score_period_count: Optional[int] = None) -> List[Action]:
    try:
        soup = BeautifulSoup(html, "html.parser")
        table = find_actions_table(soup)
        if table is None:
            return []

        rows = table.find_all("tr", recursive=False)
        events: List[Action] = []
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

            penalty_meta: Optional[PenaltyMetadata] = None
            if event_type == "penalty":
                penalty_meta = extract_penalty_metadata(player_text)
                player_text = penalty_meta.clean_player_text
                players = penalty_meta.players
                player_numbers = penalty_meta.player_numbers

            events.append(Action(
                period=infer_missing_period_label(current_period, game_time, score_period_count),
                game_time=game_time,
                event_type=event_type,
                team_abbrev=team_abbrev,
                player_text=player_text,
                players=players,
                player_numbers=player_numbers,
                is_goal=goal_data is not None or ps_is_goal,
                goal=goal_data,
                event_detail=event_detail,
                penalty_reason=penalty_meta.reason if penalty_meta else None,
                penalty_time_range=penalty_meta.time_range if penalty_meta else None,
            ))

        return events
    except ParseActionsError:
        raise
    except Exception as exc:
        raise ParseActionsError(f"parse_actions failed: {exc}") from exc


def parse_top_stats(html: str) -> Game:
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
        home_saves_total, home_saves_periods = parse_total_and_periods(saves_cells[1], saves_cells[2])
        away_saves_total, away_saves_periods = parse_total_and_periods(saves_cells[4], saves_cells[5])
        home_pim_total, home_pim_periods = parse_total_and_periods(pim_cells[1], pim_cells[2])
        away_pim_total, away_pim_periods = parse_total_and_periods(pim_cells[5], pim_cells[6])
        home_pp_time_match = re.search(r"\(([^)]+)\)", pp_cells[2])
        away_pp_time_match = re.search(r"\(([^)]+)\)", pp_cells[5])

        is_overtime = len(score.periods) > 3
        is_shootout = len(score.periods) > 4

        return Game(
            game=GameInfo(
                home_team=home_team,
                away_team=away_team,
                is_overtime=is_overtime,
                is_shootout=is_shootout,
                date_time=meta_cells[0] if len(meta_cells) > 0 else None,
                league=meta_cells[1] if len(meta_cells) > 1 else None,
                arena=meta_cells[2] if len(meta_cells) > 2 else None,
            ),
            score=score,
            teams={
                home_team: TeamStats(
                    shots=ShotStats(total=home_shots_total, by_period=home_shots_periods, percentage=shots_percentage_cells[1]),
                    saves=SaveStats(total=home_saves_total, by_period=home_saves_periods, percentage=saves_percentage_cells[1]),
                    pim=PimStats(total=home_pim_total, by_period=home_pim_periods),
                    pp=PpStats(percentage=pp_cells[1], time=home_pp_time_match.group(1) if home_pp_time_match else pp_cells[2]),
                ),
                away_team: TeamStats(
                    shots=ShotStats(total=away_shots_total, by_period=away_shots_periods, percentage=shots_percentage_cells[3]),
                    saves=SaveStats(total=away_saves_total, by_period=away_saves_periods, percentage=saves_percentage_cells[3]),
                    pim=PimStats(total=away_pim_total, by_period=away_pim_periods),
                    pp=PpStats(percentage=pp_cells[4], time=away_pp_time_match.group(1) if away_pp_time_match else pp_cells[5]),
                ),
            },
            actions=[],
        )
    except ParseTopStatsError:
        raise
    except Exception as exc:
        raise ParseTopStatsError(f"parse_top_stats failed: {exc}") from exc


