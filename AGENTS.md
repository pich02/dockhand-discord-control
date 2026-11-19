# AGENTS.md

This file explains how the **dockhand-discord-control** project works so AI coding agents can contribute effectively.

## Project overview

Discord bot and Reflex web UI for controlling a self-hosted Dockhand server.

- **Language:** Python 3.12–3.13 (src layout)
- **Web framework:** Reflex (Python)
- **Entry point:** `app.py` (repo root) exposes `app = build_app()` so `reflex run` works from the repo root.
- **Reflex config:** `rxconfig.py` (`app_name="dockhand_discord_control"`, `app_module_import="app"`).
- **Docker:** `Dockerfile` + `docker-compose.yml`; Reflex UI on port 8080, SQLite persisted via named volume `dockhand_data`.

## Repository layout

```
app.py                      # Reflex app entry (builds app, starts Discord bridge)
rxconfig.py                 # Reflex configuration
pyproject.toml              # Project metadata, ruff/pytest/importlinter config
tox.ini                     # lint / types / test envs
Dockerfile                  # container image
docker-compose.yml          # single `app` service, port 8080, .env file
.env.example                # copy to .env and fill values
README.md                   # install / start / stop (local + Docker)
docs/ARCHITECTURE.md        # architecture plan
src/dockhand_discord_control/   # importable package (src layout)
  config/                   # pydantic-settings (Settings)
  domain/                   # pure business logic + ports (no internal deps)
  dockhand/                 # Dockhand API adapter (httpx)
  discord/                  # Discord bot adapter (discord.py)
  persistence/              # SQLite adapters (settings + channel mappings)
  ui/                       # Reflex pages, state, app wiring
tests/                      # pytest unit tests (mirrors src layout)
```

## How to run (local)

```bash
git clone <repo-url>
cd dockhand-discord-control
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env        # fill in DOCKHAND_* and DISCORD_BOT_TOKEN
reflex run --env prod --single-port --frontend-port 8080 --backend-port 8080 --backend-host 0.0.0.0
```

- UI: `http://localhost:8080`
- Stop: `Ctrl+C`

### Docker

```bash
cp .env.example .env
docker compose up --build        # start (port 8080)
docker compose down              # stop
docker compose down -v           # stop + remove SQLite volume
docker compose logs -f           # view logs
```

## Quality gates (tox)

Run via `tox` (preferred) or directly:

```bash
# lint: ruff check + ruff format --check + import-linter
tox -e lint
# types: pyright
tox -e types
# tests: pytest
tox -e test
```

Direct equivalents:

```bash
ruff check .
ruff format --check .
lint-imports
pyright
pytest
```

Key conventions:
- Line length 88, double quotes (ruff).
- `import-linter` enforces layered architecture: `domain` must not depend on other internal modules; adapters depend only on `domain` (+ infra libs).
- Python 3.13 type targets in `pyrightconfig.json` (include `src` and `tests`).

## Layered architecture (Clean Architecture style)

Dependency rule — inner layers do not depend on outer layers:

1. `config` — pydantic settings (no internal deps)
2. `domain` — models, ports, use cases (pure, no internal deps)
3. `dockhand`, `discord`, `persistence` — adapters implementing domain ports (may depend only on `domain`)
4. `ui` — Reflex app (may depend on domain, adapters, persistence, config)

The Discord bridge runs as a background daemon thread inside the Reflex process (started by `build_app()`), best-effort: a missing token or adapter failure is logged and the UI keeps running.

## How work gets done

1. Read the request + `docs/ARCHITECTURE.md` + this file; establish acceptance criteria.
2. Prefer small, vertical slices through the layers (domain → adapter → UI).
3. Write or update tests under `tests/` mirroring the `src/` layout.
4. Run `tox -e lint`, `tox -e types`, `tox -e test` before considering a change complete.
5. Keep diffs focused; avoid touching unrelated files.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `DOCKHAND_BASE_URL` | Yes | Dockhand API base URL |
| `DOCKHAND_API_TOKEN` | Yes | Dockhand API bearer token |
| `DISCORD_BOT_TOKEN` | Yes | Discord bot token |
| `DISCORD_GUILD_ID` | No | Guild ID to scope slash commands |
| `DB_PATH` | No | SQLite database path (`/app/data/app.sqlite` in Docker) |

Config is read from `.env` (Docker) or the environment (local). Runtime overrides may be stored in SQLite via the Reflex UI.

## Things to be careful about

- `rxconfig.app_name` must stay a simple package name (no dots) — Reflex validates it.
- `--single-port` on `reflex run` requires `--env prod` and equal `--frontend-port`/`--backend-port`.
- Do not commit `.env`; it is gitignored and dockerignored.
- SQLite data lives in `./data/` locally (default path) and in the `dockhand_data` volume under Docker.
- Discord bridge failures are logged, not fatal — don't treat bridge errors as UI failures.
