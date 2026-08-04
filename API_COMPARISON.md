# API Comparison: shl2026-backend vs shl-se-backend

## Schedule / Games

| Functionality | shl-se-backend | shl2026-backend |
|---|---|---|
| Full season schedule | `GET /schedule?league=&season=` | `GET /games?season_id=` |
| By date | — | `GET /games/date/{date}` |
| Played games | — | `GET /games/played?season_id=` |
| Rounds (all) | — | `GET /games/rounds?season_id=` |
| Next round | — | `GET /games/rounds/next?season_id=` |
| Game detail | `GET /schedule/{game_id}` | `GET /games/{game_id}` |

**Key data differences:**
- shl2026 game entries include: `spectators`, `venue`, `game_url`, plus full team stats (shots, saves, PIM, power play) and a `score_state` field
- shl-se returns schedule entries with inline `events` (goals/penalties per game); shl2026 does not hydrate events inline
- shl2026 wraps all responses in an envelope with data-freshness metadata (`updated_at`, cache TTL)

---

## Standings

| Functionality | shl-se-backend | shl2026-backend |
|---|---|---|
| League standings | `GET /standings?league=&season=` | `GET /standings?season_id=` |
| Live standings | `GET /standings/live?league=` | `GET /standings?season_id=` (effectively live) |

**Key data differences:**
- shl2026 adds: `rank`, `otw` (OT wins), `otl` (OT losses), and a `gws` column
- shl2026 standings are **effectively live during games**: the poller fetches the schedule page every 30s during game windows, and SweHockey updates scores on that page mid-game. `GET /standings` recalculates from the latest cached scores, so standings reflect in-progress games within ~30s of a goal.
- shl-se has a separate `/standings/live` endpoint; in shl2026 the regular standings endpoint serves the same purpose — no separate endpoint needed.

---

## Players / Rosters

| Functionality | shl-se-backend | shl2026-backend |
|---|---|---|
| Team roster | `GET /players?team=&league=&season=` | — |
| Player detail | `GET /players/{player_id}` | — |
| Player stats | `GET /players/{player_id}/stats` | — |

shl2026-backend has **no player/roster endpoints at all** yet.

---

## Teams

| Functionality | shl-se-backend | shl2026-backend |
|---|---|---|
| Team list | `GET /teams?league=&season=` | — |

shl2026-backend is missing a teams endpoint.

---

## Live / Game-day

| Functionality | shl-se-backend | shl2026-backend |
|---|---|---|
| Live standings | `GET /standings/live?league=` | `GET /standings?season_id=` (effectively live) |

shl2026 does not have a separate live-standings endpoint because it's unnecessary — the regular standings endpoint already reflects in-progress game scores. The poller fetches the schedule page every 30s during game windows, and standings are recalculated from the latest data on every request.

---

## Push Notifications (new in shl2026)

| Functionality | shl-se-backend | shl2026-backend |
|---|---|---|
| Register device | — | `POST /notifications/register` |
| Get subscriptions | — | `GET /notifications/subscriptions/{device_id}` |
| Update subscriptions | — | `PUT /notifications/subscriptions/{device_id}` |
| Unregister | — | `DELETE /notifications/register/{device_id}` |

Entirely new capability in shl2026.

---

## Infrastructure & API Design

| Aspect | shl-se-backend | shl2026-backend |
|---|---|---|
| Multi-league | Yes (`league=shl` or `league=swe`) | No (only `season_id` scoping) |
| Response envelope | Plain JSON | Wrapped with `updated_at` metadata |
| Rate limiting | No | Yes |
| API root/discovery | `GET /` returns available endpoints | — |

---

## Summary

**shl2026-backend is stronger in:** richer game/standings data, more schedule query options, push notifications, rate limiting, data freshness metadata, and effectively live standings during games (30s refresh).

**shl2026-backend is missing:** players/rosters (biggest gap), teams listing, multi-league support, and API discovery. Players and teams are the most critical functional gaps if this backend is meant to replace shl-se-backend.

---

## Schedule Mapping: shl2026 → shl-se compatibility

### Field mapping (ScheduleEntry → Game)

