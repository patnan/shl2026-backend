# SHL.se API

The official SHL website (www.shl.se) runs on the Sportality platform (s8y.se). It exposes a JSON API behind `/api/` that powers the frontend SPA.

## Authentication

No API key or OAuth token is needed. The only required header is:

```
x-s8y-instance-id: shl1_shl
```

Without this header, most endpoints return 404.

## Base URL

```
https://www.shl.se/api
```

## Example request

```python
import httpx

headers = {
    "accept": "application/json",
    "x-s8y-instance-id": "shl1_shl",
}

r = httpx.get("https://www.shl.se/api/sports-v2/athletes/by-team-uuid/4519-4519Rdei6", headers=headers)
data = r.json()
```

## Team identifiers

Teams are identified by a UUID (e.g. `4519-4519Rdei6` for IF Björklöven). Retrieve all teams via:

```
GET /api/site/list/teams-in-league?instanceId=shl1_shl
```

Response:
```json
[
  {"name": "Brynäs", "value": "bif1_bif"},
  {"name": "Djurgårdens IF Hockey", "value": "dif1_dif"},
  {"name": "Färjestad BK", "value": "fbk1_fbk"},
  {"name": "Frölunda HC", "value": "fhc1_fhc"},
  {"name": "HV71", "value": "hv711_hv71"},
  {"name": "Björklöven", "value": "ifb1_ifb"},
  {"name": "Linköping Hockey Club", "value": "lhc1_lhc"},
  {"name": "Luleå HF", "value": "lhf1_lhf"},
  {"name": "IF Malmö Redhawks", "value": "mif1_mif"},
  {"name": "Rögle BK", "value": "rbk1_rbk"},
  {"name": "Skellefteå AIK", "value": "ske1_ske"},
  {"name": "Timrå IK", "value": "tik1_tik"},
  {"name": "Växjö Lakers HC", "value": "vlh1_vlh"},
  {"name": "Örebro HK", "value": "ohk1_ohk"}
]
```

Note: `value` here is the `instanceId` (owner site). The team UUID used in most endpoints is different — get it from `/api/site/settings`.

## Endpoints

### Site & Teams

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/site/settings` | Full site config: all teams with UUIDs, logos, teamCodes, metadata (132 KB) |
| GET | `/api/site/settings?instanceId=shl1_shl` | Same as above |
| GET | `/api/site/list/teams-in-league?instanceId=shl1_shl` | Lightweight team list (name → instanceId) |
| GET | `/api/site/{instanceId}/info` | Basic site info (name, publicUrl) |

### Athletes & Staff

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sports-v2/athletes/by-team-uuid/{teamUuid}` | Full squad grouped by position (GK/D/F) |
| GET | `/api/sports-v2/staffs?page=0&pageSize=1000&teamUuid={teamUuid}` | Coaching staff, management |
| GET | `/api/sports-v2/teams/{teamUuid}` | Team info for one team |

### Games & Schedule

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sports-v2/upcoming-games/{teamUuid}?gamePlace=` | Upcoming games for a team |
| GET | `/api/sports-v2/played-games/{teamUuid}` | Played games for a team |
| GET | `/api/sports-v2/upcoming-live-games` | Currently live or about-to-start games |
| GET | `/api/sports-v2/today-games?instanceId=shl1_shl` | Today's games |
| GET | `/api/sports-v2/game-schedule?seasonUuid=X&seriesUuid=Y&gameTypeUuid=Z` | Full schedule (requires UUIDs) |

### Statistics

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/statistics-v2/team-page/stats-header?teamUuid={teamUuid}` | Team stats summary |
| GET | `/api/statistics-v2/league-standings?ssgtUuid={ssgtUuid}` | League standings (requires SSGT UUID) |

### Game Day (Live)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/gameday/gameheader` | Current game header info |
| GET | `/api/gameday/upcoming-live-games/v2?instanceId=shl1_shl` | Live games (V2) |

