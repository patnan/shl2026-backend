"""Shared helpers for router modules."""
from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timezone
from typing import Any, Dict


def _serialize(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    return value


def _meta() -> Dict[str, str]:
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _extract_game_ids(entries: list[Any]) -> list[int]:
    ids: list[int] = []
    for entry in entries:
        game_url = getattr(entry, "game_url", "")
        match = re.search(r"/(\d+)$", game_url)
        if match is None:
            continue
        ids.append(int(match.group(1)))
    return ids