| shl-se field | Source in shl2026 | Difficulty |
|---|---|---|
| `game_id` | Parse from `game_url` (extract "1004308" from `.../Events/1004308`) | Easy — regex/split |
| `home_team` | `home_team` | ✅ Direct |
| `away_team` | `away_team` | ✅ Direct |
| `home_team_abbr` | Not in ScheduleEntry — needs a lookup table | Medium — static team name→abbr map |
| `away_team_abbr` | Same | Medium |
| `home_team_logo` | Not available | Needs a static map or separate source |
| `away_team_logo` | Same | Same |
| `date` | `date` | ✅ Direct |
| `time` | `time` | ✅ Direct |
| `period` | Not available in schedule (only in Game detail) | ❌ Can't fill for live games from schedule alone |
| `venue` | `venue` | ✅ Direct |
| `status` | Derive: empty `game_result` → "upcoming", non-empty + `overtime`="" → "finished", `overtime`="OT" → "finished-ot", "SO" → "finished-so" | Easy — conditional logic |
| `home_score` | Parse `game_result` split on " - " → `int(parts[0])` | Easy |
| `away_score` | Parse `game_result` split on " - " → `int(parts[1])` | Easy |
| `game_link` | `game_url` | ✅ Direct (same swehockey URL) |
| `game_url` | Could construct or leave null | Trivial |
| `has_events` | Not in schedule data | Default `false` |
| `events` | Not included in schedule view (old backend also leaves empty in schedule) | `[]` — fine |

### Round grouping

shl2026's `/seasons/{id}/rounds` already groups by round. Map `round` (string) → `round_number` (int) and construct a `round_name`.

### Response envelope

Restructure from `{"data": [...], "meta": {...}}` to `{"league": "SHL", "last_updated": meta.generated_at, "rounds": [...]}`.

### Effort estimate

**Easy (a few hours):**
- Score parsing (string → two ints)
- Status derivation
- game_id extraction from URL
- Envelope restructuring
- Round grouping mapping

**Medium (needs a static data source):**
- Team abbreviations — a ~14-entry dict mapping team names to abbreviations
- Team logos — same, a dict mapping to logo URLs

**Not possible from schedule data alone:**
- `period` for live games (current period indicator) — only exists in the detailed Game model, not in ScheduleEntry. The old backend gets this from a separate live-polling mechanism.

### Example adapter (~50-80 lines)

```python
def schedule_entry_to_game(entry: ScheduleEntry, team_map: dict) -> dict:
    game_id = entry.game_url.split("/")[-1] if entry.game_url else None
    home_score = away_score = None
    status = "upcoming"

    if entry.game_result:
        parts = entry.game_result.split(" - ")
        home_score, away_score = int(parts[0]), int(parts[1])
        if entry.overtime == "OT":
            status = "finished-ot"
        elif entry.overtime == "SO":
            status = "finished-so"
        else:
            status = "finished"

    return {
        "game_id": game_id,
        "home_team": entry.home_team,
        "away_team": entry.away_team,
        "home_team_abbr": team_map.get(entry.home_team, {}).get("abbr"),
        "away_team_abbr": team_map.get(entry.away_team, {}).get("abbr"),
        "home_team_logo": team_map.get(entry.home_team, {}).get("logo"),
        "away_team_logo": team_map.get(entry.away_team, {}).get("logo"),
        "date": entry.date,
        "time": entry.time,
        "period": None,  # not available from schedule
        "venue": entry.venue,
        "status": status,
        "home_score": home_score,
        "away_score": away_score,
        "game_link": entry.game_url,
        "game_url": None,
        "has_events": False,
        "events": [],
    }
```

### Verdict

Easy to map for the schedule endpoint. The only real gaps are:
1. **Team abbreviations/logos** — solvable with a static lookup
2. **Live period indicator** — not solvable from schedule data; needs game detail endpoint or separate live-polling

If live game period tracking isn't needed in the schedule view, this is a straightforward afternoon task.

---

## Standings Mapping: shl2026 → shl-se compatibility

### Field mapping (StandingsRow → TeamStanding)

| shl-se field | Source in shl2026 | Difficulty |
|---|---|---|
| `team_name` | `team` | ✅ Direct (just rename) |
| `team_abbr` | Not available — needs lookup table | Medium — static team name→abbr map |
| `team_logo` | Not available — needs lookup table | Medium — static team name→logo URL map |
| `games_played` | `games_played` | ✅ Direct |
| `wins` | `w` | ✅ Direct (just rename) |
| `wins_ot` | `otw + gwsw` | Easy — sum the two fields |
| `losses_ot` | `otl + gwsl` | Easy — sum the two fields |
| `losses` | `l` | ✅ Direct (just rename) |
| `goals_for` | `goals_for` | ✅ Direct |
| `goals_against` | `goals_against` | ✅ Direct |
| `goal_difference` | `goal_difference` | ✅ Direct |
| `points` | `tp` | ✅ Direct (just rename) |
| `movement` | `movement` (computed from previously saved standings snapshot) | ✅ Direct |
| `use_official_points` | Not applicable | Hardcode `True` (trust `tp` as-is) |

