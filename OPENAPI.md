# OpenAPI Spec & Client Generation

The file [openapi.yaml](openapi.yaml) is the canonical API contract. Both the Python backend and any client (Kotlin, Swift, TypeScript, etc.) should derive from it.

## Viewing the spec

- **Swagger UI:** Start the API (`./start_api.sh`) and open http://localhost:8000/docs
- **Raw spec:** `openapi.yaml` in the repo root

## Generating a Kotlin client (Android)

### Prerequisites

Install `openapi-generator`:

```bash
# macOS
brew install openapi-generator

# Linux (via npm)
npm install @openapitools/openapi-generator-cli -g

# Or download the JAR directly
# https://github.com/OpenAPITools/openapi-generator#1---installation
```

### Generate

```bash
openapi-generator generate \
  -i openapi.yaml \
  -g kotlin \
  -o ../shl-se-android/api-client \
  --additional-properties=library=retrofit2,serializationLibrary=kotlinx_serialization,packageName=se.shl.api
```

This produces:
- **Data classes** for all schemas (ScheduleEntry, StandingsRow, PlayerStat, etc.)
- **Retrofit API interface** with suspend functions for each endpoint
- **Serialization config** using kotlinx.serialization

### Alternative: OkHttp (no Retrofit)

```bash
openapi-generator generate \
  -i openapi.yaml \
  -g kotlin \
  -o ../shl-se-android/api-client \
  --additional-properties=library=jvm-okhttp4,serializationLibrary=kotlinx_serialization,packageName=se.shl.api
```

### Using in the Android project

Add to your `build.gradle.kts`:

```kotlin
implementation(project(":api-client"))
```

Or copy the generated sources directly into your existing source tree.

### Example usage (generated code)

```kotlin
val api = ShlApi.create("http://your-server:8000")

// Get standings
val standings = api.getStandings(seasonId = 18263)
standings.data.forEach { row ->
    println("${row.rank}. ${row.team} (${row.tp}p, movement=${row.movement})")
}

// Get player stats
val players = api.getPlayerStats(seasonId = 18263, team = "SKE")
players.data.forEach { p ->
    println("${p.name}: ${p.goals}G ${p.assists}A ${p.totalPoints}TP")
}
```

## Keeping the spec in sync

When you add/change endpoints in the backend:

1. Update `openapi.yaml`
2. Regenerate the client
3. Verify the Android app compiles

The spec is the source of truth — not the auto-generated `/openapi.json` from FastAPI (which has weaker typing).

## Validating the spec

```bash
# Using openapi-generator
openapi-generator validate -i openapi.yaml

# Using spectral (if installed)
spectral lint openapi.yaml
```
