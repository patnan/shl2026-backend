# TODO — Future Improvements

Identified 2026-08-07. Sorted by category.

## Performance / Architecture

- [x] **Store singleton** — `_store(cache_dir)` creates a new `Store` every call (mkdir, executescript, migrations). Cache the instance per `cache_dir` with `functools.lru_cache`. Significant on RPi.
- [x] **Docker Compose tick-interval** — Poller tick is 30s but live targets are due every 25s. Reduce to `--tick-interval 5` (tick = how often worker checks, not fetch interval).
- [ ] **Parallel target execution** — Poller runs targets sequentially. Use a thread pool so concurrent targets (schedule + live_games + stats) don't block each other.
- [ ] **Async REST endpoints** — FastAPI endpoints block the event loop with sync DB reads. Use `async def` + `run_in_executor` for DB-heavy endpoints under load.

## Reliability / Robustness

- [ ] **Graceful shutdown** — No SIGTERM/SIGINT handling in poller/notifier. Docker sends SIGTERM on stop; mid-fetch state could corrupt. Finish current tick before exiting.
- [ ] **Thread safety for `_session`** — `requests.Session` is shared across threads if the API bootstrap path runs concurrently with the poller. Low risk but worth fixing.
- [ ] **Notification retry** — FCM send is fire-and-forget. If FCM is temporarily down, the event is marked processed and the notification is lost. Retry with backoff or leave unprocessed on transient errors.
- [ ] **Domain events pruning** — `domain_events` table is append-only. No cleanup. Add periodic deletion of processed events older than 7 days.

## Code Quality / Maintainability

- [ ] **Split store.py (918 lines)** — Handles games, schedule, standings, stats, rosters, live games, devices, poll targets, domain events. Split into domain-specific modules or at least separate module-level wrappers.
- [ ] **Eliminate module-level wrappers** — ~90 one-liner wrappers that just call `_store(cache_dir).method()`. Use `__getattr__` proxy or import `Store` directly in callers.
- [ ] **Split rest_api.py (613 lines)** — All endpoints in one `create_app()`. Use FastAPI routers to split by domain (games, standings, players, devices).
- [ ] **Pydantic response models** — Endpoints return `Dict[str, Any]`. Response models give validation, better /docs, and alignment with openapi.yaml.

## Testing

- [ ] **Test `_are_games_in_progress` / `_seconds_until_games_finish`** — New helper functions for stats deferral have no dedicated tests.
- [ ] **Test schedule hash-skip in poller context** — The poller calls `fetch_schedule(force_reparse=True)` with hash-skip, but no poller-level test verifies it.
- [ ] **Expand notifier tests** — Only builder is tested. Add tests for full worker loop (event processing, mark processed, error handling).

## Deployment / Operations

- [ ] **Log rotation** — No max-size in Docker Compose logging driver. Long-running containers accumulate unlimited logs.
- [ ] **SQLite backup strategy** — cache.db on volume mount. If SD card corrupts (RPi), all data is lost. Add periodic backup (cp or `.backup` command).
- [ ] **Poller/notifier health signals** — No way to detect a stalled poller from outside. Expose heartbeat file or /health on a secondary port.
- [ ] **Proactive SweHockey rate limiter** — No awareness of their rate limit threshold. Add a token bucket or similar to cap outbound requests/minute preemptively.

## Low-priority / Nice-to-have

- [ ] **Generic `from_dict` / `to_dict`** — Every dataclass has manual dict conversion. Use `dacite` or introspect `dataclasses.fields()`.
- [ ] **OpenAPI response validation in tests** — Validate API responses against openapi.yaml schemas automatically.
- [ ] **Pre-commit hooks** — Add `ruff`, `mypy`, and formatting enforcement. The Literal types would benefit from `mypy` checking.
