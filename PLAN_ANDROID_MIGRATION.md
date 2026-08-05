# Migration Plan: Android App → shl2026-backend API

## Overview

Migrate `shl-se-android` from the old backend (`http://192.168.3.220:1082/api/`) to `shl2026-backend`.

The app uses Ktor + kotlinx.serialization. All API calls are in 4 repository files.

---

## Current vs New API Mapping

| App repository | Old endpoint | New endpoint | Status |
|---|---|---|---|
| `ScheduleRepository` | `GET /api/schedule/{league}` | `GET /seasons/{season_id}/rounds` | ✅ Available |
| `StandingsRepository` | `GET /api/standings/{league}` | `GET /seasons/{season_id}/standings` | ✅ Available |
| `LiveRepository` | `GET /api/today/{league}` | `GET /seasons/{season_id}/games/today` + game detail | ⚠️ Partial |
| `PlayersRepository` | `GET /api/players/{league}/{team}` | `GET /seasons/{season_id}/rosters?team={team}` | ✅ Available |
| `PlayersRepository` | `GET /api/player/{league}/{team}/{jersey}` | — | ❌ Missing |

---

## Files to Change

### 1. New: `ApiConfig.kt`

Centralize the base URL and season ID:

```kotlin
object ApiConfig {
    var baseUrl = "http://192.168.3.220:8000"  // Configurable
    var seasonId = 18263
}
```

### 2. `ScheduleRepository.kt` — Moderate rewrite

**Old:** `GET /api/schedule/SHL` → `{ rounds: [...] }`

**New:** `GET /seasons/18263/rounds` → `{ data: [{ round: "1", games: [...] }], meta: {...} }`

Changes:
- URL: `/seasons/${seasonId}/rounds`
- Response wrapper: extract `data` array from envelope
- Game fields mapping:
  - `game_id` → parse from `game_url` (last path segment)
  - `home_team` / `away_team` → plain strings (no longer objects with abbr/logo)
  - `home_score` / `away_score` → parse from `game_result` string ("3 - 2")
  - `status` → derive from `game_result` presence + `overtime` field
  - `start_time` → combine `date` + `time`
  - `events` → not inline (empty list; fetch via `/games/{id}` on demand)

### 3. `StandingsRepository.kt` — Minor rewrite

**Old:** `GET /api/standings/SHL` → `{ standings: [...] }`

**New:** `GET /seasons/18263/standings` → `{ data: [...], meta: {...} }`

Changes:
- URL: `/seasons/${seasonId}/standings`
- Response wrapper: `data` instead of `standings`
- Field renames:
  - `team_name` → `team`
  - `team_abbr` → not present (need a static lookup or derive from team name)
  - `points` → `tp`
  - `wins` → `w`
  - `losses` → `l`
  - `wins_ot` → `otw + gwsw`
  - `losses_ot` → `otl + gwsl`
  - `goal_difference` → `goal_difference` (same)
  - `movement` → `movement` (same ✅)
- Missing fields: `team_logo`, `streak`, `last5` (see Data Gaps below)

### 4. `LiveRepository.kt` — Moderate rewrite

**Old:** `GET /api/today/SHL` → `{ games: [...] }` with live scores, period, status

**New:** `GET /seasons/18263/games/today` → upcoming games (no live scores yet)

Changes:
- URL: `/seasons/${seasonId}/games/today`
- For live score data: use schedule endpoint (has live scores from 30s polling) or fetch individual game detail
- Game fields: same mapping as ScheduleRepository

### 5. `PlayersRepository.kt` — Moderate rewrite

**Old:** `GET /api/players/SHL/ske` → `List<Player>` with full career data

**New:** `GET /seasons/18263/rosters?team=Skellefteå AIK` → roster entries (name, position, jersey, birthdate, height, weight, nationality)

Changes:
- URL: `/seasons/${seasonId}/rosters?team={fullTeamName}`
- Need a team abbreviation → full name mapping (e.g. "ske" → "Skellefteå AIK")
- Response is `{ data: [...] }` envelope
- Player fields mapping — see Data Gaps below

### 6. `ScheduleModels.kt` / `StandingsModels.kt` / `PlayerModels.kt`

Update data classes to match new response shapes. Can either:
- Create new API-specific data classes and map to existing domain models (cleaner)
- Modify existing data classes (faster but messier)

Recommended: create a new `api/` package with response models matching the OpenAPI spec, then map to existing domain models in the repositories.

---

## Data Gaps (Previously Available, Now Missing)

### ❌ Completely missing

| Data | Old source | Impact | Workaround |
|---|---|---|---|
| **Player career history** | EliteProspects integration | Player detail view loses career stats table | None — would need EP integration |
| **Player career stats** (career GP, G, A, PTS) | EliteProspects | Player detail view | None |
| **Player season stats** (current season G, A, PTS per player) | Old backend computed | Player detail view | Could derive from scoring leaders for top players |
| **Player image/photo** | EliteProspects | Player detail view | None |
| **Player draft info** | EliteProspects | Player detail view | None |
| **Player contract** | EliteProspects | Player detail view | None |
| **Player profile link** | EliteProspects | Player detail view | None |
| **Player birth place** | EliteProspects | Player detail view | None |
| **Individual player detail endpoint** | `GET /api/player/{league}/{team}/{jersey}` | Player tap opens detail | Show roster data only |

