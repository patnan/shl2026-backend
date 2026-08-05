"""SHL.se API client and SweHockey ↔ shl.se mapping functions.

Bridges SweHockey team/player names to shl.se data (logos, portraits, UUIDs).
Uses the Sportality platform API at www.shl.se/api/ with header x-s8y-instance-id.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx

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
