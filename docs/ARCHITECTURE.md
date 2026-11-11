# Dockhand Discord Control — Architecture Plan

Status: Draft (planning artifact) · Date: 2026-11-09

## 1. Purpose and scope

**Goal:** A WebApp that controls a self-hosted Dockhand server through a Discord bot,
configured and observed primarily through a Reflex web UI.

**In scope (MVP):**

- Discord bot (slash commands) that can:
  - report status of Dockhand environments and Docker containers,
  - list Docker containers,
  - start / stop Docker containers.
- Clean separation between the Dockhand API integration and the Discord
  (chat platform) API integration, designed so a future message app can replace
  or supplement Discord.
- Reflex web UI used to configure:
  - Dockhand URL and API token,
  - Discord bot credentials (app / webhook),
  - per-container Discord visibility and channel mapping.

**Out of scope (MVP):** other chat platforms, multi-server scaling, RBAC beyond
channel mappings, container logs streaming, deployment automation beyond start/stop.

## 2. Requirements (as clarified)

- Runnable with Docker and `docker compose`.
- Python is the main language.
- Linters (`pyright`, `ruff`, `importlinter`) configured and run through `tox` envs.
- Unit tests with `pytest`; PEP 8 code style.
- Web framework: Reflex (Python).
- Code may be split into submodules, but a single cohesive structure is preferred.

## 3. Architecture overview

Layered design with explicit ports and adapters (Clean Architecture style, pragmatic
for a small project):

```
                 ┌──────────────────────────────────────────────┐
                 │  ui (Reflex app)                             │
                 │  pages: dashboard / settings / mappings     │
                 └──────────────────┬───────────────────────────┘
                                    │ imports
   ┌───────────────┐   ┌────────────▼────────────┐   ┌────────────────┐
   │ dockhand      │   │ domain (use cases,      │   │ persistence    │
   │ adapter       │◄──┤ ports & models          │──►│ adapter        │
   │ (httpx)       │   │                           │   │ (SQLite)       │
   └───────────────┘   └───────▲──────────────────┘   └────────────────┘
                                 │
   ┌───────────────┐   ┌────────────▼────────────┐         ┌────────────────┐
   │ discord       │──►│   domain (use cases)    │         │ config (pydantic)│
   │ adapter       │   │                           │         └────────────────┘
   │ (discord.py) │   └────────────▲─────────────┘
   └───────────────┘                │
                                   │
                        ┌──────────▼────────────┐
                        │ bridge wiring / main  │
                        │ (single service entry)│
                        └───────────────────────┘
```

Dependency rule:

- `domain` must not depend on any other internal module.
- `dockhand`, `discord`, `persistence` adapters implement domain ports and may
  depend only on `domain` (plus infra libraries such as `httpx` / `discord.py`).
- `ui` may depend on domain, adapters, persistence and config.
- `config` is a plain settings object with no internal dependencies.

## 4. Component breakdown

### 4.1 Domain (pure business logic)

- Models: `DockhandEnvironment`, `DockerContainer`, `ActionResult`, `ChannelMapping`.
- Ports (interfaces):
  - `DockhandClient` — list environments / containers, start / stop container.
  - `ChannelMappingRepository` — lookup mapping by channel / container, persist.
  - `SettingsRepository` — load / persist app settings.
- Use cases:
  - Snapshot use case (environment + container status) — used by Discord status/list
    and optionally the UI dashboard.
  - Start / stop use case — authorizes against the channel mapping before calling
    the dockhand client, returns `ActionResult`.

### 4.2 Dockhand API adapter

- `DockhandApiClient` implements `DockhandClient` (httpx).
- Base URL + bearer token supplied by configuration.
- API endpoint shapes are treated as an implementation detail behind the port;
  exact endpoints to be confirmed during implementation (tracked as research).

### 4.3 Discord adapter

- `DiscordBot` built with `discord.py` (slash commands):
  - `/dockhand_status`
  - `/dockhand_list`
  - `/dockhand_start <container>`
  - `/dockhand_stop <container>`
- Interaction flow: platform boundary → mapping authorization → domain use case →
  reply rendering → Discord response.
- Authorization: a container may only be controlled from a Discord channel that has
  an enabled mapping for that container (configured via Reflex UI).

### 4.4 Persistence adapter

- SQLite: singleton settings row + `channel_mappings` rows
  (`container_name`, `channel_id`, `enabled`).

### 4.5 Config

- `Settings` (pydantic-settings) provides only the SQLite database path
  (`DB_PATH`); all Dockhand and Discord settings (base URL, API token, bot token,
  guild ID) are configured through the web UI at `/settings` and persisted in
  SQLite.

### 4.6 Reflex UI (web app)

- App root: `rxconfig.py`, `app.py`, `pages/` (dashboard / settings / mappings),
  `styles/`.
- State (`AppState`) loads/saves settings and mappings via persistence ports.
- Dashboard: read-only status snapshot via domain use cases (observability; Discord
  remains the control plane).
- Settings page: Dockhand URL + token, Discord bot token / webhook, platform choice.
- Mappings page: choose container visibility (enabled), choose Discord channel per
  container.

## 5. Discord ↔ Dockhand flow (MVP)

1. User invokes a Discord slash command in a channel.
2. `discord` adapter receives the interaction (platform boundary; no dockhand types).
3. Adapter resolves channel → container mapping (enabled?) via persistence port.
4. Adapter calls the domain use case (`Start` / `Stop` / `Status` / `List`).
5. Domain use case calls `DockhandClient`.
6. Adapter renders the reply and answers the interaction; failures become friendly
   user-facing messages.

Future platforms: another chat app adapter can implement the same ports/use cases,
keeping the Dockhand API integration untouched.

## 6. Reflex flow

1. UI state loads settings + mappings (persistence ports) and, for dashboard,
   queries the domain snapshot.
2. Settings page persists via settings port.
3. Mappings page persists via mappings port.
4. The in-process bridge (same service) consumes mappings when Discord commands run.

## 7. Cross-cutting concerns

- Error handling: adapters translate infra errors into domain `ActionResult` outcomes.
- Config: env defaults + DB overrides.
- Logging: structured-ish std logging; no secrets in logs.

## 8. Tooling and quality gates

- Python 3.13, src layout (`src/dockhand_discord_control/`).
- `ruff` — lint + format (`PEP8`), config in `pyproject.toml`.
- `pyright` — type checking, config in `pyproject.toml` / `pyrightconfig.json`.
- `importlinter` — contracts in `importlinter.yaml` / `pyproject.toml`
  (domain isolation rules described above).
- `pytest` — unit tests under `tests/`.
- `tox` — envs: `lint` (ruff check + ruff format --check + lint-imports),
  `types` (pyright), `test` (pytest); run via `tox -e lint`, `tox -e types`, `tox -e test`.

## 9. Docker

- `Dockerfile`: Python 3.13 slim base, install project, copy source, non-root user,
  SQLite persisted via volume, Reflex port 8080.
- `docker-compose.yml`: single service `app`, build context `.`, ports `8080:8080`,
  `env_file: .env`, environment for `DOCKHAND_*` / `DISCORD_*`, named volume for SQLite.

## 10. Open items / bounded research for implementation

- Exact Dockhand REST API surface and auth scheme (bearer token assumed) — verify.
- Reflex lifecycle integration to run the Discord bridge inside the Reflex process.
- discord.py slash command registration strategy (global vs guild-scoped) and channel
  selection UX in Reflex (channel ID input vs richer picker) — MVP uses channel ID.

## 11. Suggested delivery order (backlog)

See the task board (`task-board`) for the authoritative, evolving backlog.
