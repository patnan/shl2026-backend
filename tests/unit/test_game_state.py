"""Tests for ScheduleEntry.game_state computed property."""
from src.shl.models import ScheduleEntry


def _entry(**kwargs) -> ScheduleEntry:
    """Helper to create a ScheduleEntry with defaults."""
    defaults = dict(
        date="2026-08-07", time="16:00", home_team="Team A", away_team="Team B",
        game_result="", periods="", spectators="", venue="", game_url="", round="",
        status="", game_clock="", current_period="",
    )
    defaults.update(kwargs)
    return ScheduleEntry(**defaults)


class TestGameState:
    def test_not_started_no_status(self):
        assert _entry().game_state == "not_started"

    def test_not_started_waiting_for_first(self):
        assert _entry(status="Waiting for 1st period").game_state == "not_started"

    def test_ongoing_with_clock(self):
        e = _entry(game_result="1 - 0", status="1st period (15:24)",
                   game_clock="15:24", current_period="1st period")
        assert e.game_state == "ongoing"

    def test_ongoing_2nd_period(self):
        e = _entry(game_result="2 - 1", status="2nd period (10:00)",
                   game_clock="10:00", current_period="2nd period")
        assert e.game_state == "ongoing"

    def test_ongoing_3rd_period(self):
        e = _entry(game_result="2 - 1", status="3rd period (01:47)",
                   game_clock="01:47", current_period="3rd period",
                   periods="(1-0, 0-1, 1-0)")
        assert e.game_state == "ongoing"

    def test_ongoing_powerplay(self):
        e = _entry(game_result="1 - 2", status="Powerplay (5 on 4) for MIF (14:36)",
                   game_clock="14:36", current_period="")
        assert e.game_state == "ongoing"

    def test_intermission_waiting_2nd(self):
        e = _entry(game_result="1 - 1", status="Waiting for 2nd period")
        assert e.game_state == "intermission"

    def test_intermission_waiting_3rd(self):
        e = _entry(game_result="2 - 1", status="Waiting for 3rd period")
        assert e.game_state == "intermission"

    def test_intermission_period_ended(self):
        e = _entry(game_result="1 - 0", status="1st period ended")
        assert e.game_state == "intermission"

    def test_finished_game_finished(self):
        e = _entry(game_result="4 - 2", status="Game Finished",
                   periods="(1-1, 2-1, 1-0)")
        assert e.game_state == "finished"

    def test_finished_final_score(self):
        e = _entry(game_result="3 - 1", status="Final Score",
                   periods="(1-0, 1-1, 1-0)")
        assert e.game_state == "finished"

    def test_finished_overtime(self):
        e = _entry(game_result="3 - 2", status="Final Score",
                   periods="(1-1, 1-1, 0-0, 1-0)")
        assert e.game_state == "finished_overtime"

    def test_finished_shootout(self):
        e = _entry(game_result="3 - 2", status="Game Finished",
                   periods="(1-1, 0-1, 1-0, 0-0, 1-0)")
        assert e.game_state == "finished_shootout"

    def test_overtime_4th_period(self):
        e = _entry(game_result="2 - 2", status="4th period (03:00)",
                   game_clock="03:00", current_period="4th period",
                   periods="(1-1, 1-1, 0-0)")
        assert e.game_state == "overtime"

    def test_shootout_5th_period(self):
        e = _entry(game_result="2 - 2", status="5th period (00:00)",
                   game_clock="00:00", current_period="5th period",
                   periods="(1-1, 1-1, 0-0, 0-0)")
        assert e.game_state == "shootout"

    def test_to_dict_includes_game_state(self):
        e = _entry(game_result="1 - 0", status="2nd period (10:00)",
                   game_clock="10:00", current_period="2nd period")
        d = e.to_dict()
        assert d["game_state"] == "ongoing"
        assert d["overtime"] == ""

    def test_to_dict_finished_overtime(self):
        e = _entry(game_result="3 - 2", status="Final Score",
                   periods="(1-1, 1-1, 0-0, 1-0)")
        d = e.to_dict()
        assert d["game_state"] == "finished_overtime"
        assert d["overtime"] == "OT"