### ⚠️ Partially available (less data)

| Data | Old source | New source | What's missing |
|---|---|---|---|
| **Team abbreviations** | Backend provided `team_abbr` | Not in standings/schedule | Need a static 14-entry lookup |
| **Team logos** | Backend provided `team_logo` | Not available | Need a static lookup (sportality CDN URLs already in app code) |
| **Streak / Last 5** | Backend computed | Not available | Could compute client-side from schedule data |
| **Live game period/clock** | `GET /api/today` had period info | Not yet available | Deferred to season start |
| **Game events inline** | Schedule included events per game | Events via separate `/games/{id}` endpoint | Extra request per game on detail view |

### ✅ Fully available (same or better)

| Data | Notes |
|---|---|
| Schedule (all games, rounds) | Same data, better structure |
| Standings (rank, points, W/L, goals, movement) | Same + movement now tracked |
| Rosters (name, jersey, position, birthdate, height, weight, nationality) | ✅ Same |
| Goalie stats (GAA, SVS%, wins) | New — wasn't in old schedule view |
| Scoring leaders (goals, assists, points, +/-) | New — old app used per-team player list |

---

## Team Lookup (Required)

The app needs team abbreviations and logos. shl2026 uses full team names. A static map is needed:

```kotlin
val TEAM_MAP = mapOf(
    "Brynäs IF" to Team("bif", "Brynäs IF", "BIF", "https://sportality.cdn.s8y.se/team-logos/bif1_bif.svg"),
    "Djurgårdens IF" to Team("dif", "Djurgårdens IF", "DIF", "https://sportality.cdn.s8y.se/team-logos/dif1_dif.svg"),
    "Frölunda HC" to Team("fhc", "Frölunda HC", "FHC", "https://sportality.cdn.s8y.se/team-logos/fhc1_fhc.svg"),
    "Färjestad BK" to Team("fbk", "Färjestad BK", "FBK", "https://sportality.cdn.s8y.se/team-logos/fbk1_fbk.svg"),
    "HV 71" to Team("hv71", "HV 71", "HV71", "https://sportality.cdn.s8y.se/team-logos/hv711_hv71.svg"),
    "IF Malmö Redhawks" to Team("mif", "IF Malmö Redhawks", "MIF", "https://sportality.cdn.s8y.se/team-logos/mif1_mif.svg"),
    "Leksands IF" to Team("lif", "Leksands IF", "LIF", "https://sportality.cdn.s8y.se/team-logos/lif1_lif.svg"),
    "Linköping HC" to Team("lhc", "Linköping HC", "LHC", "https://sportality.cdn.s8y.se/team-logos/lhc1_lhc.svg"),
    "Luleå HF" to Team("lhf", "Luleå HF", "LHF", "https://sportality.cdn.s8y.se/team-logos/lhf1_lhf.svg"),
    "Rögle BK" to Team("rbk", "Rögle BK", "RBK", "https://sportality.cdn.s8y.se/team-logos/rbk1_rbk.svg"),
    "Skellefteå AIK" to Team("ske", "Skellefteå AIK", "SKE", "https://sportality.cdn.s8y.se/team-logos/sai1_sai.svg"),
    "Timrå IK" to Team("tik", "Timrå IK", "TIK", "https://sportality.cdn.s8y.se/team-logos/tik1_tik.svg"),
    "Växjö Lakers HC" to Team("vax", "Växjö Lakers HC", "VÄX", "https://sportality.cdn.s8y.se/team-logos/vlh1_vlh.svg"),
    "Örebro HK" to Team("ohk", "Örebro HK", "ÖHK", "https://sportality.cdn.s8y.se/team-logos/ohk1_ohk.svg"),
)
```

---

## Effort Estimate

| Task | Effort |
|------|--------|
| `ApiConfig.kt` (base URL + season ID) | 15 min |
| `ScheduleRepository.kt` rewrite | 1-2 hours |
| `StandingsRepository.kt` rewrite | 30 min |
| `LiveRepository.kt` rewrite | 1 hour |
| `PlayersRepository.kt` rewrite | 1 hour |
| New API response models | 1 hour |
| Team lookup map | 15 min |
| Testing / debugging | 1-2 hours |
| **Total** | **~6-8 hours** |

---

## Migration Strategy

**Recommended approach: parallel support**

1. Add the shl2026 API client alongside the existing one
2. Add a settings toggle (or build variant) to switch between backends
3. Migrate one repository at a time, verifying each screen works
4. Once all screens work, remove the old backend code

This allows testing without breaking the current working app.

---

## Decisions Needed

1. **Player detail view** — remove it entirely, show only roster data, or leave placeholder for future EP integration?
2. **Streak / Last 5** — compute client-side from schedule, or drop from UI?
3. **Team logos** — hardcode in app (already partly done) or add to backend API?
4. **Season ID** — hardcode for now, or make configurable in settings?
5. **Live games** — accept no period/clock until season starts, or hide live tab?
