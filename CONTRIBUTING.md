# Contributing to Retrivault

Thanks for your interest! Here's how to get started.

## Quick Start

```bash
git clone https://github.com/xiaoleishaw/retrivault.git
cd retrivault
python3 -m venv .venv && source .venv/bin/activate
make install
```

## Development Workflow

1. **Check existing issues** before starting work.
2. **Create a branch**: `git checkout -b feat/your-feature`
3. **Make changes**, keeping them focused and atomic.
4. **Run tests**: `make test` (all must pass)
5. **Lint**: `make lint` (no new warnings)
6. **Push and open a PR**.

## Code Standards

- **Python 3.10+** — leverage modern typing.
- **Ruff** — auto-format with `make fix`. Line length: 100.
- **mypy** — `strict = false` but `warn_return_any = true`. Add type annotations for all public APIs.
- **Tests** — every new feature needs tests. We use `pytest` with `pytest-asyncio`.
- **No circular imports** — keep dependency direction: `interfaces ← pipeline ← api ← frontend`.

## Adding a New Provider

All providers implement ABC interfaces in `src/interfaces/`:

1. Implement the ABC (e.g., `class MyVectorStore(VectorStore):`)
2. Register it in the corresponding `__init__.py` factory.
3. Add config fields to `config/config_schema.py`.
4. Wire it in `src/api/dependencies.py`.

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(scanner): add .excalidraw.md exclusion
fix(chunker): merge tiny heading-only fragments
docs(readme): add architecture diagram
test(retriever): add hybrid search edge cases
```

## PR Checklist

- [ ] Tests pass (`make test`)
- [ ] Lint passes (`make lint`)
- [ ] No new `# type: ignore` without justification
- [ ] Update README if adding a feature
- [ ] Add CHANGELOG entry if relevant

## Questions?

Open a [Discussion](https://github.com/xiaoleishaw/retrivault/discussions) or an [Issue](https://github.com/xiaoleishaw/retrivault/issues).
