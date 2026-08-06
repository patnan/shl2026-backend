"""SHL.se API client and SweHockey ↔ shl.se mapping functions.

Bridges SweHockey team/player names to shl.se data (logos, portraits, UUIDs).
Uses the Sportality platform API at www.shl.se/api/ with header x-s8y-instance-id.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from src.shl.store import (
    load_shl_se_player,
    load_shl_se_team_players,
    save_shl_se_player,
    get_shl_se_player_fetched_at,
)

_logger = logging.getLogger(__name__)

SHL_SE_API_BASE = "https://www.shl.se/api"
SHL_SE_INSTANCE_ID = "shl1_shl"
_DEFAULT_TIMEOUT = 10


def _headers() -> Dict[str, str]:
    return {
        "accept": "application/json",
        "x-s8y-instance-id": SHL_SE_INSTANCE_ID,
    }


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShlSeTeam:
    """Team data from shl.se."""

    uuid: str
    team_code: str
    instance_id: str
    name_short: str
    name_long: str
    name_full: str
    logo_url: str

    @classmethod
    def from_api(cls, data: dict) -> ShlSeTeam:
        names = data.get("teamNames", {})
        return cls(
            uuid=data["uuid"],
            team_code=data.get("teamCode", ""),
            instance_id=data.get("instanceId", data.get("ownerInstanceId", "")),
            name_short=names.get("short", ""),
            name_long=names.get("long", ""),
            name_full=names.get("full", ""),
            logo_url=data.get("logo", "") or data.get("icon", ""),
        )


@dataclass(frozen=True)
class ShlSePlayer:
    """Player data from shl.se."""

    uuid: str
    first_name: str
    last_name: str
    full_name: str
    jersey_number: int
    nationality: str
    position: str
    position_code: str
    portrait_url: str


# ---------------------------------------------------------------------------
# API fetch functions
# ---------------------------------------------------------------------------


def fetch_shl_se_teams(timeout: int = _DEFAULT_TIMEOUT) -> List[ShlSeTeam]:
    """Fetch all SHL teams from shl.se/api/site/settings."""
    url = f"{SHL_SE_API_BASE}/site/settings"
    r = httpx.get(url, headers=_headers(), timeout=timeout)
    r.raise_for_status()
    settings = r.json()
    teams_raw = settings.get("teamsInSite", [])
    return [ShlSeTeam.from_api(t) for t in teams_raw]


def fetch_shl_se_roster(team_uuid: str, timeout: int = _DEFAULT_TIMEOUT) -> List[ShlSePlayer]:
    """Fetch player roster for a team from shl.se."""
    url = f"{SHL_SE_API_BASE}/sports-v2/athletes/by-team-uuid/{team_uuid}"
    r = httpx.get(url, headers=_headers(), timeout=timeout)
    r.raise_for_status()
    groups = r.json()

    players: List[ShlSePlayer] = []
    for group in groups:
        position = group.get("position", "")
        position_code = group.get("positionCode", "")
        for p in group.get("players", []):
            portrait_url = ""
            rendered = p.get("renderedLatestPortrait") or {}
            if rendered.get("url"):
                portrait_url = rendered["url"]
            elif p.get("portraitList"):
                first_portrait = p["portraitList"][0]
                rendered_media = first_portrait.get("renderedMedia", {})
                portrait_url = rendered_media.get("url", "")

            players.append(ShlSePlayer(
                uuid=p.get("uuid", ""),
                first_name=p.get("firstName", ""),
                last_name=p.get("lastName", ""),
                full_name=p.get("fullName", ""),
                jersey_number=p.get("jerseyNumber", 0),
                nationality=p.get("nationality", ""),
                position=position,
                position_code=position_code,
                portrait_url=portrait_url,
            ))
    return players


# ---------------------------------------------------------------------------
# Mapping: SweHockey → shl.se
# ---------------------------------------------------------------------------


class TeamMapper:
    """Maps between SweHockey team names and shl.se team data.

    The mapping algorithm uses shl.se's short team name (e.g. "Frölunda",
    "Skellefteå") which is always a substring of SweHockey's full team name
    (e.g. "Frölunda HC", "Skellefteå AIK"). This works dynamically without
    hardcoded mappings.
    """

    def __init__(self, shl_se_teams: List[ShlSeTeam]) -> None:
        self._shl_teams = shl_se_teams
        # Pre-build lookup: normalized short name → team
        self._short_to_team: Dict[str, ShlSeTeam] = {}
        for team in shl_se_teams:
            self._short_to_team[team.name_short] = team

    @classmethod
    def from_api(cls, timeout: int = _DEFAULT_TIMEOUT) -> TeamMapper:
        """Create a TeamMapper by fetching current teams from shl.se."""
        teams = fetch_shl_se_teams(timeout=timeout)
        return cls(teams)

    def swehockey_to_shl_se(self, swehockey_team_name: str) -> Optional[ShlSeTeam]:
        """Map a SweHockey team name to shl.se team data.

        Uses substring matching: shl.se short name ⊂ SweHockey full name.
        Fallback: normalized space-removal for "HV 71" vs "HV71".
        """
        for team in self._shl_teams:
            if team.name_short in swehockey_team_name:
                return team
        # Fallback: strip spaces (handles "HV 71" vs "HV71")
        normalized = swehockey_team_name.replace(" ", "")
        for team in self._shl_teams:
            if team.name_long.replace(" ", "") == normalized:
                return team
        return None

    def shl_se_to_swehockey(self, shl_se_team: ShlSeTeam, swehockey_team_names: List[str]) -> Optional[str]:
        """Map shl.se team back to the SweHockey team name.

        Requires the list of known SweHockey team names (from schedule/standings).
        """
        for swh_name in swehockey_team_names:
            if shl_se_team.name_short in swh_name:
                return swh_name
        # Fallback: strip spaces
        for swh_name in swehockey_team_names:
            if swh_name.replace(" ", "") == shl_se_team.name_long.replace(" ", ""):
                return swh_name
        return None

    def get_team_by_code(self, team_code: str) -> Optional[ShlSeTeam]:
        """Get shl.se team by teamCode (e.g. 'FHC', 'SAIK')."""
        for team in self._shl_teams:
            if team.team_code == team_code:
                return team
        return None

    def get_team_by_uuid(self, uuid: str) -> Optional[ShlSeTeam]:
        """Get shl.se team by UUID."""
        for team in self._shl_teams:
            if team.uuid == uuid:
                return team
        return None

    @property
    def teams(self) -> List[ShlSeTeam]:
        return list(self._shl_teams)


# ---------------------------------------------------------------------------
# Mapping: SweHockey player → shl.se player (via jersey + team)
# ---------------------------------------------------------------------------


class PlayerMapper:
    """Maps SweHockey players to shl.se player data using (jersey_number, team) as key.

    Usage:
        team_mapper = TeamMapper.from_api()
        player_mapper = PlayerMapper(team_mapper)
        player_mapper.load_team("Skellefteå AIK")

        # Now look up a SweHockey player
        shl_player = player_mapper.find("Skellefteå AIK", 24)
        # → ShlSePlayer(full_name="Oscar Lindberg", portrait_url="...", ...)
    """

    def __init__(self, team_mapper: TeamMapper) -> None:
        self._team_mapper = team_mapper
        # Cache: swehockey_team_name → {jersey_number → ShlSePlayer}
        self._rosters: Dict[str, Dict[int, ShlSePlayer]] = {}

    def load_team(self, swehockey_team_name: str, timeout: int = _DEFAULT_TIMEOUT) -> bool:
        """Load the shl.se roster for a SweHockey team. Returns True if successful."""
        shl_team = self._team_mapper.swehockey_to_shl_se(swehockey_team_name)
        if not shl_team:
            _logger.warning("No shl.se team match for '%s'", swehockey_team_name)
            return False

        try:
            players = fetch_shl_se_roster(shl_team.uuid, timeout=timeout)
        except Exception as exc:
            _logger.error("Failed to fetch roster for %s: %s", shl_team.uuid, exc)
            return False

        by_jersey: Dict[int, ShlSePlayer] = {}
        for p in players:
            if p.jersey_number > 0:
                by_jersey[p.jersey_number] = p
        self._rosters[swehockey_team_name] = by_jersey
        return True

    def load_all_teams(self, swehockey_team_names: List[str], timeout: int = _DEFAULT_TIMEOUT) -> int:
        """Load rosters for all teams. Returns count of successfully loaded teams."""
        loaded = 0
        for name in swehockey_team_names:
            if self.load_team(name, timeout=timeout):
                loaded += 1
        return loaded

    def find(self, swehockey_team_name: str, jersey_number: int) -> Optional[ShlSePlayer]:
        """Find shl.se player by SweHockey team name + jersey number."""
        roster = self._rosters.get(swehockey_team_name)
        if roster is None:
            return None
        return roster.get(jersey_number)

    def get_portrait_url(self, swehockey_team_name: str, jersey_number: int) -> Optional[str]:
        """Get player portrait URL. Returns None if not found."""
        player = self.find(swehockey_team_name, jersey_number)
        return player.portrait_url if player else None

    def get_team_logo_url(self, swehockey_team_name: str) -> Optional[str]:
        """Get team logo URL from shl.se."""
        shl_team = self._team_mapper.swehockey_to_shl_se(swehockey_team_name)
        return shl_team.logo_url if shl_team else None

    def is_loaded(self, swehockey_team_name: str) -> bool:
        """Check if a team's roster has been loaded."""
        return swehockey_team_name in self._rosters

    @property
    def loaded_teams(self) -> List[str]:
        """List of SweHockey team names with loaded rosters."""
        return list(self._rosters.keys())


