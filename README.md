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
