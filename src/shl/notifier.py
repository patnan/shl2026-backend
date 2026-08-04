"""Notification worker that processes domain events and sends FCM push notifications.

Configuration (environment variables):
    GOOGLE_APPLICATION_CREDENTIALS  Path to Firebase service account JSON key file.
                                    Required for firebase-admin to initialize.
    SHL_FCM_DRY_RUN                 Set to "1" to log notifications without sending.
                                    Useful for testing without Firebase credentials.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from time import sleep as _sleep
from typing import Any, Dict, List

from src.shl.store import (
    list_device_tokens,
    list_unprocessed_domain_events,
    mark_domain_event_processed,
)

logger = logging.getLogger(__name__)

_fcm_initialized = False


def _ensure_fcm() -> bool:
    """Initialize Firebase Admin SDK (once). Returns True if ready."""
    global _fcm_initialized
    if _fcm_initialized:
        return True

    if os.environ.get("SHL_FCM_DRY_RUN") == "1":
        logger.info("FCM dry-run mode enabled — notifications will be logged only")
        _fcm_initialized = True
        return True

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        logger.error("GOOGLE_APPLICATION_CREDENTIALS not set — cannot send FCM notifications")
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred = credentials.Certificate(creds_path)
            firebase_admin.initialize_app(cred)

        _fcm_initialized = True
        return True
    except Exception as exc:
        logger.error("Failed to initialize Firebase Admin SDK: %s", exc)
        return False


def _build_goal_notification(payload: Dict[str, Any]) -> Dict[str, str]:
    """Build notification title and body from a score_changed event payload."""
    score = payload.get("score", "?-?")
    teams_scored = payload.get("teams_scored", [])

    # Build title: "⚽ Team A 2 - 1 Team B" style isn't possible without
    # knowing both teams. Use the score and scoring team.
    scorers = []
    for event in teams_scored:
        team = event.get("team", "")
        scorer = event.get("scorer")
        game_time = event.get("game_time")
        parts = [team]
        if scorer:
            parts.append(scorer)
        if game_time:
            parts.append(f"({game_time})")
        scorers.append(" ".join(parts))

    title = f"⚽ Mål! {score}"
    body = " | ".join(scorers) if scorers else f"Score: {score}"

    return {"title": title, "body": body}


def _build_state_notification(payload: Dict[str, Any]) -> Dict[str, str] | None:
    """Build notification for game state changes (e.g. game ended)."""
    current_state = payload.get("current_state", "")
    score = payload.get("score", "?-?")

    if current_state == "Final Score":
        return {
            "title": "🏁 Slutsignal",
            "body": f"Slutresultat: {score}",
        }
    return None


def _send_fcm_notifications(tokens: List[str], title: str, body: str, data: Dict[str, str] | None = None) -> None:
    """Send a notification to all registered device tokens."""
    if not tokens:
        logger.info("No registered devices — skipping notification")
        return

    dry_run = os.environ.get("SHL_FCM_DRY_RUN") == "1"

    if dry_run:
        logger.info("DRY-RUN FCM: title=%r body=%r tokens=%d", title, body, len(tokens))
        return

    from firebase_admin import messaging

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        tokens=tokens,
    )

    try:
        response = messaging.send_each_for_multicast(message)
        logger.info(
            "FCM sent: success=%d failure=%d",
            response.success_count,
            response.failure_count,
        )
    except Exception as exc:
        logger.error("FCM send failed: %s", exc)


def _process_event(cache_dir: Path, event) -> None:
    """Process a single domain event and send appropriate notification."""
    tokens = list_device_tokens(cache_dir)

    if event.event_type == "score_changed":
        notif = _build_goal_notification(event.payload)
        _send_fcm_notifications(
            tokens,
            notif["title"],
            notif["body"],
            data={"event_type": "score_changed", "payload": json.dumps(event.payload, ensure_ascii=False)},
        )

    elif event.event_type == "game_state_changed":
        notif = _build_state_notification(event.payload)
        if notif:
            _send_fcm_notifications(
                tokens,
                notif["title"],
                notif["body"],
                data={"event_type": "game_state_changed", "payload": json.dumps(event.payload, ensure_ascii=False)},
            )


def run_notification_worker(
    cache_dir: Path,
    tick_interval_seconds: float = 5.0,
    max_ticks: int | None = None,
) -> Dict[str, Any]:
    """Run the notification worker loop.

    Reads unprocessed score_changed and game_state_changed events,
    sends FCM push notifications, and marks events as processed.

    Args:
        cache_dir: Path to the cache/database directory.
        tick_interval_seconds: Seconds between checking for new events.
        max_ticks: Stop after N ticks (None = run forever).

    Returns:
        Summary dict with counts of processed events.
    """
    if not _ensure_fcm():
        logger.error("Cannot start notification worker — FCM not configured")
        return {"error": "FCM not configured", "events_processed": 0}

    ticks = 0
    events_processed = 0
    events_skipped = 0

    logger.info("Notification worker started (tick_interval=%.1fs)", tick_interval_seconds)

    while True:
        events = list_unprocessed_domain_events(cache_dir, limit=50)

        for event in events:
            if event.event_type in ("score_changed", "game_state_changed"):
                try:
                    _process_event(cache_dir, event)
                    events_processed += 1
                except Exception as exc:
                    logger.error("Failed to process event %d: %s", event.id, exc)
            else:
                events_skipped += 1

            mark_domain_event_processed(cache_dir, event.id)

        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break

        _sleep(tick_interval_seconds)

    summary = {
        "ticks": ticks,
        "events_processed": events_processed,
        "events_skipped": events_skipped,
    }
    logger.info("Notification worker stopped: %s", json.dumps(summary))
    return summary