### Sponsors & Media

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/sponsors/main-sponsor-groups` | Main sponsors |
| GET | `/api/sponsors/site-sponsor-groups` | All sponsor groups |
| GET | `/api/layouts/site-layouts-list` | Available page layouts |
| GET | `/api/layouts/site-layouts/{layoutId}` | Specific layout config |

## Response format: Athletes

`GET /api/sports-v2/athletes/by-team-uuid/{teamUuid}`

```json
[
  {
    "position": "Målvakter",
    "positionCode": "GK",
    "players": [
      {
        "uuid": "qd0-A1ryrHsi",
        "firstName": "Lassi",
        "lastName": "Lehtinen",
        "fullName": "Lassi Lehtinen",
        "nationality": "FI",
        "jerseyNumber": 30,
        "playerType": "athlete",
        "gender": "",
        "globalPortraitFallback": [],
        "portraitList": [
          {
            "mediaString": "image|ramses_sports|player_portrait_...",
            "type": "portrait",
            "sortOrder": 0,
            "renderedMedia": {
              "url": "https://s8y-cdn-sp-photos.imgix.net/...",
              "alt": "",
              "srcset": "..."
            }
          }
        ]
      }
    ]
  },
  {
    "position": "Backar",
    "positionCode": "D",
    "players": [...]
  },
  {
    "position": "Forwards",
    "positionCode": "F",
    "players": [...]
  }
]
```

## Response format: Site settings (teams)

`GET /api/site/settings` → `teamsInSite[]`:

```json
{
  "uuid": "1ab8-1ab8bfj7N",
  "teamCode": "BIF",
  "ownerInstanceId": "bif1_bif",
  "logo": "https://sportality.cdn.s8y.se/team-logos/bif1_bif.svg",
  "icon": "https://sportality.cdn.s8y.se/team-logos/bif1_bif.svg",
  "instanceId": "bif1_bif",
  "name": "Brynäs",
  "publicUrl": "http://www.brynas.se/",
  "teamNames": {
    "code": "BIF",
    "short": "Brynäs",
    "long": "Brynäs IF",
    "full": "Brynäs Idrottsförening"
  },
  "teamInfo": {
    "founded": "1912",
    "golds": "13 (...)",
    "finals": "11* (...)",
    "retiredNumbers": "#06 Tord Lundström\n#26 Anders Huss",
    "address": "...",
    "email": "info@brynas.se"
  },
  "socialMediaInformation": [
    {"url": "https://www.facebook.com/brynasif/", "type": "facebook"},
    {"url": "https://www.instagram.com/brynas__if/", "type": "instagram"}
  ]
}
```

## Live data (Server-Sent Events)

Live game data uses SSE via an internal Kubernetes service (`game-broadcaster.s8y.se`). These are NOT available as public REST endpoints:

- `/live/game?gameUuid={uuid}` — real-time score updates
- `/live/standings?ssgtUuid={uuid}` — real-time standings

During live games, the frontend connects via EventSource to `game-broadcaster.s8y.se`.

## Player details

### Profile page

`GET /api/statistics-v2/athlete/profile-page?playerUuid={uuid}`

```json
{
  "uuid": "qQ9-322eZcouc",
  "fullName": "Oscar Lindberg",
  "firstName": "Oscar",
  "lastName": "Lindberg",
  "birthDate": "1991-10-29",
  "nationality": "SE",
  "gender": "male",
  "age": {"value": 33, "format": "years"},
  "weight": {"value": 88, "format": "kg"},
  "height": {"value": 183, "format": "cm"},
  "jerseyNumber": 24,
  "position": "Forward",
  "positionCode": "F",
  "shoots": "L",
  "team": {
    "uuid": "50e6-50e6DYeWM",
    "instanceId": "ske1_ske",
    "name": "Skellefteå",
    "code": "SAIK",
    "media": "https://sportality.cdn.s8y.se/team-logos/ske1_ske.svg"
  },
  "seasonStats": [
    {"field": "GP", "value": 52},
    {"field": "TP", "value": 67},
    {"field": "G", "value": 30},
    {"field": "A", "value": 37}
  ],
  "careerStats": [
    {"field": "GP", "value": 300},
    {"field": "TP", "value": 250},
    {"field": "G", "value": 120},
    {"field": "A", "value": 130}
  ],
  "statisticsProvider": "statnet",
  "isInSquad": true,
  "media": {"url": "https://s8y-cdn-sp-photos.imgix.net/...", "srcset": "..."}
}
```

### Athlete details (bio/physical)

`GET /api/sports-v2/athlete-details/{playerUuid}`

```json
{
  "athleteData": {
    "uuid": "qQ9-322eZcouc",
    "firstName": "Oscar",
    "lastName": "Lindberg",
    "dateOfBirth": "1991-10-29",
    "nationality": "SE",
    "height": 183,
    "weight": 88,
    "gender": "",
    "shoots": null,
    "playerExtIds": [
      {"id": 743, "extId": "3191", "extIdType": {"code": "ramses_legacy"}},
      {"id": 744, "extId": "1552", "extIdType": {"code": "isa"}}
    ]
  }
}
```

### Season list (years active in SHL)

`GET /api/statistics-v2/athlete/seasonList?playerUuid={uuid}`

```json
[
  {"value": "2025", "name": "2025/2026", "label": "2025/2026"},
  {"value": "2024", "name": "2024/2025", "label": "2024/2025"},
  {"value": "2012", "name": "2012/2013", "label": "2012/2013"},
  {"value": "2011", "name": "2011/2012", "label": "2011/2012"},
  {"value": "2010", "name": "2010/2011", "label": "2010/2011"},
  {"value": "2009", "name": "2009/2010", "label": "2009/2010"}
]
```

Note: gaps in years (2013–2023 for Lindberg) indicate time outside SHL (NHL, KHL, etc.) but the API does NOT provide info about those stints.

## Data NOT available

The following data is **not** exposed by the shl.se API:

- **Contract information** — No fields for contract length, salary, free agent status, or contract expiry.
- **Previous clubs / transfer history** — No endpoint showing "played for team X in 2015–2018". The season list shows *which years* a player was in SHL, but not which team per season.
- **NHL/international career** — Gaps in the season list indicate time outside SHL, but no details.
- **Draft information** — No NHL draft data.

For career history and contract data, refer to [EliteProspects](https://www.eliteprospects.com) (which shl.se itself links to from player pages).

### EliteProspects accessibility

EliteProspects is **not practically scrapeable**:

- ❌ **httpx/requests** → 403 Forbidden (Cloudflare blocks all non-browser requests)
- ❌ **Playwright headless** → Stuck on "Just a moment..." Cloudflare challenge page
- ❌ **Playwright headed** (with Xvfb) → Same result; Cloudflare Turnstile detects automation via browser fingerprinting (`navigator.webdriver = true`), Canvas/WebGL fingerprints, and lack of human input behavior
- ❓ **playwright-stealth / undetected-chromedriver** → Cat-and-mouse game, unreliable, violates EP ToS
- 💰 **EliteProspects API** (paid) → `developer.eliteprospects.com` — the only reliable and legal option

**Conclusion:** Contract and career history data requires either EP's paid API subscription or manual data entry.

## Team UUID mapping

Retrieved from `/api/site/settings` → `teamsInSite`:

| Team | teamCode | instanceId | UUID |
|------|----------|------------|------|
| Brynäs IF | BIF | bif1_bif | 1ab8-1ab8bfj7N |
| Djurgårdens IF | DIF | dif1_dif | 2459-2459QTs1f |
| Färjestad BK | FBK | fbk1_fbk | 752c-752c12zB7Z |
| Frölunda HC | FHC | fhc1_fhc | (from settings) |
| HV 71 | HV71 | hv711_hv71 | (from settings) |
| IF Björklöven | IFB | ifb1_ifb | 4519-4519Rdei6 |
| IF Malmö Redhawks | MIF | mif1_mif | (from settings) |
| Linköping HC | LHC | lhc1_lhc | (from settings) |
| Luleå HF | LHF | lhf1_lhf | (from settings) |
| Rögle BK | RBK | rbk1_rbk | (from settings) |
| Skellefteå AIK | SKE | ske1_ske | (from settings) |
| Timrå IK | TIK | tik1_tik | (from settings) |
| Växjö Lakers HC | VÄX | vlh1_vlh | (from settings) |
| Örebro HK | ÖHK | ohk1_ohk | (from settings) |

## Discovery notes

- The site is built with Vue 3 (Pinia state management) on the Sportality platform.
- SSR hydration embeds initial state in `window.__INITIAL_STATE__` (encoded IIFE).
- The frontend JS bundle at `/assets/index-*.js` contains all route definitions in the `Qt` constant.
- Internal service: `site-service-cached.frontend.svc.cluster.local` (Kubernetes).
- CDN for team logos/player photos: `sportality.cdn.s8y.se` and `s8y-cdn-sp-photos.imgix.net`.
- Ad network endpoints (maxetise.net, cmp.inmobi.com) make up most of the XHR noise.

## Comparison with SweHockey

| Data | SweHockey (stats.swehockey.se) | SHL.se API |
|------|-------------------------------|------------|
| Schedule | HTML scraping | JSON (needs season/series UUIDs) |
| Standings | HTML scraping | JSON (needs SSGT UUID) |
| Player stats | HTML scraping | JSON via team UUID |
| Rosters | HTML scraping | JSON via team UUID |
| Team info | Limited | Rich (logos, social, history) |
| Live scores | HTML polling (30s) | SSE real-time |
| Authentication | None | Header: `x-s8y-instance-id` |
| Stability | Page structure can change | Versioned API paths |
