# Project Conventions

## Every code change must include

1. Update `openapi.yaml` if any API endpoint, parameter, or response shape changed.
2. Update `MODELS.md` if any dataclass or model was added or modified.
3. Update `README.md` if capabilities, CLI usage, or key model types changed.
4. Update `ARCHITECTURE_PLAN.md` if architectural behavior changed.
5. Write and run tests for new functionality and bug fixes.
6. All of the above in one atomic commit — not separate follow-up passes.

## API contract

`openapi.yaml` is the single source of truth for all endpoints and data types. Any API change not reflected there is incomplete.

## Commit messages

Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`. Subject under 70 chars.

## Testing

Run `python -m pytest tests/unit/` before committing. All tests must pass.