### Semantic note: OT/SO split

shl-se merges overtime and shootout wins into one `wins_ot` field. shl2026 splits them into `otw` (overtime) + `gwsw` (shootout). Mapping back is simply addition:
- `wins_ot = otw + gwsw`
- `losses_ot = otl + gwsl`

This is lossless in the shl2026→shl-se direction (you lose the OT/SO distinction, but that's how the old API worked).

### Response envelope

Restructure from:
```json
{"data": [...], "meta": {"season_id": "...", "generated_at": "..."}}
```
to:
```json
{"league": "SHL", "last_updated": "<meta.generated_at>", "standings": [...]}
```

### Example adapter

```python
def standings_row_to_team_standing(row: dict, team_map: dict) -> dict:
    return {
        "team_name": row["team"],
        "team_abbr": team_map.get(row["team"], {}).get("abbr", ""),
        "team_logo": team_map.get(row["team"], {}).get("logo"),
        "games_played": row["games_played"],
        "wins": row["w"],
        "wins_ot": row["otw"] + row["gwsw"],
        "losses_ot": row["otl"] + row["gwsl"],
        "losses": row["l"],
        "goals_for": row["goals_for"],
        "goals_against": row["goals_against"],
        "goal_difference": row["goal_difference"],
        "points": row["tp"],
        "movement": row["movement"],
        "use_official_points": True,
    }
```

### Effort estimate

**Easy (trivial):**
- Field renames (`team`→`team_name`, `w`→`wins`, `l`→`losses`, `tp`→`points`)
- OT/SO field merging (`otw + gwsw` → `wins_ot`)
- Envelope restructuring

**Medium (needs a static data source):**
- Team abbreviations and logos — same ~14-entry dict as the schedule mapping (reuse)

**Not possible without extra work:**
- None — all fields are covered.

### Verdict

Easier than the schedule mapping. Most fields are direct renames or simple arithmetic. The same team lookup table needed for schedule covers abbreviations and logos here too. All fields are covered including `movement`.

Total adapter: ~20 lines of Python.

---

## Today's Games Mapping: shl2026 → shl-se compatibility

### What the old endpoint actually does

`GET /api/today/{league}` in shl-se-backend is **not** just a date filter. It's a **live-enriched** response powered by a dedicated scraper (`SweTodaysExtractor`) that polls `stats.swehockey.se/ScheduleAndResults/Live/` during game windows:

- `home_score` / `away_score` — updated in real-time
- `period` — "2nd period", "3rd period", etc.
- `time` — live game clock (not just start time)
- `status` — "upcoming" → "live" → "intermission" → "finished"
- Change detection fires callbacks for push notifications

### What shl2026's date endpoint provides

`GET /seasons/{season_id}/games/today` is just a date filter over the static schedule cache. Same `ScheduleEntry` fields — no scores, no period, no status. Games disappear from the response once they have a result.

### Field mapping attempt

| shl-se field | Source in shl2026 `/games/today` | Works? |
|---|---|---|
| `game_id` | Parse from `game_url` | ✅ |
| `home_team` | `home_team` | ✅ |
| `away_team` | `away_team` | ✅ |
| `date` | `date` | ✅ |
| `time` | `time` (start time only) | ⚠️ No live clock |
| `venue` | `venue` | ✅ |
| `home_score` | Not available | ❌ No live data |
| `away_score` | Not available | ❌ No live data |
| `period` | Not available | ❌ No live data |
| `status` | Can only be "upcoming" (no live/finished) | ❌ No live transitions |
| `events` | Not available | ❌ |

### Can the game detail endpoint fill the gap?

shl2026's `GET /games/{game_id}` does have `Score.home_score`, `Score.away_score`, `Score.current_period`, and `Score.state`. But:
- Requires one HTTP request **per game** (no batch)
- Data is only available if someone has already fetched that game's detail page
- No automatic polling — it's on-demand, not continuously updated

### What would be needed for parity

The schedule page already provides live scores (updated mid-game by SweHockey), which is how shl2026 standings are already live. The only missing piece for full live game tracking is **period and clock info**, which is available on each game's detail page (`score.current_period`, `score.state`).

To add this:
1. Poll game detail pages for today's active games during game windows (the `game` target type and `fetch_game` infrastructure already exist)
2. Store the fetched game state in the DB (already happens via `save_game`)
3. Return enriched game objects via the API (already possible via `GET /games/{game_id}`)

This is a small extension of existing infrastructure — not a new scraping system.

### Verdict

**Mostly covered.** Live scores are already available via the schedule (30s refresh). Period/clock tracking requires polling individual game detail pages during active windows — the infrastructure exists, it just needs to be wired up as an automatic polling target during game days.

For a non-live "what's on today" view, the schedule works directly. For full game-day live tracking with period info, activate game detail polling for today's games.

---

## Game Detail Mapping: shl2026 → shl-se compatibility

### What each backend provides

**shl-se-backend** (`GET /api/game/{league}/{game_id}/events`) returns a **flat event list** only:
```json
{
  "league": "SHL",
  "game_id": "123456",
  "last_updated": "...",
  "events": [
    { "period": 1, "time": "12:34", "team": "home", "team_abbr": "FHC",
      "event_type": "Mål", "description": "...", "details": "Lundqvist",
      "team_logo": "https://...", "icon": "https://..." }
  ]
}
```

**shl2026-backend** (`GET /games/{game_id}`) returns a **rich nested object** — game info, score breakdown, full team stats, and structured actions:
```json
{
  "data": {
    "game": { "home_team", "away_team", "is_overtime", "is_shootout", "arena", "date_time", "league" },
    "score": { "current": "3-2", "home_score": 3, "away_score": 2,
               "periods": ["1-0","1-1","1-1"], "current_period": 3, "state": "Final Score" },
    "teams": { "Frölunda HC": { "shots": {...}, "saves": {...}, "pim": {...}, "pp": {...} } },
    "actions": [
      { "period": "1st period", "game_time": "03:45", "event_type": "goal", "team_abbrev": "FHC",
        "players": ["15. Lundqvist, Carl"], "player_numbers": [15], "is_goal": true,
        "goal": { "home_score": 1, "away_score": 0, "strength": "EQ", "qualifier": null },
        "penalty_reason": null, "penalty_time_range": null, "shot_outcome": null }
    ]
  },
  "meta": { "game_id": "123456", "source_fetched_at": "...", "generated_at": "..." }
}
```

### Data richness comparison

**shl2026 has MORE than shl-se:**

| Data | shl2026 | shl-se |
|---|---|---|
| Team stats (shots, saves, PIM, PP) per period | ✅ | ❌ |
| Score per period breakdown | ✅ | ❌ |
| OT/SO explicit flags | ✅ | ❌ |
| Goal strength (EQ/PP1/PP2/SH) | ✅ | ❌ |
| Penalty reason (e.g. "Hooking") | ✅ | ❌ (buried in description) |
| Penalty time range (start/end) | ✅ | ❌ |
| Player jersey numbers | ✅ | ❌ |
| Shootout shot outcomes | ✅ | ❌ |
| Game state & current period | ✅ | ❌ |
| Arena, date_time, league | ✅ | ❌ |

**shl-se has things shl2026 doesn't:**

| Data | shl-se | shl2026 |
|---|---|---|
| Team logos per event | ✅ | ❌ |
| Event icons | ✅ | ❌ |
| Home/away side label ("home"/"away") | ✅ | ❌ (only `team_abbrev`) |
| Swedish event type labels ("Mål") | ✅ | ❌ (English: "goal") |
| Human-readable description field | ✅ | ❌ (structured fields instead) |

### Field mapping (Action → GameEvent)

| shl-se field | Source in shl2026 | Difficulty |
|---|---|---|
| `period` (int) | Parse from `period` string ("1st period" → 1, "2nd period" → 2) | Easy — regex or dict |
| `time` | `game_time` | ✅ Direct rename |
| `team` ("home"/"away") | Compare `team_abbrev` against `game.home_team`/`game.away_team` | Easy — needs team abbr→name map or compare against GameInfo |
| `team_abbr` | `team_abbrev` | ✅ Direct (minor rename) |
| `event_type` | Translate: "goal"→"Mål", "penalty"→"Utvisning" | Easy — small translation dict |
| `description` | Reconstruct from `player_text` + `event_detail` | Medium — string formatting |
| `details` | `players[0]` or `player_text` | Easy |
| `team_logo` | Not available — needs static lookup by team | Medium |
| `icon` | Not available — needs icon mapping by event type | Medium |

### Response envelope mapping

Extract events from the nested response and wrap in old format:
```python
# shl2026 response → shl-se format
old_format = {
    "league": game_data["data"]["game"]["league"].split()[0],  # "SHL 2024/2025" → "SHL"
    "game_id": meta["game_id"],
    "last_updated": meta["source_fetched_at"],
    "events": [action_to_event(a, game_data["data"]["game"]) for a in game_data["data"]["actions"]],
}
```

### Example adapter

```python
PERIOD_MAP = {"1st period": 1, "2nd period": 2, "3rd period": 3, "Overtime": 4, "GWS": 5}
EVENT_TYPE_MAP = {"goal": "Mål", "penalty": "Utvisning", "GWS": "Straffslag", "PS": "Straffslag"}
ICON_MAP = {"goal": "/icons/goal.svg", "penalty": "/icons/penalty.svg"}

def action_to_event(action: dict, game_info: dict, team_map: dict) -> dict:
    # Determine home/away
    team_side = None
    if team_map.get(action["team_abbrev"]) == game_info["home_team"]:
        team_side = "home"
    elif team_map.get(action["team_abbrev"]) == game_info["away_team"]:
        team_side = "away"

    # Build description
    description = action.get("player_text", "")
    if action.get("event_detail"):
        description += f" ({action['event_detail']})"

    return {
        "period": PERIOD_MAP.get(action.get("period"), None),
        "time": action["game_time"],
        "team": team_side,
        "team_abbr": action["team_abbrev"],
        "event_type": EVENT_TYPE_MAP.get(action["event_type"], action["event_type"]),
        "description": description,
        "details": action["players"][0] if action.get("players") else action.get("player_text"),
        "team_logo": team_map.get(action["team_abbrev"], {}).get("logo"),
        "icon": ICON_MAP.get(action["event_type"]),
    }
```

### Effort estimate

**Easy:**
- Period string → int parsing
- game_time → time rename
- team_abbrev → team_abbr rename
- Event type English → Swedish translation
- Envelope restructuring

**Medium:**
- Reconstruct `description` from structured fields (formatting choices)
- Team logo lookup (same static map as schedule/standings)
- Icon mapping by event type
- Determining "home"/"away" from team_abbrev (need to match against GameInfo)

**Not needed (data loss is acceptable):**
- shl2026 has much richer data (goal strength, penalty reason, player numbers) that simply gets dropped in the old format — that's fine, it's a simplification

### Verdict

**Very doable.** Since shl2026 has *more* data than shl-se needs, you're just simplifying/flattening. No information gaps that would make the mapping impossible. The adapter is ~40-60 lines. Same team lookup table from schedule/standings covers logos here too.

The only design decision: how to reconstruct the `description` string from the structured action fields. The old backend scraped it as free text; you'll need to decide on a format.

---

## Android App (shlapp-android) API Usage vs shl2026-backend

### Base URL

The app points to `https://app.nandorf.org:9449/shl/` — this is the older monolithic backend (the `shl/` project), not `shl-se-backend`.

### All endpoints the app actively uses

| # | Endpoint | Purpose | Polling frequency |
|---|---|---|---|
| 1 | `GET live` | Live scores during games | Every 15-30s |
| 2 | `GET livetable` | Live standings | Every 15s |
| 3 | `GET schedule` | Season schedule | Once |
| 4 | `GET gamedetails/{key}` | Full game stats (shots/saves/PIM/PP) | Every 15s during game |
| 5 | `GET geteventsbyteam/{key}` | Game events by team | Every 15s during game |
| 6 | `GET playerstats` | Player scoring leaders | Once at start |
| 7 | `GET goaliestats` | Goalie stats | Once at start |
| 8 | `GET playerstatsbyteam` | Detailed per-player stats by team | Once at start |
| 9 | `GET rosters/{league}/{team}` | Team roster | On-demand |
| 10 | `GET eliteprospects` | Career data, contracts | Once at start |

### Fields actually used by the app UI

**Schedule** — `Game` model:
- `homeTeam`, `awayTeam`, `homeScore`, `awayScore`, `date`, `time`, `game_url`

**Live** — `LiveGame` model:
- `homeTeam`, `awayTeam`, `homeScore`, `awayScore`, `score` (period time), `periodNo`, `periodDetails`, `placeOrDetailedScore`, `hasEnded`, `game_url`

**Standings** — `TeamStanding` model:
- `movement`, `position`, `team`, `gamesPlayed`, `wins`, `losses`, `otWins`, `otLosses`, `goalsFor`, `goalsAgainst`, `points`
- Calculated in UI: `goalsFor - goalsAgainst` (diff column)

**Game Details** — `GameDetails` model:
- `homeTeam`, `awayTeam`, `score.homeScore`, `score.awayScore`, `date`, `venue`
- `homeShots.total/percent/details`, `awayShots.total/percent/details`
- `homeSaves.total/percent/details`, `awaySaves.total/percent/details`
- `homePims.total/details`, `awayPims.total/details`
- `homePp.total/details`, `awayPp.total/details`

**Events** — `SHLSEEVent` model:
- `accumulatedTime`, `type`, `team`, `playerName`, `description`

**Player Stats** — `PlayerStat` model:
- `rank`, `jersey`, `name`, `team`, `position`, `gamesPlayed`, `goals`, `assists`, `totalPoints`, `pointsPerGame`, `penaltyMinutes`, `plusMinus`

**Goalie Stats** — `GoalieStatsData` model:
- `no`, `name`, `team`, `gp`, `gpi`, `mip`, `sog`, `ga`, `gaa`, `svs`, `svsPercent`, `so`, `w`, `l`, `wp`

**Rosters** — `RostersPlayer` model:
- `number`, `name`, `position`, `lr`, `nationality`, `club`, `height`, `weight`, `birthdate`

### Mapping feasibility to shl2026-backend

| App endpoint | shl2026 equivalent | Mappable? | Notes |
|---|---|---|---|
| `schedule` | `GET /seasons/{id}/schedule` | ✅ Easy | Parse `game_result` → homeScore/awayScore. Direct: homeTeam, awayTeam, date, time, game_url |
| `gamedetails/{key}` | `GET /games/{game_id}` | ✅ **Excellent** | shl2026 `TeamStats` has shots/saves/PIM/PP with total + by_period + percentage — maps almost 1:1 to what the app needs |
| `geteventsbyteam/{key}` | `GET /games/{game_id}` actions | ✅ Good | App needs: time→`game_time`, type→`event_type`, team→`team_abbrev`, playerName→`players[0]`, description→reconstruct |
| `livetable` | `GET /seasons/{id}/standings` | ✅ Good | Effectively live (30s refresh during games). All fields map except `movement` (default 0). Rename: w→wins, l→losses, otw+gwsw→otWins, otl+gwsl→otLosses, tp→points |
| `live` | Schedule (scores) + `GET /games/{id}` (period/state) | ⚠️ Partial | Live scores available from schedule (30s refresh). Period/clock requires game detail polling for active games — infrastructure exists, needs wiring |
| `playerstats` | **No equivalent** | ❌ Gap | Not in shl2026 |
| `goaliestats` | **No equivalent** | ❌ Gap | Not in shl2026 |
| `playerstatsbyteam` | **No equivalent** | ❌ Gap | Not in shl2026 |
| `rosters/{league}/{team}` | **No equivalent** | ❌ Gap | Not in shl2026 |
| `eliteprospects` | **No equivalent** | ❌ Gap | Not in shl2026 |

### Game Details mapping (best match)

The app's `GameDetails` model maps almost perfectly to shl2026's Game response:

| App field | shl2026 source |
|---|---|
| `homeTeam` | `data.game.home_team` |
| `awayTeam` | `data.game.away_team` |
| `score.homeScore` | `data.score.home_score` |
| `score.awayScore` | `data.score.away_score` |
| `date` | `data.game.date_time` (parse date) |
| `venue` | `data.game.arena` |
| `homeShots.total` | `data.teams[home_team].shots.total` |
| `homeShots.percent` | `data.teams[home_team].shots.percentage` |
| `homeShots.details` | `data.teams[home_team].shots.by_period` (format as string) |
| `homeSaves.total` | `data.teams[home_team].saves.total` |
| `homeSaves.percent` | `data.teams[home_team].saves.percentage` |
| `homeSaves.details` | `data.teams[home_team].saves.by_period` (format as string) |
| `homePims.total` | `data.teams[home_team].pim.total` |
| `homePims.details` | `data.teams[home_team].pim.by_period` (format as string) |
| `homePp.total` | `data.teams[home_team].pp.percentage` |
| `homePp.details` | `data.teams[home_team].pp.time` |

This is essentially a field rename + minor formatting. ~30 lines of adapter code.

### Summary

**Can replace with shl2026 today (6/10 endpoints):**
- Schedule ✅
- Game details ✅ (actually better data)
- Game events ✅
- Standings ✅ (effectively live — 30s refresh during games, includes `movement`)
- Live standings ✅ (same endpoint as above, no separate endpoint needed)
- Live scores ⚠️ (scores from schedule already live; period/clock needs game detail polling — infrastructure exists)

**Cannot replace — needs new infrastructure (4/10 endpoints):**
- Live game period/clock — game detail pages have this info; needs polling active games during game windows (infrastructure exists via `game` target type)
- Player stats, goalie stats, stats by team — needs stats scraping
- Rosters — needs roster data source
- EliteProspects — needs EP integration

**Effort to support the 6 mappable endpoints:** ~1-2 days of adapter work. The game details endpoint is the strongest match and would actually give the app richer data than it currently gets. Adding game detail polling for active games is a small wiring task.

**Effort to reach full parity:** The remaining 4 endpoints represent data domains (player statistics, roster management, external data integration) that would need new scrapers and data pipelines.

---

## Backend Lineage & Architecture Context

### Three separate backends exist

| Project | Role | Status |
|---|---|---|
| `shl/` (monolith) | Original backend with all services (api, schedule, stats, roster, eliteprospects, live-games, photo, tournaments) | **Currently serving the Android app** at `app.nandorf.org:9449/shl/` |
| `shl-se-backend/` | Intermediate rewrite — cleaner architecture, focused on SweHockey scraping (schedule + standings + live + events) | Partial coverage, multi-league (SHL + SWE) |
| `shl2026-backend/` | Latest iteration — schedule, standings, game details, push notifications | Newest, richest game data, but narrowest scope |

### The Android app uses the monolith (`shl/`), NOT `shl-se-backend`

The app points to `https://app.nandorf.org:9449/shl/` which is the monolithic `shl/` project. This is why the app has access to endpoints like `playerstats`, `goaliestats`, `rosters`, `eliteprospects` — those services exist in the monolith but were never ported to `shl-se-backend` or `shl2026-backend`.

### Evolution path

```
shl/ (monolith, everything)
  └─→ shl-se-backend/ (partial rewrite: schedule + standings + live, multi-league)
       └─→ shl2026-backend/ (latest rewrite: schedule + standings + game detail + notifications)
```

Each rewrite improved data quality and architecture but narrowed functional scope. To fully replace the monolith, shl2026-backend still needs:
- Live game polling
- Player/goalie statistics
- Team rosters
- EliteProspects integration

---

## Schedule Shape: App vs shl2026 (near-identical)

The app's schedule `Game` model is minimal (11 fields, flat list):

```kotlin
data class Game(
    val date: String,
    val time: String,
    val homeTeam: String,
    val awayTeam: String,
    val result: String,
    val homeScore: Int,        // home_score
    val awayScore: Int,        // away_score
    val resultDetails: String,
    val isFinalScore: Boolean,
    val isLive: Boolean,
    val game_url: String?
)
```

shl2026's `ScheduleEntry` is essentially the same shape:

```python
@dataclass
class ScheduleEntry:
    date: str              # → Game.date ✅
    time: str              # → Game.time ✅
    home_team: str         # → Game.homeTeam ✅
    away_team: str         # → Game.awayTeam ✅
    game_result: str       # → Game.result ✅, parse for homeScore/awayScore
    periods: str           # → Game.resultDetails (format as needed)
    spectators: str        # (extra, not needed by app)
    venue: str             # (extra, not needed by app for schedule)
    game_url: str          # → Game.game_url ✅
    round: str             # (extra, not needed by app)
    overtime: str          # (helps derive isFinalScore)
```

**Mapping: 10 of 11 app fields are directly available.** Only `isLive` cannot come from schedule data (it comes from the separate live endpoint). The app's schedule is a flat list — no round grouping needed.

This is essentially a trivial adapter: parse `game_result` into two ints, derive `isFinalScore` from non-empty result, and `isLive` defaults to `false` (the app gets live state from the `GET live` endpoint separately anyway).