# ---------------------------------------------------------------------------
# Lazy singleton for TeamMapper
# ---------------------------------------------------------------------------

_team_mapper_instance: Optional[TeamMapper] = None


def _get_team_mapper() -> TeamMapper:
    """Get or create the module-level TeamMapper singleton (lazy initialization)."""
    global _team_mapper_instance
    if _team_mapper_instance is None:
        _team_mapper_instance = TeamMapper.from_api()
    return _team_mapper_instance


# ---------------------------------------------------------------------------
# Portrait download
# ---------------------------------------------------------------------------


def download_portrait(portrait_url: str, cache_dir: Path, team_code: str, jersey: int) -> Optional[str]:
    """Download player portrait and save to cache/portraits/{team_code}_{jersey}.png.

    Returns relative path from cache_dir if successful, None otherwise.
    """
    if not portrait_url:
        return None

    portraits_dir = cache_dir / "portraits"
    portraits_dir.mkdir(parents=True, exist_ok=True)

    relative_path = f"portraits/{team_code}_{jersey}.png"
    dest = cache_dir / relative_path

    try:
        r = httpx.get(portrait_url, timeout=15, follow_redirects=True)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return relative_path
    except Exception as exc:
        _logger.warning("Failed to download portrait %s: %s", portrait_url, exc)
        return None


