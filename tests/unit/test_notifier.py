"""Tests for notifier notification builders."""
from src.shl.notifier import _build_state_notification


class TestBuildStateNotification:
    def test_final_score_triggers_notification(self):
        payload = {"current_state": "Final Score", "score": "3 - 2"}
        result = _build_state_notification(payload)
        assert result is not None
        assert result["title"] == "🏁 Slutsignal"
        assert result["body"] == "Slutresultat: 3 - 2"

    def test_game_finished_triggers_notification(self):
        payload = {"current_state": "Game Finished", "score": "4 - 2"}
        result = _build_state_notification(payload)
        assert result is not None
        assert result["title"] == "🏁 Slutsignal"
        assert result["body"] == "Slutresultat: 4 - 2"

    def test_in_progress_status_returns_none(self):
        payload = {"current_state": "2nd period (15:30)", "score": "1 - 0"}
        result = _build_state_notification(payload)
        assert result is None

    def test_empty_state_returns_none(self):
        payload = {"current_state": "", "score": ""}
        result = _build_state_notification(payload)
        assert result is None
