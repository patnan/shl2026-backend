# Contributing

## Rules for every code change

1. **Update `openapi.yaml`** if any API endpoint, parameter, or response shape changed.
2. **Update `MODELS.md`** if any dataclass/model was added or modified.
3. **Update `README.md`** if capabilities, CLI usage, or key types changed.
4. **Update `ARCHITECTURE_PLAN.md`** if architectural behavior changed.
5. **Write tests** for new functionality and bug fixes.
6. **One commit** — code + tests + doc updates are a single atomic unit, not separate passes.

## Commit messages

Use conventional commits:

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — code change that doesn't fix a bug or add a feature
- `test:` — adding or updating tests

Keep the subject line under 70 characters. Use the body for details.

## Testing

Run all unit tests before committing:

```bash
python -m pytest tests/unit/
```

## API contract

`openapi.yaml` is the single source of truth for all endpoints and data types. Any API change that isn't reflected there is incomplete.