# ---------------------------------------------------------------------------
# Player data helpers
# ---------------------------------------------------------------------------


def _player_to_dict(player: ShlSePlayer, team_code: str, portrait_path: Optional[str]) -> dict:
    """Convert ShlSePlayer + extras into the standard dict representation."""
    return {
        "first_name": player.first_name,
        "last_name": player.last_name,
        "full_name": player.full_name,
        "jersey_number": player.jersey_number,
        "nationality": player.nationality,
        "position": player.position,
        "position_code": player.position_code,
        "portrait_url": f"/portraits/{team_code}_{player.jersey_number}.png" if portrait_path else "",
        "team_code": team_code,
        "shl_se_uuid": player.uuid,
    }


# ---------------------------------------------------------------------------
# Fetch functions (write to DB, used by poller / endpoints with force_refresh)
# ---------------------------------------------------------------------------


def fetch_shl_se_player(
    season_id: int,
    swehockey_team: str,
    jersey: int,
    cache_dir: Path,
    force_refresh: bool = False,
) -> Optional[dict]:
    """Fetch player info from shl.se, cache portrait, persist in DB.

    Returns dict with: first_name, last_name, full_name, jersey_number,
    nationality, position, position_code, portrait_url, portrait_path, team_code, shl_se_uuid

    If force_refresh=False and data exists in DB, returns cached.
    If force_refresh=True, re-fetches from shl.se.
    """
    if not force_refresh:
        cached = load_shl_se_player(cache_dir, season_id, swehockey_team, jersey)
        if cached is not None:
            return cached["data"]

    try:
        mapper = _get_team_mapper()
    except Exception as exc:
        _logger.error("fetch_shl_se_player: failed to initialize team mapper: %s", exc)
        return None
    shl_team = mapper.swehockey_to_shl_se(swehockey_team)
    if not shl_team:
        _logger.warning("fetch_shl_se_player: no shl.se team match for '%s'", swehockey_team)
        return None

    try:
        roster = fetch_shl_se_roster(shl_team.uuid)
    except Exception as exc:
        _logger.error("fetch_shl_se_player: failed to fetch roster for %s: %s", shl_team.uuid, exc)
        return None

    player = next((p for p in roster if p.jersey_number == jersey), None)
    if player is None:
        _logger.warning("fetch_shl_se_player: jersey %d not found in %s roster", jersey, swehockey_team)
        return None

    portrait_path = download_portrait(player.portrait_url, cache_dir, shl_team.team_code, jersey)
    data = _player_to_dict(player, shl_team.team_code, portrait_path)

    save_shl_se_player(cache_dir, season_id, swehockey_team, jersey, data, portrait_path)
    return data


