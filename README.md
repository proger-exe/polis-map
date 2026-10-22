# Polis Map

<!-- portfolio-card:start -->
[![Polis Map — Территории, государства и история общего мира.](docs/portfolio/card.png)](docs/portfolio/screenshot.png)

Скриншот работающего веб-демо Polis Map. [Полный размер](docs/portfolio/screenshot.png).
<!-- portfolio-card:end -->

Interactive political map for roleplay communities: states, polygon territories, colonization requests with moderation, an audit log, PNG export and optional Telegram account linking.

## What it does

- **Public map**: read-only world map with state territories, capitals and contested zones.
- **Admin mapper** (`/admin`): create states, draw polygons on the base map, upload a new base image, approve or reject colonization actions, browse the audit log.
- **Players**: link a Telegram account with a one-time code, submit colonization actions, export the current map as PNG.
- **Bot** (optional): `/link <code>`, `/profile`, `/map`, `/actions`.

## Stack

| Layer | Tech |
|---|---|
| API | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic Settings, Pillow (PNG export) |
| Web | React 18, TypeScript, Vite |
| Bot | aiogram 3 |
| Storage | SQLite (file in `data/`), base maps in `assets/maps/` |
| Tests | pytest, 11 API tests |

## Run

One container, API serves the built frontend:

```bash
cp .env.example .env        # change ADMIN_PASSWORD
docker compose up -d --build
# http://127.0.0.1:8000  (public map)  ·  /admin  ·  /docs
```

With the Telegram bot: set `TELEGRAM_BOT_TOKEN` in `.env` and run `docker compose --profile bot up -d`.

Local development:

```bash
make setup      # venv + npm install
make dev-api    # :8000
make dev-web    # :5173, proxies /api to the backend
make test
```

Default admin credentials are `admin` / `admin`; override them with `ADMIN_USERNAME` / `ADMIN_PASSWORD`.

## Layout

```
backend/app/   main.py (routes), services.py (domain logic), models.py, security.py
frontend/src/  App.tsx (public map + admin panel), api.ts, types.ts
bot/           aiogram handlers
assets/maps/   base maps (sample-world.svg is generated on first start)
tests/         API tests
```

## License

MIT
