# Superseded Phase 1 removal manifest

The replacement handbook defines a different clinical asset. The paths below belonged to the previous implementation and were permanently removed on 26 September 2026 at the project owner's request. Counts include generated Python cache files and were recorded before removal.

| Exact path | Files | Purpose in old implementation |
| --- | ---: | --- |
| `oncology_evidence/` | 68 | Old entity-level SQLite package, prompts and terminology seed |
| `tests/` | 34 | Tests and artificial fixtures for the old entity model |
| `schemas/` | 33 | Generated schemas for the old entities |
| `docs/` | 2 | Previous requirements and evaluation guidance |
| `.github/` | 1 | CI workflow for the old package |
| `oncology_trial_evidence.egg-info/` | 6 | Generated distribution metadata for the old package |
| `pyproject.toml` | 1 | Previous package definition and command |
| `.env.example` | 1 | Previous configuration template |

The old `README.md` has been replaced with the current delivery status and intended architecture. `.gitignore` continues to protect credentials and user data.

**Preserved:** `.env`, `.venv`, `.git`, `data/`, and any other path not listed above. In particular, no simulation output or other user-generated data under `data/` is included in the removal scope.

The new [handbook interpretation](HANDBOOK_IMPLEMENTATION.md) is outside the removal scope.

After the project owner explicitly requested deletion, the eight paths above were removed. The Neon database was inspected with a read-only query. It had no user tables, and no database object was changed.

Obsolete `.pytest_cache/` and `.ruff_cache/` directories were also removed. A temporary local PostgreSQL driver directory used for the connection check was removed after that check.