def fetch_shl_se_team_players(
    season_id: int,
    swehockey_team: str,
    cache_dir: Path,
    force_refresh: bool = False,
) -> List[dict]:
    """Fetch all players for a team from shl.se. Downloads all portraits."""
    if not force_refresh:
        cached = load_shl_se_team_players(cache_dir, season_id, swehockey_team)
        if cached:
            return [row["data"] for row in cached]

    try:
        mapper = _get_team_mapper()
    except Exception as exc:
        _logger.error("fetch_shl_se_team_players: failed to initialize team mapper: %s", exc)
        return []
    shl_team = mapper.swehockey_to_shl_se(swehockey_team)
    if not shl_team:
        _logger.warning("fetch_shl_se_team_players: no shl.se team match for '%s'", swehockey_team)
        return []

    try:
        roster = fetch_shl_se_roster(shl_team.uuid)
    except Exception as exc:
        _logger.error("fetch_shl_se_team_players: failed to fetch roster for %s: %s", shl_team.uuid, exc)
        return []

    results: List[dict] = []
    for player in roster:
        if player.jersey_number <= 0:
            continue
        portrait_path = download_portrait(player.portrait_url, cache_dir, shl_team.team_code, player.jersey_number)
        data = _player_to_dict(player, shl_team.team_code, portrait_path)
        save_shl_se_player(cache_dir, season_id, swehockey_team, player.jersey_number, data, portrait_path)
        results.append(data)

    return results


# ---------------------------------------------------------------------------
# Get functions (read-only from DB, used by REST API)
# ---------------------------------------------------------------------------


def get_shl_se_player(
    season_id: int,
    swehockey_team: str,
    jersey: int,
    cache_dir: Path,
) -> Optional[dict]:
    """Read-only: get persisted player info from DB. Returns None if not fetched."""
    cached = load_shl_se_player(cache_dir, season_id, swehockey_team, jersey)
    if cached is None:
        return None
    return cached["data"]


def get_shl_se_team_players(
    season_id: int,
    swehockey_team: str,
    cache_dir: Path,
) -> Optional[List[dict]]:
    """Read-only: get all persisted players for a team. Returns None if not fetched."""
    rows = load_shl_se_team_players(cache_dir, season_id, swehockey_team)
    if not rows:
        return None
    return [row["data"] for row in rows]
