# dockhand-discord-control

Discord bot and Reflex web UI for controlling a self-hosted Dockhand server.

## Requirements

- Python 3.12 or 3.13
- `docker` and `docker compose` (for the Docker install)
- A running Dockhand server and a Discord bot token

## Install and run from scratch (local)

1. Clone the repo and create a virtual environment:

```bash
git clone <repo-url>
cd dockhand-discord-control
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

2. Install the package in editable mode (pulls in reflex, discord.py, httpx, pydantic):

```bash
pip install -e .
```

3. Create the environment file from the example and fill in your values:

```bash
cp .env.example .env
# edit .env with your Dockhand URL/token and Discord bot token
```

Required variables:

- `DOCKHAND_BASE_URL` — base URL of your Dockhand API (e.g. `http://dockhand:8080`)
- `DOCKHAND_API_TOKEN` — Dockhand API bearer token
- `DISCORD_BOT_TOKEN` — your Discord bot token
- `DISCORD_GUILD_ID` — optional; guild ID to scope slash command registration

4. Start the app:

```bash
reflex run --env prod --single-port --frontend-port 8080 --backend-port 8080 --backend-host 0.0.0.0
```

The Reflex web UI is available at `http://localhost:8080`. The Discord bridge starts
inside the same process on init (best-effort).

> The `--single-port` flag requires `--env prod` and runs both the frontend and
> backend on the same port (`--frontend-port` and `--backend-port` must match).

5. Stop the app:

Press `Ctrl+C` in the terminal running the app.

---

## Install and run with Docker

### Build and start

```bash
cp .env.example .env
# edit .env with your values

docker compose up --build
```

This builds the image, starts the `app` service, and maps port `8080` on the host to
port `8080` in the container. The Reflex web UI is available at `http://localhost:8080`.
SQLite data is persisted in the named Docker volume `dockhand_data` (mounted at
`/app/data`).

### Stop

```bash
docker compose down
```

To also remove the named volume (and thus the SQLite database):

```bash
docker compose down -v
```

### Restart

```bash
docker compose restart
```

### View logs

```bash
docker compose logs -f
```

---

## Configuration

| Variable | Required | Description | Example |
|---|---|---|---|
| `DOCKHAND_BASE_URL` | Yes | Dockhand API base URL | `http://dockhand:8080` |
| `DOCKHAND_API_TOKEN` | Yes | Dockhand API bearer token | `...` |
| `DISCORD_BOT_TOKEN` | Yes | Discord bot token | `...` |
| `DISCORD_GUILD_ID` | No | Guild ID to scope slash commands | `1234567890` |
| `DB_PATH` | No | SQLite database path | `/app/data/app.sqlite` |

Configuration is read from `.env` (docker compose) or the environment (local run).
Runtime overrides may also be stored in SQLite via the Reflex UI.

### Saving settings from the UI

Pressing **Save settings** on `/settings`:

1. persists the Dockhand and Discord values in SQLite (the `data/` directory is
   created automatically),
2. checks that the Dockhand API answers with the saved credentials,
3. starts, restarts or stops the Discord bot so it matches the saved token.

The outcome is shown as one status message, for example
`Settings saved. Dockhand reachable (2 environment(s), 5 container(s)). Discord bot started.`
Failures are reported in the same place instead of failing silently; the current
bot state is also shown on the dashboard.

### Checking the save flow end to end

`scripts/e2e_settings_save.py` drives a running backend over its real
Socket.IO transport (the same one the browser uses), clicks the equivalent of
the "Save settings" button and asserts that the status message arrives and the
values reach SQLite:

```bash
# terminal 1
DB_PATH=./data/e2e-app.sqlite reflex run --env dev --backend-only \
    --backend-port 8000 --backend-host 127.0.0.1

# terminal 2
uv run python scripts/e2e_settings_save.py
```

It prints the status message, the bot status, the persisted rows and a
`RESULT: PASS`/`FAIL` line. Use a dedicated database (as above): the check
replaces the settings it finds and restores them when it is done.

### Following the save flow in the logs

The app logs the save flow at `INFO` level, so the terminal shows exactly
where a save stops:

```
frontend connected (sid=…)                       # the browser reached the backend
frontend event: set_dockhand_base_url            # an input changed
frontend event: save_settings                    # the button was clicked
save_settings called: base_url set=True, …       # the handler ran
save_settings: writing the settings to ./data/app.sqlite
writing the Dockhand settings to ./data/app.sqlite (base_url=http://…)
save_settings: the settings were persisted
```

If there is no `frontend connected` line, the browser never reached the
backend — in dev mode the UI is served by the frontend dev server
(`http://localhost:3000`), not by the backend port. In production
(`--env prod --single-port`) the UI and the API share one port.

