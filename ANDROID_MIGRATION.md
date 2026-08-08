# Android App → shl2026-backend Migration

Summary of changes needed to make `shl-se-android` consume `shl2026-backend` directly.

---

## Backend Changes

### 1. Enricha `TeamInfo` med `logo_url`

`/seasons/{season_id}/teams` ska returnera:

```json
{
  "data": [
    {"team": "Brynäs IF", "abbreviation": "BIF", "logo_url": "https://www.shl.se/..."}
  ],
  "meta": {...}
}
```

- Koden finns redan i `shl_se.py` (`ShlSeTeam.logo_url` via `TeamMapper`)
- Ändring: enricha `TeamInfo`-modellen med `logo_url`, populera vid fetch

### 2. Lägg till `team_abbr` i standings-raden

`/seasons/{season_id}/standings/live` ska inkludera abbreviation per team:

```json
{"rank": 1, "team": "Skellefteå AIK", "team_abbr": "SKE", "games_played": 10, ...}
```

- Backend har redan `TeamInfo`-tabellen (name→abbr)
- Ändring: `get_standings()` / `get_live_standings()` slår upp abbr och berikar `StandingsRow`

### 3. Lägg till `game_id` i `ScheduleEntry`

Alla schedule/live/rounds-svar ska inkludera `game_id` som eget int-fält:

```json
{"game_id": 1004308, "date": "2025-09-13", "home_team": "Brynäs IF", ...}
```

- Finns redan i `game_url` (`/Game/Events/1004308`)
- Ändring: extrahera vid parsing eller som `@property` i modellen, inkludera i serialisering

---

## Android App Changes

### 1. Season ID-koncept

- Lägg till `season_id` i preferences (int, t.ex. 18263)
- Alla API-anrop använder `/seasons/{season_id}/...` istf `/api/{league}/...`
- Kan hårdkodas per säsong eller göras konfigurerbar i Settings

### 2. URL-routing i repositories

| Repository | Nuvarande URL | Ny URL |
|---|---|---|
| `LiveRepository` | `/api/today/{league}` | `/seasons/{season_id}/games/live` |
| `ScheduleRepository` | `/api/schedule/{league}` | `/seasons/{season_id}/rounds` |
| `StandingsRepository` | `/api/livestandings/{league}` | `/seasons/{season_id}/standings/live` |
| `PlayersRepository` (lista) | `/api/players/{league}/{abbr}` | `/seasons/{season_id}/players/{team_name}` |
| `PlayersRepository` (detalj) | `/api/player/{league}/{abbr}/{jersey}` | `/seasons/{season_id}/players/{team_name}/{jersey}` |

### 3. Response envelope

Alla svar wrappas i `{"data": [...], "meta": {...}}`.

- Extrahera `data`-nyckeln som primary path (delvis redan implementerat som fallback)
- `meta` kan ignoreras eller användas för freshness-info i UI

### 4. Team-info cache (ny komponent)

- Hämta `/seasons/{season_id}/teams` vid uppstart
- Cacha lokalt: `Map<String, TeamCacheEntry>` med `team_name`, `abbreviation`, `logo_url`
- Används av:
  - Standings: mappa `team` → `team_abbr` för lokal logo-matchning
  - Players: mappa `abbr` → `team_name` för URL-byggning
  - Schedule/Live: berika team-info

### 5. Logo-hantering

- Ta bort bundlade SVG:er i `res/raw/` (bif.svg, fhc.svg, etc.)
- Använd Coil med URL-baserad laddning + disk-cache
- Logo-URL:er kommer från team-info cachen

### 6. Standings — fältmappning

Uppdatera `ApiStandingItem` och parsing:

| Android (nu) | shl2026-backend |
|---|---|
| `team_name` | `team` |
| `team_abbr` | `team_abbr` ✅ (efter backend-ändring) |
| `team_logo` | → lookup via team-info cache |
| `wins` | `w` |
| `wins_ot` | `otw` |
| `losses_ot` | `otl` |
| `losses` | `l` |
| `points` | `tp` |
| `games_played` | `games_played` ✅ |
| `goals_for` | `goals_for` ✅ |
| `goals_against` | `goals_against` ✅ |
| `goal_difference` | `goal_difference` ✅ |
| `movement` | `movement` ✅ |

### 7. Schedule/Live games — parsing

- `home_team` / `away_team` är strängar (inte objekt) — hantera direkt
- `game_result: "4 - 7"` → split till `homeScore` / `awayScore`
- `game_id` som eget fält (efter backend-ändring) — använd direkt
- `status`, `game_state`, `game_clock`, `current_period` — rikare än gamla API:t

### 8. Mål-notifikationer (game events)

Score-diff-detektering funkar redan (`DataCache.checkForGoals()`).

För att berika notifikationer med detaljer (scorer, tid, assists):
- Vid detekterad score-diff → hämta `/games/{game_id}`
- Extrahera senaste goal-action från `actions`-arrayen
- Kräver ny modell för `GameDetailResponse` + `Action`

### 9. Players — anpassningar

- URL: använd `team_name` (URL-encodat) istf `team_abbr` — lookup via team-info cache
- Fält: `jersey` (int) istf `jersey_number` (string)
- Fält: `portrait_url` istf `image_url`
- `career_stats`, `season_stats`, `career_history` → saknas (EliteProspects) — gör nullable/dölj

### 10. Port-ändring

- Gamla backend: port 1082
- shl2026-backend: port 8000
- Uppdatera default i `PreferencesManager` och `SettingsScreen`

---

## Prioritetsordning

1. **Backend**: `logo_url` i teams, `team_abbr` i standings, `game_id` i schedule (liten insats)
2. **App**: Team-info cache + URL-routing + envelope-parsing (grund som allt annat bygger på)
3. **App**: Standings + Schedule/Live fältmappning
4. **App**: Logo-laddning via Coil (ersätt bundlade SVG:er)
5. **App**: Mål-notifikationer via `/games/{game_id}`
6. **App**: Players-anpassning
